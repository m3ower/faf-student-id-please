"""Disposable real owned HTTP/gRPC writes, streaming replicas and Patroni failover.

Only resources created under this invocation's UUID prefix may be stopped/removed.
No shared stack, deployment env, existing volume, production credential or image push.
"""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4


def docker(*args, check=True, stdin=None):
    try:
        r = subprocess.run(["docker", *map(str, args)], input=stdin, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Isolated Docker operation timed out") from None
    if check and r.returncode:
        raise RuntimeError("Isolated Docker operation failed")
    return r


def verify(args):
    root = Path(__file__).resolve().parents[1]
    prefix = "owned-ha-" + uuid4().hex[:10]
    network, control = prefix + "-app", prefix + "-control"
    containers, volumes, checks = [], [], []
    aliases = {"applicant": ["applicant-db", "applicant-db-2", "applicant-db-3"],
               "record": ["university-record-db", "university-record-db-2", "university-record-db-3"]}
    node_names = {name: prefix + "-" + name for group in aliases.values() for name in group}
    credentials = {scope: {key: secrets.token_urlsafe(32) for key in ("app", "admin", "replication", "rest", "internal", "broker", "management", "export")}
                   for scope in aliases}
    ids, generations, receipts, payloads = {}, {}, {}, {}
    service_names = {scope: prefix + "-" + scope + "-service" for scope in aliases}
    etcds = [prefix + "-etcd-" + str(i) for i in range(1, 4)]
    all_secrets = [value for group in credentials.values() for value in group.values()]

    def evidence(condition, message):
        if not condition:
            raise RuntimeError(message)
        checks.append(message)
        print("PASS " + message, flush=True)

    def wait(work, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                result = work()
                if result:
                    return result
            except (RuntimeError, ValueError, KeyError, IndexError):
                pass
            time.sleep(.5)
        raise RuntimeError("Isolated HA convergence exceeded its deadline")

    def sql(alias, query, database="postgres", check=False):
        r = docker("exec", node_names[alias], "psql", "-U", "postgres", "-d", database, "-v", "ON_ERROR_STOP=1", "-Atc", query, check=check)
        return r.stdout.strip() if r.returncode == 0 else None

    def primary(scope):
        leaders = [a for a in aliases[scope] if sql(a, "SELECT NOT pg_is_in_recovery()") == "t"]
        return leaders[0] if len(leaders) == 1 else None

    def replicated(scope):
        leader = primary(scope)
        if not leader:
            return False
        return sql(leader, "SELECT count(*) FROM pg_stat_replication WHERE state='streaming'") == "2"

    def call(scope, *, path="/health/ready", method="GET", body=None, operation=None, arguments=None):
        script = r"""
import json,sys,urllib.request,urllib.error,subprocess,os
from datetime import datetime,timedelta,timezone
from uuid import uuid4
v=json.load(sys.stdin)
if v['operation']:
 os.makedirs('/tmp/generated',exist_ok=True)
 subprocess.run([sys.executable,'-m','grpc_tools.protoc','-I/contracts','--python_out=/tmp/generated','--grpc_python_out=/tmp/generated','/contracts/studentid/messaging/v1/messaging.proto'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 sys.path.insert(0,'/tmp/generated')
 import grpc
 from studentid.messaging.v1 import messaging_pb2 as pb,messaging_pb2_grpc as rpc
 group='applicant-service' if v['scope']=='applicant' else 'university-record-service'
 operation=v['scope']+'.'+v['operation']
 d=pb.Delivery(message_id=str(uuid4()),correlation_id=str(uuid4()),kind=pb.REQUEST,topic='operation.'+operation+'.v1',operation=operation,group=group,publisher='session-service' if v['operation']=='generate' else 'credential-service',trace_id='grade5.ha',deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat().replace('+00:00','Z'),arguments=v['arguments'] or {},payload_json=json.dumps(v['body']).encode() if v['body'] is not None else b'')
 with grpc.insecure_channel(v['host']+':'+str(v['port']+1000)) as channel:
  r=rpc.MessageConsumerStub(channel).Deliver(d,timeout=2,metadata=[('authorization','Bearer '+v['internal']),('x-service-name',d.publisher),('x-trace-id',d.trace_id)])
  print(json.dumps({'status':r.status,'body':json.loads(r.body_json)}))
else:
 h={'X-Management-Token':v['management'],'X-Trace-Id':'grade5.ha','Content-Type':'application/json'}
 data=None if v['body'] is None else json.dumps(v['body']).encode()
 req=urllib.request.Request('http://'+v['host']+':'+str(v['port'])+v['path'],headers=h,data=data,method=v['method'])
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as r:status=r.status;raw=r.read()
 except urllib.error.HTTPError as r:status=r.code;raw=r.read();r.close()
 print(json.dumps({'status':status,'body':json.loads(raw) if raw else None}))
"""
        r = docker("run", "--rm", "-i", "--network", network, "-v", str(root / "contracts/proto") + ":/contracts:ro",
                   "--entrypoint", "python", args.helper_image, "-c", script,
                   stdin=json.dumps({"scope": scope, "host": service_names[scope], "port": 8080 if scope == "applicant" else 8081,
                                     "path": path, "method": method, "body": body, "operation": operation,
                                     "arguments": arguments, **{k: credentials[scope][k] for k in ("management", "internal")}}))
        return json.loads(r.stdout)

    def row_path(scope):
        return ("/api/v1/applicants/" if scope == "applicant" else "/api/v1/university-records/") + ids[scope]

    def own_rows(scope):
        table = "applicants" if scope == "applicant" else "university_records"
        return all(sql(alias, "SELECT count(*) FROM " + table + " WHERE id='" + ids[scope] + "'", scope + "_db") == "1"
                   and sql(alias, "SELECT count(*) FROM integration_initializations WHERE applicant_id='" + generations[scope]['applicantId'] + "'", scope + "_db") == "1"
                   for alias in aliases[scope])

    try:
        docker("network", "create", network)
        docker("network", "create", "--internal", control)
        for i, name in enumerate(etcds, 1):
            alias = "owned-ha-etcd-" + str(i)
            volume = name + "-data"; volumes.append(volume); containers.append(name)
            initial = ",".join(f"owned-ha-etcd-{j}=http://owned-ha-etcd-{j}:2380" for j in range(1, 4))
            docker("run", "-d", "--name", name, "--network", control, "--network-alias", alias,
                   "-v", volume + ":/etcd-data", args.etcd_image, "/usr/local/bin/etcd", "--name=" + alias,
                   "--data-dir=/etcd-data", "--listen-client-urls=http://0.0.0.0:2379", "--advertise-client-urls=http://" + alias + ":2379",
                   "--listen-peer-urls=http://0.0.0.0:2380", "--initial-advertise-peer-urls=http://" + alias + ":2380",
                   "--initial-cluster=" + initial, "--initial-cluster-state=new", "--initial-cluster-token=" + prefix)
        for name in etcds:
            wait(lambda: docker("exec", name, "/usr/local/bin/etcdctl", "endpoint", "health", check=False).returncode == 0, 45)
        for scope in aliases:
            for alias in aliases[scope]:
                name = node_names[alias]; containers.append(name)
                volume = name + "-data"; volumes.append(volume)
                env = {"HA_NAME": alias, "HA_SCOPE": scope, "HA_ETCD_HOSTS": "owned-ha-etcd-1:2379,owned-ha-etcd-2:2379,owned-ha-etcd-3:2379",
                       "HA_APP_USER": scope + "_user", "HA_APP_DATABASE": scope + "_db",
                       **{"HA_" + key.upper() + "_PASSWORD": credentials[scope][key] for key in ("admin", "replication", "rest", "app")}}
                command = ["run", "-d", "--name", name, "--network", control, "--network-alias", alias, "-v", volume + ":/var/lib/postgresql/ha"]
                for key, value in env.items(): command += ["-e", key + "=" + value]
                docker(*command, args.postgres_image)
                docker("network", "connect", "--alias", alias, network, name)
        for scope in aliases:
            wait(lambda: replicated(scope))
            evidence(True, scope + ": one primary and two streaming replicas")
            hosts = ",".join(a + ":5432" for a in aliases[scope])
            secret = credentials[scope]
            if scope == "applicant":
                url = "jdbc:postgresql://" + hosts + "/applicant_db?targetServerType=primary&connectTimeout=1&socketTimeout=3&hostRecheckSeconds=1"
            else:
                url = "postgres://record_user:" + secret['app'] + "@" + hosts + "/record_db?sslmode=disable&connect_timeout=1&target_session_attrs=read-write"
            env = {"DB_URL": url, "DB_USER": scope + "_user", "DB_PASSWORD": secret['app'], "BROKER_GRPC_TARGET": "unavailable:9093",
                   "BROKER_SERVICE_TOKEN": secret['broker'], "SERVICE_INTERNAL_TOKEN": secret['internal'], "MANAGEMENT_TOKEN": secret['management'],
                   "WAREHOUSE_EXPORT_TOKEN": secret['export'], "DISCOVERY_URL": "", "SESSION_CLIENT": "broker", "INTEGRATION_DELIVERY_WORKER_ENABLED": "false"}
            name = service_names[scope]; containers.append(name)
            command = ["run", "-d", "--name", name, "--network", network]
            for key, value in env.items(): command += ["-e", key + "=" + value]
            docker(*command, args.applicant_image if scope == "applicant" else args.record_image)
            wait(lambda: call(scope)['status'] == 200)
            payload = {"name": "Synthetic HA applicant", "studentId": "HA-" + uuid4().hex[:12], "major": "FAF"}
            payload.update({"studyYear": 2, "universityStatus": "ENROLLED", "role": "STUDENT", "courses": ["PAD"]} if scope == "applicant" else {"enrolledSince": "2024-09-01", "status": "ACTIVE", "courses": ["PAD"], "outlookGroups": [], "fcimMessages": []})
            result = call(scope, method="POST", path="/api/v1/applicants" if scope == "applicant" else "/api/v1/university-records/", body=payload)
            evidence(result['status'] == 201, scope + ": actual HTTP mutation succeeds")
            ids[scope] = result['body']['id']
            payloads[scope] = payload
            generations[scope] = {"requestId": str(uuid4()), "applicantId": str(uuid4()), "sessionId": str(uuid4()), "seed": 88731, "difficulty": "HARD"}
            evidence(call(scope, operation="generate", body=generations[scope])['status'] == 202, scope + ": actual gRPC initialization persists")
            receipt = call(scope, operation="getInitialization", arguments={"applicantId": generations[scope]['applicantId']})
            evidence(receipt['status'] == 200, scope + ": authenticated gRPC receipt available")
            receipts[scope] = receipt['body']
            wait(lambda: own_rows(scope))
            evidence(True, scope + ": HTTP row is visible on both physical replicas")
        # Crash only owned test primaries. No application restart or mutation replay during ambiguity.
        crashed = {scope: primary(scope) for scope in aliases}
        for scope, alias in crashed.items(): docker("kill", node_names[alias])
        for scope in aliases:
            first = call(scope, path=row_path(scope))
            evidence(first['status'] in (200, 503, 504), scope + ": failover read is success or bounded availability error, never mock/500")
            wait(lambda: primary(scope) and primary(scope) != crashed[scope])
            wait(lambda: call(scope, path=row_path(scope))['status'] == 200)
            evidence(True, scope + ": automatic promotion restores original HTTP data without restarting service")
            updated = {**payloads[scope], "courses": ["PAD", "HA"]}
            evidence(call(scope, path=row_path(scope), method="PUT", body=updated)['status'] == 200,
                     scope + ": a new HTTP mutation succeeds on the promoted writer")
            result = call(scope, operation="getInitialization", arguments={"applicantId": generations[scope]['applicantId']})
            evidence(result['status'] == 200 and result['body'] == receipts[scope], scope + ": durable gRPC receipt unchanged across failover")
            evidence(call(scope, operation="generate", body=generations[scope])['status'] == 202, scope + ": same business-ID replay remains idempotent")
            leader = primary(scope)
            evidence(sql(leader, "SELECT count(*) FROM integration_initializations WHERE applicant_id='" + generations[scope]['applicantId'] + "'", scope + "_db") == "1", scope + ": no duplicated durable initialization")
            evidence(sql(leader, "SELECT count(*) FROM integration_deliveries WHERE applicant_id='" + generations[scope]['applicantId'] + "'", scope + "_db") == "2", scope + ": pending owner outbox records survive failover and replay")
            docker("start", node_names[crashed[scope]])
            wait(lambda: replicated(scope), 120)
            evidence(sql(crashed[scope], "SELECT pg_is_in_recovery()") == "t", scope + ": former primary safely rejoins as replica")
            wait(lambda: own_rows(scope))
        # Stop a majority of the shared control quorum; neither DB may retain a writable leader.
        for name in etcds[:2]: docker("stop", name)
        wait(lambda: all(not any(sql(a, "SELECT NOT pg_is_in_recovery()") == "t" for a in aliases[scope]) for scope in aliases), 60)
        evidence(True, "etcd majority loss demotes both database primaries")
        for scope in aliases:
            evidence(call(scope)['status'] == 503, scope + ": readiness fails closed without a writer")
        for name in etcds[:2]: docker("start", name)
        for scope in aliases:
            wait(lambda: replicated(scope), 120)
            wait(lambda: call(scope, path=row_path(scope))['status'] == 200)
            evidence(True, scope + ": quorum restoration recovers connections and both replicas")
        for name in containers:
            text = docker("logs", name, check=False).stdout + docker("logs", name, check=False).stderr
            evidence(not any(secret in text for secret in all_secrets), "credential-free logs: " + name.removeprefix(prefix + "-"))
        output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
        report = {"passed": len(checks), "checks": checks, "images": {key: getattr(args, key + '_image') for key in ('postgres', 'applicant', 'record', 'etcd')},
                  "scope": "isolated synthetic stores; asynchronous replication; no published/deployed full-team claim"}
        (output / "results.json").write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({"passed": len(checks), "scope": report['scope']}), flush=True)
    finally:
        for name in reversed(containers): docker("rm", "-f", "-v", name, check=False)
        for volume in volumes: docker("volume", "rm", volume, check=False)
        for net in (network, control): docker("network", "rm", net, check=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--postgres-image', default='pad-owned-postgres-ha:grade5')
    p.add_argument('--applicant-image', required=True)
    p.add_argument('--record-image', required=True)
    p.add_argument('--helper-image', default='pad-owned-grpc-tests:local')
    p.add_argument('--etcd-image', default='quay.io/coreos/etcd:v3.5.17@sha256:a055da833a7c013b836ed0822e8ec1f99b059658be255ad8d0fcd31b635ae3d6')
    p.add_argument('--output', default='docs-local/owned-postgres-ha/live')
    verify(p.parse_args())
