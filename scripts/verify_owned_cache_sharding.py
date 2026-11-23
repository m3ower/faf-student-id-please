"""Fresh owned replicas + PostgreSQL + Redis: no shared stack, ports, secrets or publication."""
import argparse
import hashlib
import hmac
import bisect
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
        raise RuntimeError("Isolated cache verification timed out") from None
    if check and r.returncode:
        raise RuntimeError("Isolated cache verification operation failed")
    return r


def verify(args):
    root = Path(__file__).resolve().parents[1]
    prefix = "owned-shards-" + uuid4().hex[:10]
    scopes = ('applicant', 'record')
    networks = {s: prefix + '-' + s + '-net' for s in scopes}
    dbs = {s: prefix + '-' + s + '-db' for s in scopes}
    caches = {s: {node:prefix+'-'+s+'-redis-'+node for node in ('a','b','c')} for s in scopes}
    points=sorted((hashlib.sha256(('owned-cache-ring-v1\nnode\n'+node+'\n'+str(i)).encode()).hexdigest(),node) for node in ('a','b','c') for i in range(128))
    def owner(key):
        hashed=hashlib.sha256(('owned-cache-ring-v1\nkey\n'+key).encode()).hexdigest()
        return points[bisect.bisect_left([p[0] for p in points],hashed)%len(points)][1]
    nodes = {s: [prefix + '-' + s + '-' + str(i) for i in (1, 2)] for s in scopes}
    credentials = {s: {k: secrets.token_urlsafe(32) for k in ('db', 'cache', 'internal', 'management', 'broker', 'export')} for s in scopes}
    containers, checks = [], []

    def evidence(ok, message):
        if not ok: raise RuntimeError(message)
        checks.append(message); print('PASS ' + message, flush=True)

    def wait(work, seconds=60):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                value = work()
                if value: return value
            except (RuntimeError, KeyError, ValueError): pass
            time.sleep(.1)
        raise RuntimeError('Isolated cache convergence exceeded its deadline')

    def sql(s, query):
        return docker('exec', dbs[s], 'psql', '-U', s, '-d', s + '_cache_test', '-v', 'ON_ERROR_STOP=1', '-Atc', query).stdout.strip()

    def redis(s, *command, node=None):
        if command[0]=='KEYS' and node is None:
            return '\n'.join(value for id in caches[s] for value in redis(s,*command,node=id).splitlines() if value)
        if node is None:node=owner(command[1]) if command[0] in ('GET','SET','EXISTS') else 'a'
        return docker('exec', '-e', 'REDISCLI_AUTH=' + credentials[s]['cache'], caches[s][node], 'redis-cli', '--raw', *command).stdout.strip()

    def call(s, index=0, path='/status', method='GET', body=None, operation=None, arguments=None, publisher=None, wrong=False):
        script = r"""
import json,sys,subprocess,os,urllib.request,urllib.error
from datetime import datetime,timedelta,timezone
from uuid import uuid4
v=json.load(sys.stdin)
if v['operation']:
 os.makedirs('/tmp/generated',exist_ok=True)
 subprocess.run([sys.executable,'-m','grpc_tools.protoc','-I/contracts','--python_out=/tmp/generated','--grpc_python_out=/tmp/generated','/contracts/studentid/messaging/v1/messaging.proto'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 sys.path.insert(0,'/tmp/generated')
 import grpc
 from studentid.messaging.v1 import messaging_pb2 as pb,messaging_pb2_grpc as rpc
 operation=v['scope']+'.'+v['operation']
 caller=v['publisher'] or ('session-service' if v['operation']=='generate' else 'credential-service')
 d=pb.Delivery(message_id=str(uuid4()),correlation_id=str(uuid4()),kind=pb.REQUEST,topic='operation.'+operation+'.v1',operation=operation,group='applicant-service' if v['scope']=='applicant' else 'university-record-service',publisher=caller,trace_id='grade6.cache',deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat().replace('+00:00','Z'),arguments=v['arguments'] or {},payload_json=json.dumps(v['body']).encode() if v['body'] is not None else b'')
 with grpc.insecure_channel(v['host']+':'+str(v['port']+1000)) as channel:
  r=rpc.MessageConsumerStub(channel).Deliver(d,timeout=2,metadata=[('authorization','Bearer '+v['internal']),('x-service-name',caller),('x-trace-id','grade6.cache')])
  print(json.dumps({'status':r.status,'body':json.loads(r.body_json)}))
else:
 h={'Content-Type':'application/json','X-Trace-Id':'grade6.cache','X-Management-Token':'wrong' if v['wrong'] else v['management'], 'Authorization':'Bearer '+('wrong' if v['wrong'] else v['internal']), 'X-Service-Name':'gateway-service','X-Player-Id':str(uuid4()),'X-Session-Id':str(uuid4())}
 data=None if v['body'] is None else json.dumps(v['body']).encode()
 req=urllib.request.Request('http://'+v['host']+':'+str(v['port'])+v['path'],headers=h,data=data,method=v['method'])
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as r:status=r.status;raw=r.read()
 except urllib.error.HTTPError as r:status=r.code;raw=r.read();r.close()
 print(json.dumps({'status':status,'body':json.loads(raw) if raw else None}))
"""
        r = docker('run', '--rm', '-i', '--network', networks[s], '-v', str(root / 'contracts/proto') + ':/contracts:ro',
                   '--entrypoint', 'python', args.helper_image, '-c', script,
                   stdin=json.dumps({'scope': s, 'host': nodes[s][index], 'port': 8080 if s == 'applicant' else 8081,
                                     'path': path, 'method': method, 'body': body, 'operation': operation,
                                     'arguments': arguments, 'publisher': publisher, 'wrong': wrong,
                                     'internal': credentials[s]['internal'], 'management': credentials[s]['management']}))
        return json.loads(r.stdout)

    def hits(s, i=0): return call(s, i)['body']['cache']['hits']

    try:
        for s in scopes:
            docker('network', 'create', networks[s])
            containers.append(dbs[s]); docker('run', '-d', '--name', dbs[s], '--network', networks[s], '-e', 'POSTGRES_USER=' + s,
                '-e', 'POSTGRES_DB=' + s + '_cache_test', '-e', 'POSTGRES_PASSWORD=' + credentials[s]['db'], 'postgres:16-alpine')
            for shard in caches[s].values():
                containers.append(shard);docker('run','-d','--name',shard,'--network',networks[s],
                    '-v',str(root/'docker/owned-cache/start.sh')+':/owned-cache/start.sh:ro','-e','CACHE_PASSWORD='+credentials[s]['cache'],
                    '--entrypoint','sh',args.redis_image,'/owned-cache/start.sh')
            wait(lambda: docker('exec', dbs[s], 'pg_isready', '-h', '127.0.0.1', '-U', s, check=False).returncode == 0)
            for id in caches[s]:wait(lambda:redis(s,'PING',node=id)=='PONG')
            for i, name in enumerate(nodes[s]):
                env = {'DB_URL': ('jdbc:postgresql://' + dbs[s] + ':5432/applicant_cache_test') if s == 'applicant' else ('postgres://record:' + credentials[s]['db'] + '@' + dbs[s] + ':5432/record_cache_test?sslmode=disable'),
                       'DB_USER': s, 'DB_PASSWORD': credentials[s]['db'], 'CACHE_ENABLED': 'true',
                       ('CACHE_REDIS_HOST' if s == 'applicant' else 'CACHE_REDIS_ADDR'): caches[s]['a'] + ('' if s == 'applicant' else ':6379'),
                       'CACHE_REDIS_NODES': ','.join(id+'='+host+':6379' for id,host in caches[s].items()),'CACHE_VIRTUAL_NODES':'128',
                       'CACHE_REDIS_PASSWORD': credentials[s]['cache'], 'BROKER_GRPC_TARGET': 'unavailable:9093',
                       'BROKER_SERVICE_TOKEN': credentials[s]['broker'], 'SERVICE_INTERNAL_TOKEN': credentials[s]['internal'],
                       'MANAGEMENT_TOKEN': credentials[s]['management'], 'WAREHOUSE_EXPORT_TOKEN': credentials[s]['export'],
                       'DISCOVERY_URL': '', 'INTEGRATION_DELIVERY_WORKER_ENABLED': 'false', 'SESSION_CLIENT': 'broker'}
                command = ['run', '-d', '--name', name, '--network', networks[s]]
                for k, v in env.items(): command += ['-e', k + '=' + v]
                containers.append(name); docker(*command, args.applicant_image if s == 'applicant' else args.record_image)
                wait(lambda: call(s, i)['status'] == 200)
        for s in scopes:
            if s == 'applicant':
                payload = {'name': 'Cache Before', 'studentId': 'CACHE-' + uuid4().hex[:12], 'major': 'FAF', 'studyYear': 2,
                           'universityStatus': 'ENROLLED', 'role': 'STUDENT', 'courses': ['PAD']}
                created = call(s, path='/api/v1/applicants', method='POST', body=payload)
                evidence(created['status'] == 201, 'Applicant real create')
                path = '/api/v1/applicants/' + created['body']['id']; kind = 'applicant'; field = 'name'; before = 'Cache Before'; after = 'Cache After'
                updated = {**payload, 'name': after}; write_path = path; value = lambda r: r['body'][field]
            else:
                payload = {'academicYear': '2026-2027', 'semester': '2026-1', 'weekOfSemester': 8,
                           'courses': [{'code': 'PAD', 'name': 'Distributed Applications', 'year': 3}]}
                evidence(call(s, path='/api/v1/university-records/academic-context', method='PUT', body=payload)['status'] == 204, 'Record actual academic configuration')
                path = '/api/v1/records/academic-context'; kind = 'academic-context'; field = 'weekOfSemester'; before = 8; after = 9
                updated = {**payload, 'weekOfSemester': after}; write_path = '/api/v1/university-records/academic-context'; value = lambda r: r['body'][field]
            baseline = hits(s)
            wait(lambda: call(s, path=path)['status'] == 200 and hits(s) > baseline)
            evidence(value(call(s, path=path)) == before, s + ': real hot HTTP GET returns source data')
            other = hits(s, 1); evidence(value(call(s, 1, path=path)) == before and hits(s, 1) > other, s + ': second replica shares Redis entry')
            evidence(call(s, path=path, wrong=True)['status'] == 401, s + ': hot cache does not bypass authentication')
            generation = sql(s, "SELECT revision FROM cache_generations WHERE scope='data'")
            pattern = ('applicant' if s == 'applicant' else 'record') + ':cache:v1:' + kind + ':' + generation + ':*'
            keys = redis(s, 'KEYS', pattern).splitlines(); evidence(len(keys) == 1, s + ': opaque generation-scoped cache key')
            key = keys[0]; original = redis(s, 'GET', key); envelope = json.loads(original)
            body = json.loads(envelope['body']) if s == 'applicant' else envelope['body']
            body[field] = 'FORGED' if s == 'applicant' else 999
            envelope['body'] = json.dumps(body) if s == 'applicant' else body
            redis(s, 'SET', key, json.dumps(envelope), 'EX', '30')
            evidence(value(call(s, path=path)) == before, s + ': tampered value cannot replace authoritative data')
            evidence(call(s)['body']['cache']['errors'] > 0, s + ': corruption is observable without exposing payloads')
            redis(s, 'SET', key, original, 'EX', '30')
            docker('pause', caches[s][owner(key)])
            try:
                evidence(call(s, 1, path=write_path, method='PUT', body=updated)['status'] in (200, 204), s + ': real replica-B write commits while Redis is paused')
                evidence(value(call(s, path=path)) == after, s + ': cache outage falls back to fresh database data')
            finally: docker('unpause', caches[s][owner(key)])
            evidence(sql(s, "SELECT revision FROM cache_generations WHERE scope='data'") != generation, s + ': database commit advanced durable generation')
            baseline = hits(s)
            wait(lambda: value(call(s, path=path)) == after and hits(s) > baseline)
            evidence(redis(s, 'GET', key) == original, s + ': old entry survived outage but is unreachable after write')
            evidence(value(call(s, 1, path=path)) == after, s + ': both replicas use committed updated view')
            docker('pause', dbs[s])
            try:
                evidence(call(s, path=path)['status'] in (503, 504), s + ': database failure is never hidden by a warm cache')
            finally: docker('unpause', dbs[s])
            wait(lambda: call(s, path=path)['status'] == 200)
            # Shared HTTP/gRPC application functions use the same cache and live readiness.
            generation_request = {'requestId': str(uuid4()), 'applicantId': str(uuid4()), 'sessionId': str(uuid4()), 'seed': 72137, 'difficulty': 'HARD'}
            evidence(call(s, operation='generate', body=generation_request)['status'] == 202, s + ': actual native gRPC generation remains intact')
            operation = 'getProfile' if s == 'applicant' else 'enrollmentFacts'; arguments = {'applicantId': generation_request['applicantId']}
            evidence(call(s, operation=operation, arguments=arguments)['status'] == 200, s + ': authenticated gRPC projection loads')
            h = hits(s, 1); evidence(call(s, 1, operation=operation, arguments=arguments)['status'] == 200 and hits(s, 1) > h, s + ': gRPC projection cache is shared across replicas')
            evidence(call(s, operation='getReadiness', arguments=arguments)['status'] == 202, s + ': cached facts are not a peer readiness receipt')
            if s == 'applicant':
                evidence(call(s, operation='getProfile', arguments=arguments, publisher='session-service')['status'] == 202, 'Applicant Session readiness check remains live with cached profile')
                evidence(call(s, path=path, method='DELETE')['status'] == 204 and call(s, 1, path=path)['status'] == 404, 'Applicant deletion invalidates both replicas')
            else:
                evidence(call(s, path='/api/v1/records/enrollment?studentId=unknown')['status'] == 503, 'Record Session outage never becomes a cached permission grant')
            population=[]
            for i in range(16):
                request={'requestId':str(uuid4()),'applicantId':str(uuid4()),'sessionId':str(uuid4()),'seed':81000+i,'difficulty':'HARD'}
                if call(s,operation='generate',body=request)['status']!=202:raise RuntimeError('Actual shard population generation failed')
                population.append(request['applicantId'])
            current=sql(s,"SELECT revision FROM cache_generations WHERE scope='data'")
            projection='profile' if s=='applicant' else 'enrollment-facts'
            def cache_key(id):
                signature=hmac.new(credentials[s]['internal'].encode(),(s+'-cache-v1\nidentity\n'+id).encode(),hashlib.sha256).hexdigest()
                return s+':cache:v1:'+projection+':'+current+':'+signature
            targets={}
            for id in population:targets.setdefault(owner(cache_key(id)),id)
            evidence(len(targets)==3,s+': generated real projections cover all three physical owners')
            for node,id in targets.items():
                baseline=hits(s)
                wait(lambda:call(s,operation=operation,arguments={'applicantId':id})['status']==200 and hits(s)>baseline)
                key_for_id=cache_key(id)
                evidence(all((redis(s,'EXISTS',key_for_id,node=n)=='1')==(n==node) for n in caches[s]),s+': projection stored only on shard '+node)
            baseline=hits(s,1)
            for id in targets.values():
                if call(s,1,operation=operation,arguments={'applicantId':id})['status']!=200:raise RuntimeError('Replica projection failed')
            evidence(hits(s,1)>=baseline+3,s+': second replica agrees with all three owners')
            docker('pause',caches[s]['b'])
            try:
                evidence(call(s,operation=operation,arguments={'applicantId':targets['b']})['status']==200,s+': paused owner falls back to authoritative source')
                baseline=hits(s)
                for n in ('a','c'):
                    if call(s,operation=operation,arguments={'applicantId':targets[n]})['status']!=200:raise RuntimeError('Healthy shard projection failed')
                evidence(hits(s)>=baseline+2,s+': failed owner does not suppress healthy shard hits')
                evidence(all(redis(s,'EXISTS',cache_key(targets['b']),node=n)=='0' for n in ('a','c')),s+': failed keys are not spilled to another owner')
                evidence(call(s)['status']==200,s+': shard failure is not a readiness dependency')
            finally:docker('unpause',caches[s]['b'])
            baseline=hits(s)
            wait(lambda:call(s,operation=operation,arguments={'applicantId':targets['b']})['status']==200 and hits(s)>baseline)
            evidence(True,s+': same owner resumes hits after recovery')
            evidence(call(s)['body']['cache']['shards']==3 and call(s)['body']['cache']['virtualNodes']==128,s+': status reports real ring configuration')
            evidence(call(s)['body']['load']['activeTasks'] == 0, s + ': completed cache work releases business admission')
        all_secrets = [v for group in credentials.values() for v in group.values()]
        for name in containers:
            r = docker('logs', name, check=False); output = r.stdout + r.stderr
            evidence(not any(secret in output for secret in all_secrets), 'credential-free logs: ' + name.removeprefix(prefix + '-'))
        output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
        report = {'passed': len(checks), 'checks': checks, 'images': {'applicant': args.applicant_image, 'record': args.record_image},
                  'scope': 'isolated actual owned services, PostgreSQL and Redis; no full Gateway/Session gameplay acceptance'}
        (output / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8');print(json.dumps({'passed': len(checks)}), flush=True)
    finally:
        for name in containers: docker('unpause', name, check=False)
        for name in reversed(containers): docker('rm', '-f', '-v', name, check=False)
        for name in networks.values(): docker('network', 'rm', name, check=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--applicant-image', required=True);p.add_argument('--record-image', required=True)
    p.add_argument('--helper-image', default='pad-owned-grpc-tests:local')
    p.add_argument('--redis-image', default='redis:7.4-alpine@sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe')
    p.add_argument('--output', default='docs-local/owned-cache-sharding/live')
    verify(p.parse_args())
