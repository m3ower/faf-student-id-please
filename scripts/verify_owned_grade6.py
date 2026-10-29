"""Verify only Applicant/Record REST routing and their network isolation."""

import argparse
import json
from pathlib import Path
import subprocess
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OWNED = ["applicant-service", "university-record-service"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="pad-lab2")
    parser.add_argument("--base-url", default="http://localhost:8090")
    args = parser.parse_args()
    checks = []

    def command(parts):
        return subprocess.run(parts, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)

    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
        print(("PASS " if passed else "FAIL ") + name, flush=True)

    compose = ["docker", "compose", "-p", args.project]
    result = command(compose + ["config", "--format", "json"])
    result.check_returncode()
    services = json.loads(result.stdout)["services"]
    for name in OWNED:
        service = services[name]
        check(name + " has no published HTTP port", not service.get("ports"))
        check(name + " REST destinations use Gateway", all(
            service["environment"].get(key) == "http://gateway-service:8080"
            for key in ["GATEWAY_URL", "APPLICANT_SERVICE_URL", "RECORD_SERVICE_URL"]
        ))
    networks = [set(services[name]["networks"]) for name in OWNED]
    check("Owned services have separate networks", not networks[0].intersection(networks[1]))
    check("Gateway joins both owned networks", all(
        network.issubset(services["gateway-service"]["networks"]) for network in networks
    ))
    check("Gateway routes to the owned containers", all(
        services["gateway-service"]["environment"].get(key) == origin for key, origin in {
            "APPLICANT_SERVICE_URL": "http://applicant-service:8080",
            "RECORD_SERVICE_URL": "http://university-record-service:8081",
        }.items()
    ))

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name in OWNED:
        try:
            with opener.open(args.base_url.rstrip("/") + "/api/v1/health/" + name, timeout=10) as response:
                check(name + " readiness through Gateway", response.status == 200)
        except Exception:
            check(name + " readiness through Gateway", False)

    result = command(compose + ["ps", "-q", "applicant-service"])
    result.check_returncode()
    container_id = result.stdout.strip()
    if not container_id:
        raise RuntimeError("Applicant service is not running")
    probe = ["docker", "run", "--rm", "--network", "container:" + container_id,
             "busybox:1.37", "wget", "-T", "3", "-qO-"]
    indirect = command(probe + ["http://gateway-service:8080/api/v1/university-records"])
    reachable = indirect.returncode == 0
    check("Applicant network -> Gateway -> Record succeeds", reachable)
    direct = command(probe + ["http://university-record-service:8081/api/v1/university-records"])
    check("Direct Applicant -> Record bypass is blocked", reachable and direct.returncode != 0)

    report = ROOT / "docs-local" / "owned-grade6-verification.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return 0 if all(item["passed"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
