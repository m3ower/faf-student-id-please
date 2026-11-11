"""Build and verify the selected REST membership boundary in disposable Docker resources.

Requires the private candidate sources; never reads the shared deployment's .env.
No Message Broker, queues, production credentials or existing database volumes are used.
"""

import argparse
import json
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid


HOST = "11111111-1111-1111-1111-111111111111"
JUNIOR = "22222222-2222-2222-2222-222222222222"
DENIED = "33333333-3333-3333-3333-333333333333"
OUTSIDER = "44444444-4444-4444-4444-444444444444"
MEMBERSHIP = "/internal/v1/session-memberships/verify"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for service in ("gateway", "record", "session", "dms"):
        parser.add_argument(f"--{service}-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs-local/membership-baseline"))
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    project = "pad-membership-" + uuid.uuid4().hex[:10]
    checks = []
    probes = []
    count = 0

    def run(command, *, timeout=600, name="command"):
        nonlocal count
        count += 1
        log_path = output / f"{count:02d}-{name}.log"
        with log_path.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect its local log (exit {result.returncode})")
        return log_path.read_text(encoding="utf-8", errors="replace").strip()

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        print(("PASS " if condition else "FAIL ") + name, flush=True)
        if not condition:
            raise AssertionError(name)

    sources = {name: getattr(args, name + "_source").resolve() for name in ("gateway", "record", "session", "dms")}
    for name, source in sources.items():
        if not (source / "Dockerfile").is_file():
            raise ValueError(f"Missing {name} source Dockerfile")
    tools_dockerfile = Path(__file__).resolve().parents[1] / "docker/gateway-baseline-tools.Dockerfile"
    run(["docker", "build", "-f", str(tools_dockerfile), "-t", "pad-gateway-membership-tests:local", str(sources["gateway"])], name="test-tool-image")

    # Only the test signer sees a private key, which is discarded with this container.
    signer = '''
import base64,json,time
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
now=int(time.time())
players=["11111111-1111-1111-1111-111111111111","22222222-2222-2222-2222-222222222222","33333333-3333-3333-3333-333333333333","44444444-4444-4444-4444-444444444444"]
tokens={p:jwt.encode({"iss":"student-id-player-service","aud":"student-id-api","sub":p,"iat":now,"exp":now+3600,"token_use":"access"},key,algorithm="RS256") for p in players}
print(json.dumps({"public":base64.b64encode(public).decode(),"tokens":tokens}))
'''
    # The tool image contains the Gateway's pinned Python dependencies.
    signed = subprocess.run(["docker", "run", "--rm", "pad-gateway-membership-tests:local", "python", "-c", signer],
                            capture_output=True, text=True, timeout=60, check=True)
    identity = json.loads(signed.stdout)
    record_token, dms_token, target_token = (secrets.token_urlsafe(40) for _ in range(3))
    password = secrets.token_hex(24)
    environment = {
        "PG_PASSWORD": password,
        "SESSION_DB_URL": f"postgres://baseline:{password}@session-db:5432/session_grade8_test?sslmode=disable",
        "RECORD_DB_URL": f"postgres://baseline:{password}@record-db:5432/record_grade8_test?sslmode=disable",
        "GATEWAY_JWT_PUBLIC_KEY_B64": identity["public"],
        "GATEWAY_SERVICE_TOKENS_JSON": json.dumps({"university-record-service": record_token, "discord-dms-service": dms_token}, separators=(",", ":")),
        "SESSION_INTERNAL_TOKEN": target_token,
        "RECORD_GATEWAY_TOKEN": record_token,
        "DMS_GATEWAY_TOKEN": dms_token,
    }
    # These are ignored, disposable local credentials; never write them into result/log files.
    env_path = output / "candidate.env"
    env_path.write_text("".join(f"{k}='{v}'\n" for k, v in environment.items()), encoding="utf-8")
    def database(name, network):
        return {"image": "postgres:16-alpine", "environment": {
            "POSTGRES_USER": "baseline", "POSTGRES_PASSWORD": "${PG_PASSWORD}", "POSTGRES_DB": name,
        }, "networks": [network], "healthcheck": {
            "test": ["CMD", "pg_isready", "-U", "baseline", "-d", name], "interval": "2s", "timeout": "2s", "retries": 30,
        }}

    def built(name, network, env):
        return {"build": {"context": str(sources[name])}, "image": f"{project}-{name}:candidate", "networks": [network], "environment": env}

    session_env = {"SESSION_DB_URL": "${SESSION_DB_URL}", "SESSION_INTERNAL_TOKEN": "${SESSION_INTERNAL_TOKEN}", "DISCOVERY_URL": ""}
    config = {"services": {
        "session-db": database("session_grade8_test", "session-net"),
        "record-db": database("record_grade8_test", "record-net"),
        "session": built("session", "session-net", session_env),
        "session-2": {"image": f"{project}-session:candidate", "networks": ["session-net"], "environment": session_env},
        "record": built("record", "record-net", {"DB_URL": "${RECORD_DB_URL}", "SESSION_CLIENT": "gateway", "GATEWAY_URL": "http://gateway:8080", "GATEWAY_SERVICE_TOKEN": "${RECORD_GATEWAY_TOKEN}", "DISCOVERY_URL": ""}),
        "dms": built("dms", "dms-net", {"STORE": "memory", "SESSION_CLIENT": "gateway", "GATEWAY_URL": "http://gateway:8080", "GATEWAY_SERVICE_TOKEN": "${DMS_GATEWAY_TOKEN}", "DISCOVERY_URL": ""}),
        "gateway": {**built("gateway", "session-net", {
            "SESSION_SERVICE_URL": "http://session:8080", "RECORD_SERVICE_URL": "http://record:8081", "DMS_SERVICE_URL": "http://dms:8080",
            "GATEWAY_JWT_PUBLIC_KEY_B64": "${GATEWAY_JWT_PUBLIC_KEY_B64}", "GATEWAY_SERVICE_TOKENS_JSON": "${GATEWAY_SERVICE_TOKENS_JSON}", "SESSION_INTERNAL_TOKEN": "${SESSION_INTERNAL_TOKEN}", "GATEWAY_MAX_CONCURRENT_TASKS": "1", "DISCOVERY_URL": "",
        }), "networks": ["session-net", "record-net", "dms-net"], "ports": ["127.0.0.1::8080"]},
    }, "networks": {"session-net": {}, "record-net": {}, "dms-net": {}}}
    config_path = output / "compose.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    compose = ["docker", "compose", "--project-name", project, "--env-file", str(env_path), "-f", str(config_path)]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = None

    def http(method, path, player=None, body=None, extra=None, trace=None):
        headers = {"X-Trace-Id": trace or "baseline-" + uuid.uuid4().hex}
        if player:
            headers["Authorization"] = "Bearer " + identity["tokens"][player]
        headers.update(extra or {})
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(base + path, data=raw, method=method, headers=headers)
        try:
            response = opener.open(request, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            data = response.read()
            decoded = json.loads(data) if data and response.headers.get("Content-Type", "").startswith("application/json") else None
            probes.append({"method": method, "path": path.split("?")[0], "status": response.status,
                           "errorCode": decoded.get("error", {}).get("code") if isinstance(decoded, dict) else None,
                           "traceId": response.headers.get("X-Trace-Id")})
            return response.status, decoded, response.headers.get("X-Trace-Id")

    def ready(path, player=None, extra=None, timeout=100):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if http("GET", path, player, extra=extra)[0] == 200:
                    return True
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError(f"Readiness failed for {path}")

    try:
        print(f"Building isolated project {project}", flush=True)
        run(compose + ["build", "gateway", "record", "session", "dms"], timeout=900, name="build")
        run(compose + ["up", "-d", "--wait", "session-db", "record-db"], name="databases")
        run(compose + ["up", "-d", "session", "record", "dms", "gateway"], name="services")
        base = "http://" + run(compose + ["port", "gateway", "8080"], name="gateway-port")
        for path in ("/health", "/api/v1/health/session-service", "/api/v1/health/university-record-service", "/api/v1/health/discord-dms-service"):
            ready(path)
        run(compose + ["up", "-d", "session-2"], name="second-session-replica")
        check("status endpoint available on the candidate Gateway", http("GET", "/status")[0] == 200)
        check("missing player JWT rejected", http("GET", "/api/v1/records/enrollment?studentId=baseline")[0] == 401)
        check("player JWT cannot invoke service membership", http("POST", MEMBERSHIP, JUNIOR, {"sessionId": str(uuid.uuid4()), "playerId": JUNIOR})[0] == 401)
        status, current, _ = http("POST", "/api/v1/sessions", HOST, {"teamId": str(uuid.uuid4()), "hostPlayerId": HOST, "difficulty": "NORMAL"})
        check("create real persisted session", status == 201)
        sid = current["sessionId"]
        for player in (JUNIOR, DENIED):
            check("join player " + player[:8], http("POST", f"/api/v1/sessions/{sid}/join", player, {"playerId": player})[0] == 200)
        roles = {"assignments": [{"playerId": HOST, "role": "MODERATOR"}, {"playerId": JUNIOR, "role": "JUNIOR_MODERATOR"}, {"playerId": DENIED, "role": "JUNIOR_MODERATOR"}]}
        check("assign roles using actual Session storage", http("POST", f"/api/v1/sessions/{sid}/roles", HOST, roles)[0] == 200)
        enrollment = "/api/v1/records/enrollment?studentId=BASELINE-" + project[-10:]
        session_header = {"X-Session-Id": sid}
        check("role alone grants no enrollment permission", http("GET", enrollment, JUNIOR, extra=session_header)[0] == 403)
        access = {"assignments": [{"playerId": JUNIOR, "recordAccess": ["ENROLLMENT_LIST"], "channels": ["#enrollment-check"]}]}
        check("non-host cannot grant permissions even with a forged player header", http("PUT", f"/api/v1/sessions/{sid}/access", JUNIOR, access, {"X-Player-Id": HOST})[0] == 403)
        check("host persists explicit record/channel access", http("PUT", f"/api/v1/sessions/{sid}/access", HOST, access)[0] == 204)
        record = {"studentId": "BASELINE-" + project[-10:], "name": "Baseline Test", "major": "FAF", "enrolledSince": "2025-09-01", "status": "ENROLLED", "outlookGroups": [], "courses": [], "fcimMessages": []}
        check("create real Record row through Gateway", http("POST", "/api/v1/university-records", HOST, record)[0] == 201)
        trace = "baseline-record-allowed"
        status, body, returned = http("GET", enrollment, JUNIOR, extra=session_header, trace=trace)
        check("Record -> Gateway -> Session allows persisted enrollment assignment", status == 200 and body.get("found") is True and returned == trace)
        check("unassigned junior denied despite spoofing allowed player", http("GET", enrollment, DENIED, extra={**session_header, "X-Player-Id": JUNIOR})[0] == 403)
        check("unknown session denied", http("GET", enrollment, JUNIOR, extra={"X-Session-Id": str(uuid.uuid4())})[0] == 403)
        check("unknown player denied", http("GET", enrollment, OUTSIDER, extra=session_header)[0] == 403)
        check("DMs -> Gateway -> Session verifies actual member", http("GET", f"/api/v1/channels?sessionId={sid}", JUNIOR, trace="baseline-dms-allowed")[0] == 200)
        check("DMs denies unknown member", http("GET", f"/api/v1/channels?sessionId={sid}", OUTSIDER)[0] == 403)
        run(compose + ["restart", "session"], name="restart-session")
        ready("/api/v1/health/session-service")
        check("permissions survive Session process restart", http("GET", enrollment, JUNIOR, extra=session_header)[0] == 200)
        # Verify the same persisted permission from a second real Session process.
        replica_probe = "import os,json,urllib.request; r=urllib.request.Request('http://session-2:8080" + MEMBERSHIP + "',data=json.dumps({'sessionId':'" + sid + "','playerId':'" + JUNIOR + "'}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['SESSION_INTERNAL_TOKEN']}); print(json.load(urllib.request.urlopen(r))['recordAccess']==['ENROLLMENT_LIST'])"
        check("permission visible to second Session replica", run(compose + ["exec", "-T", "gateway", "python", "-c", replica_probe], name="replica-membership") == "True")
        run(compose + ["stop", "session"], name="stop-session")
        check("Record fails closed when Session is unavailable", http("GET", enrollment, JUNIOR, extra=session_header)[0] == 503)
        check("DMs fails closed when Session is unavailable", http("GET", f"/api/v1/channels?sessionId={sid}", JUNIOR)[0] == 503)
        run(compose + ["start", "session"], name="recover-session")
        ready("/api/v1/health/session-service")
        # Readiness and a prior response may still be releasing a task slot.
        # Observe bounded recovery with idempotent test GETs; business clients
        # themselves still make exactly one membership request and never retry.
        check("enrollment recovers after Session returns", ready(enrollment, JUNIOR, session_header, timeout=10))
        check("host starts session", http("POST", f"/api/v1/sessions/{sid}/start", HOST)[0] == 200)
        check("access cannot change during active shift", http("PUT", f"/api/v1/sessions/{sid}/access", HOST, access)[0] == 409)
        check("end session", http("POST", f"/api/v1/sessions/{sid}/end", HOST)[0] == 200)
        check("completed session revokes enrollment access", http("GET", enrollment, JUNIOR, extra=session_header)[0] == 403)
        logs = run(compose + ["logs", "--no-color", "gateway", "record", "session", "dms"], name="candidate-service-logs")
        if any(secret in logs for secret in [record_token, dms_token, target_token, password, *identity["tokens"].values()]):
            raise AssertionError("Credentials found in candidate logs")
        trace_lines = [line for line in logs.splitlines() if "baseline-record-allowed" in line or "baseline-dms-allowed" in line]
        (output / "correlated-traces.log").write_text("\n".join(trace_lines) + "\n", encoding="utf-8")
        check("one trace correlates Record, Gateway and Session", all(any(name in line and "baseline-record-allowed" in line for line in trace_lines) for name in ["university-record-service", "gateway-service", "session-service"]))
        check("one trace correlates DMs, Gateway and Session", all(any(name in line and "baseline-dms-allowed" in line for line in trace_lines) for name in ["discord-dms-service", "gateway-service", "session-service"]))
    finally:
        (output / "http-probes.json").write_text(json.dumps(probes, indent=2) + "\n", encoding="utf-8")
        run(compose + ["logs", "--no-color", "gateway", "record", "session", "dms"], name="final-service-logs")
        (output / "results.json").write_text(json.dumps({"project": project, "baseUrl": base, "checks": checks,
            "scope": "Record/DMs membership through Gateway; other game integrations remain mocks; local candidate only",
            "playerAuthentication": "isolated test-signed RS256 JWTs; Player login remains unimplemented"}, indent=2) + "\n", encoding="utf-8")
        if not args.keep_running:
            # The project is generated by this run, never a caller-supplied shared stack.
            assert re.fullmatch(r"pad-membership-[0-9a-f]{10}", project)
            run(compose + ["down", "--volumes", "--remove-orphans"], name="cleanup")
    print(f"Verified {len(checks)} checks; reports: {output}", flush=True)


if __name__ == "__main__":
    main()
