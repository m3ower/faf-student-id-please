"""Run only Andrei's Applicant and University Record Postman collections."""

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="pad-lab2")
    args = parser.parse_args()
    directory = ROOT / "docs-local" / "postman-owned"
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for service in ["applicant", "university-record"]:
        report = directory / (service + ".json")
        report.unlink(missing_ok=True)
        result = subprocess.run([
            "docker", "run", "--rm", "--network", args.project + "_default",
            "--mount", "type=bind,source=" + str(ROOT) + ",target=/workspace",
            "-w", "/workspace", "postman/newman:alpine", "run",
            "postman/" + service + "-service.postman_collection.json",
            "--env-var", "baseUrl=http://gateway-service:8080", "--reporters", "cli,json",
            "--reporter-json-export", "/workspace/docs-local/postman-owned/" + service + ".json",
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        (directory / (service + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        summary = {"service": service, "exit_code": result.returncode}
        if report.exists():
            run = json.loads(report.read_text(encoding="utf-8"))["run"]
            summary.update(stats=run["stats"], failures=[{
                "source": failure.get("source", {}).get("name"),
                "error": failure.get("error", {}).get("message"),
            } for failure in run.get("failures", [])])
        results.append(summary)
        print(json.dumps(summary), flush=True)
    (directory / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 1 if any(result["exit_code"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
