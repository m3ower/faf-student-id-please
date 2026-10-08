"""Verify the two owned task limits through Gateway using temporary database locks."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
OWNED = [
    ("applicant-service", "applicant-db", "applicant_user", "applicant_db", "applicants"),
    ("university-record-service", "university-record-db", "record_user", "record_db", "university_records"),
]


def command(parts):
    return subprocess.check_output(parts, cwd=ROOT, text=True, encoding="utf-8", timeout=10).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    compose = ["docker", "compose", "-p", args.project]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checks = []

    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
        print(("PASS " if passed else "FAIL ") + name, flush=True)

    def request(path, method="GET", payload=None):
        req = urllib.request.Request(args.base_url.rstrip("/") + path, method=method,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Id": "grade8-session", "X-Player-Id": "grade8-player"})
        begin = time.monotonic()
        try:
            response = opener.open(req, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            content = response.read()
            return {"status": response.status, "body": json.loads(content) if content else None,
                    "retry_after": response.headers.get("Retry-After"), "seconds": time.monotonic() - begin}

    def task_error(response, service, status, code):
        body = response.get("body")
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return response["status"] == status and error.get("code") == code and error.get("service") == service

    gateway_before = command(compose + ["ps", "-q", "gateway-service"])
    for service, database_service, user, database, table in OWNED:
        container = command(compose + ["ps", "-q", service])
        database_id = command(compose + ["ps", "-q", database_service])
        if not container or not database_id:
            raise RuntimeError("Owned verification containers are not running")
        # Inspect configuration in memory; never print credentials from container env.
        values = dict(item.split("=", 1) for item in json.loads(command(
            ["docker", "inspect", container, "--format", "{{json .Config.Env}}"])))
        limit = int(values.get("MAX_CONCURRENT_TASKS", "16"))
        timeout_ms = int(values.get("TASK_TIMEOUT_MS", "2000"))
        if not 1 <= limit <= 4 or not 100 <= timeout_ms <= 3000:
            raise RuntimeError("Use a focused test deployment with 1..4 slots and a 100..3000 ms deadline")
        prefix = "/api/v1/applicants" if service == "applicant-service" else "/api/v1/university-records"
        health = "/api/v1/health/" + service
        check(service + " is healthy before fault injection", request(health)["status"] == 200)
        psql = ["docker", "exec", database_id, "psql", "-U", user, "-d", database, "-tAc"]

        def query(sql):
            return command(psql + [sql])

        def wait_for(sql, predicate, seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                if predicate(int(query(sql))):
                    return True
                time.sleep(0.02)
            return False

        hold_seconds = timeout_ms / 1000 * 3 + 1
        lock = subprocess.Popen(["docker", "exec", "--env", "PGAPPNAME=codex_grade8_probe", database_id,
            "psql", "-U", user, "-d", database, "-c",
            f"BEGIN; LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep({hold_seconds}); COMMIT;"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        waiting_sql = "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
        ready_sql = f"SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON l.pid = a.pid JOIN pg_class r ON l.relation = r.oid WHERE a.datname = current_database() AND a.application_name = 'codex_grade8_probe' AND r.relname = '{table}' AND l.mode = 'AccessExclusiveLock' AND l.granted"
        try:
            if not wait_for(ready_sql, lambda n: n == 1, 2):
                raise RuntimeError("Could not acquire the temporary owned database lock")
            with ThreadPoolExecutor(max_workers=limit) as executor:
                pending = [executor.submit(request, prefix if i == 0 else prefix + "/" + str(uuid.uuid4()))
                           for i in range(limit)]
                if not wait_for(waiting_sql, lambda n: n >= limit, timeout_ms / 1000 * 0.8):
                    raise RuntimeError("The intended number of owned tasks was not admitted")
                excess_path = prefix if service == "applicant-service" else "/api/v1/records/enrollment?studentId=grade8-missing"
                excess = request(excess_path)
                check(service + " rejects excess work across business routes", task_error(excess, service, 429, "CONCURRENT_TASK_LIMIT"))
                check(service + " overload includes Retry-After", excess["retry_after"] == "1")
                check(service + " health stays available while saturated", request(health)["status"] == 200)
                results = [future.result() for future in pending]
                check(service + " admitted work returns TASK_TIMEOUT", all(task_error(r, service, 504, "TASK_TIMEOUT") for r in results))
                check(service + " responses respect the deadline", all(r["seconds"] < timeout_ms / 1000 + 1 for r in results))
            check(service + " timed-out database reads stop waiting", wait_for(waiting_sql, lambda n: n == 0, 1))
            student = "grade8-probe-" + str(uuid.uuid4())
            payload = {"studentId": student, "name": "Grade 8 Probe", "major": "FAF", "courses": ["PAD"]}
            if service == "applicant-service":
                payload.update(studyYear=2, universityStatus="ENROLLED", role="STUDENT")
            else:
                payload.update(enrolledSince="2025-09-01", status="ACTIVE", outlookGroups=[], fcimMessages=[])
            mutation = request(prefix, "POST", payload)
            check(service + " blocked mutation returns TASK_TIMEOUT", task_error(mutation, service, 504, "TASK_TIMEOUT"))
            check(service + " timed-out database mutation stops waiting", wait_for(waiting_sql, lambda n: n == 0, 1))
        finally:
            lock.communicate(timeout=hold_seconds + 5)
        recovered = request(prefix)
        check(service + " capacity recovers after the fault", recovered["status"] == 200)
        unexpected = [row for row in (recovered["body"] or []) if row.get("studentId") == student]
        check(service + " timed-out blocked mutation was not committed later", not unexpected)
        for row in unexpected:
            request(prefix + "/" + row["id"], "DELETE")

    check("Gateway container was not replaced", gateway_before == command(compose + ["ps", "-q", "gateway-service"]))
    report = ROOT / "docs-local" / "owned-grade8-verification.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return 0 if all(item["passed"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
