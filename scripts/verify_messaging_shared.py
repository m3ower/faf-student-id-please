"""Isolated real-HTTP check of shared messaging, using explicit business receivers.

Run with the Gateway development Python (its dependencies include httpx/jwt):
python scripts/verify_messaging_shared.py --services-root /path/to/CPR/services

Starts only new loopback processes/ports, no Docker stack or databases. Receivers
are test fixtures, not the actual Player/Session/DMs implementations. All secrets
and the RSA private key are generated in memory; output contains only assertions
and sanitized trace metadata. Temporary process logs are deleted on exit.
"""

import argparse
import base64
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PLAYER = "11111111-1111-1111-1111-111111111111"
SESSION = "55555555-5555-5555-5555-555555555555"
ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def envelope(topic, payload, kind="request"):
    return {"messageId": str(uuid4()), "schemaVersion": 1, "kind": kind, "topic": topic,
            "traceId": "shared.messaging.network", "correlationId": str(uuid4()),
            "deadlineAt": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(), "payload": payload}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services-root", type=Path, default=ROOT / "services")
    parser.add_argument("--output", type=Path, default=ROOT / "docs-local/messaging-evidence.json")
    args = parser.parse_args()
    source = args.services_root.resolve()
    checks, seen, processes, receivers = [], [], {}, []
    clients = httpx.Client(trust_env=False, timeout=10)
    subscriptions = json.loads((ROOT / "contracts/messaging/subscriptions.json").read_text(encoding="utf-8"))
    callers = {name: secrets.token_urlsafe(32) for name in ["gateway-service", "moderation-service", "session-service"]}
    target_tokens = {name: secrets.token_urlsafe(32) for name in ["session-service", "discord-dms-service", "player-service"]}
    discovery_token = secrets.token_urlsafe(32)
    discovery_url, broker_url, gateway_url = ["http://127.0.0.1:" + str(free_port()) for _ in range(3)]
    registry_headers = {"Authorization": "Bearer " + discovery_token}
    modes = {"ready": True, "refuse_dms": False}

    def check(name, valid):
        checks.append({"check": name, "passed": bool(valid)})
        print(("PASS " if valid else "FAIL ") + name, flush=True)
        if not valid:
            raise AssertionError(name)

    def wait_for(predicate, seconds=15):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            try:
                if predicate():
                    return
            except (httpx.HTTPError, KeyError, ValueError):
                pass
            time.sleep(0.05)
        raise TimeoutError("Isolated shared messaging did not become ready")

    def post(message, caller="moderation-service"):
        return clients.post(broker_url + "/internal/v1/messaging/publications", json=message,
            headers={"Authorization": "Bearer " + callers[caller], "X-Trace-Id": message["traceId"]})

    def poll(message, caller="moderation-service"):
        reply = None
        def terminal():
            nonlocal reply
            reply = clients.get(broker_url + "/internal/v1/messaging/results/" + message["messageId"],
                headers={"Authorization": "Bearer " + callers[caller]})
            return reply.status_code != 202
        wait_for(terminal, 3)
        return reply

    def fixture(service, number):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, body):
                wire = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(wire)))
                self.end_headers()
                self.wfile.write(wire)

            def do_GET(self):
                if self.path == "/health/ready":
                    up = modes["ready"]
                    return self.reply(200 if up else 503, {"status": "UP" if up else "DOWN", "service": service})
                if self.path == "/status":
                    return self.reply(200, {"status": "UP", "service": service, "checks": []})
                return self.business()

            def do_POST(self):
                return self.business()

            def business(self):
                if self.headers.get("Authorization") != "Bearer " + target_tokens[service]:
                    return self.reply(401, {"error": {"code": "BAD_TARGET_CREDENTIAL"}})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                trace = self.headers.get("X-Trace-Id")
                seen.append({"service": service, "replica": number, "path": self.path,
                             "traceId": trace, "caller": self.headers.get("X-Service-Name"),
                             "messageId": self.headers.get("X-Message-Id"),
                             "deadlinePresent": bool(self.headers.get("X-Deadline-At"))})
                if self.path.endswith("/events"):
                    self.send_response(200)
                    self.send_header("cOnTeNt-TyPe", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        self.wfile.write(b"event: READY\ndata: {}\n\n"); self.wfile.flush()
                        time.sleep(6)
                        self.wfile.write(b"event: LATE\ndata: {}\n\n"); self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                if self.path.startswith("/api/v1/sessions"):
                    child = envelope("operation.players.verify.v1", {"playerId": PLAYER})
                    child["traceId"] = trace
                    # Preserve the parent's actual remaining budget.
                    child["deadlineAt"] = min(child["deadlineAt"], self.headers["X-Deadline-At"])
                    with httpx.Client(trust_env=False, timeout=1) as client:
                        result = client.post(broker_url + "/internal/v1/messaging/publications", json=child,
                            headers={"Authorization": "Bearer " + callers["session-service"], "X-Trace-Id": trace})
                    values = result.json()
                    ok = values.get("state") == "COMPLETED"
                    return self.reply(200 if ok else 502, {"nestedPlayerVerified": ok, "replica": number})
                if service == "discord-dms-service" and modes["refuse_dms"]:
                    return self.reply(409, {"error": {"code": "SESSION_CHAT_NOT_INITIALIZED"}})
                if "eventId" in body:
                    return self.reply(200, {"eventId": body["eventId"], "status": "PROCESSED"})
                return self.reply(200, {"member": True, "replica": number})
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        receivers.append(server)
        return {"serviceName": service, "instanceId": str(uuid4()), "baseUrl": "http://127.0.0.1:" + str(server.server_port),
                "readinessPath": "/health/ready", "subscriptions": subscriptions[service]}

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.PEM,
                             serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    now = int(time.time())
    access = jwt.encode({"iss": "student-id-player-service", "aud": "student-id-api", "sub": PLAYER,
                         "iat": now, "exp": now + 300, "token_use": "access"}, key, algorithm="RS256")
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("BROKER_", "DISCOVERY_", "DMS_", "GATEWAY_", "SERVICE_")) or name.endswith("_INTERNAL_TOKEN"):
            env.pop(name)
    env.update({"LOG_LEVEL": "INFO", "PYTHONUNBUFFERED": "1"})
    discovery_env = {**env, "DISCOVERY_REGISTRATION_TOKEN": discovery_token,
                     "DISCOVERY_POLL_INTERVAL_SECONDS": "0.3", "DISCOVERY_POLL_TIMEOUT_SECONDS": "0.2"}
    broker_env = {**env, "DISCOVERY_URL": discovery_url, "DISCOVERY_REGISTRATION_TOKEN": discovery_token,
                  "BROKER_CALLER_TOKENS_JSON": json.dumps(callers), "SESSION_INTERNAL_TOKEN": target_tokens["session-service"],
                  "DMS_INTERNAL_TOKEN": target_tokens["discord-dms-service"], "PLAYER_INTERNAL_TOKEN": target_tokens["player-service"]}
    gateway_env = {**env, "BROKER_URL": broker_url, "BROKER_SERVICE_TOKEN": callers["gateway-service"],
                   "GATEWAY_JWT_PUBLIC_KEY_B64": public}
    with tempfile.TemporaryDirectory(prefix="pad-messaging-") as temporary:
        streams = []
        def stop(name):
            process = processes.pop(name, None)
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
        def start(name, url, environment):
            log = (Path(temporary) / (name + "-" + uuid4().hex + ".log")).open("w", encoding="utf-8")
            streams.append(log)
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                "--port", url.rsplit(":", 1)[1], "--workers", "1", "--no-access-log", "--no-proxy-headers"],
                cwd=source / name, env=environment, stdout=log, stderr=subprocess.STDOUT)
            processes[name] = process
            wait_for(lambda: clients.get(url + "/health" if name == "gateway-service" else url + "/health/ready").status_code == 200)
        try:
            start("service-discovery", discovery_url, discovery_env)
            entries = [fixture(service, n) for service, numbers in [("session-service", [1, 2]),
                       ("discord-dms-service", [1, 2]), ("player-service", [1])] for n in numbers]
            for entry in entries:
                response = clients.post(discovery_url + "/internal/v1/instances", json=entry, headers=registry_headers)
                check("register " + entry["serviceName"] + " " + entry["instanceId"][:8], response.status_code == 201)
            def ready():
                values = clients.get(discovery_url + "/internal/v1/instances", headers=registry_headers).json()["instances"]
                return len(values) == 5 and all(v["readiness"]["ready"] for v in values)
            wait_for(ready)
            check("Discovery observes fresh readiness independently", ready())
            start("message-broker", broker_url, broker_env)
            start("gateway-service", gateway_url, gateway_env)
            headers = {"Authorization": "Bearer " + access, "X-Trace-Id": "shared.messaging.network"}
            responses = [clients.get(gateway_url + "/api/v1/sessions", headers=headers) for _ in range(2)]
            check("Gateway unwraps real queued HTTP and nested operation reply", all(r.status_code == 200 and r.json()["nestedPlayerVerified"] for r in responses))
            check("two replicas compete within public subscriber queue", {r.json()["replica"] for r in responses} == {1, 2})
            check("trusted identity trace and transport IDs reach nested receivers", all(s["traceId"] == headers["X-Trace-Id"] and s["deadlinePresent"] and s["messageId"] for s in seen))
            event = {"eventId": str(uuid4()), "type": "DecisionRecorded", "occurredAt": datetime.now(timezone.utc).isoformat(),
                     "producer": "moderation-service", "version": 1, "payload": {"sessionId": SESSION}}
            message = envelope("event.DecisionRecorded.v1", event, "event")
            before = len(seen)
            check("event acceptance is pending202", post(message).status_code == 202)
            final = poll(message).json()
            check("independent event groups commit matching acknowledgments", final["state"] == "COMPLETED" and set(final["groups"]) == {"session-service", "discord-dms-service"})
            check("event has one delivery per group rather than replica", len(seen) - before == 2)
            check("same transport ID replays retained result", post(message).json() == final and len(seen) - before == 2)
            conflict = {**message, "correlationId": str(uuid4())}
            check("different content under same ID conflicts", post(conflict).status_code == 409)
            wrong = clients.get(broker_url + "/internal/v1/messaging/results/" + message["messageId"],
                headers={"Authorization": "Bearer " + callers["session-service"]})
            check("results are private to original caller", wrong.status_code == 404)
            modes["refuse_dms"] = True
            partial = envelope("event.DecisionRecorded.v1", {**event, "eventId": str(uuid4())}, "event")
            post(partial)
            final_partial = poll(partial).json()
            check("partial failure preserves acknowledged peer and DMs409", final_partial["state"] == "FAILED" and final_partial["groups"]["session-service"]["acknowledged"] and final_partial["groups"]["discord-dms-service"]["status"] == 409)
            modes["refuse_dms"] = False
            began = time.monotonic()
            with clients.stream("GET", gateway_url + "/api/v1/sessions/" + SESSION + "/events", headers=headers) as stream:
                late = any(line == "event: LATE" for line in stream.iter_lines())
            check("mixed-case SSE survives ordinary five-second deadline", late and time.monotonic() - began >= 6)
            modes["ready"] = False
            wait_for(lambda: not any(v["readiness"]["ready"] for v in clients.get(discovery_url + "/internal/v1/instances", headers=registry_headers).json()["instances"]))
            check("unready subscribers fail closed before delivery", post(envelope("operation.session.verifyMembership.v1", {"sessionId": SESSION, "playerId": PLAYER})).status_code == 503)
            modes["ready"] = True
            wait_for(ready)
            stop("message-broker")
            start("message-broker", broker_url, broker_env)
            check("Broker restart loses result; no durability claim", poll(message).status_code == 404)
            check("new request works after Broker restart", clients.get(gateway_url + "/api/v1/sessions", headers=headers).status_code == 200)
        finally:
            for name in list(processes):
                stop(name)
            for server in receivers:
                server.shutdown(); server.server_close()
            clients.close()
            for stream in streams:
                stream.close()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"scope": "real shared processes with explicit business test receivers",
                "checks": checks, "receivingTraceEvidence": seen}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
