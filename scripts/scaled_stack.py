"""Controlled Grade 5 startup/add/remove. No implicit image builds or volume deletion."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("player-service", "session-service", "credential-service", "rules-service",
            "applicant-service", "university-record-service", "moderation-service", "discord-dms-service")


class Stack:
    def __init__(self, env_file, project=None):
        self.prefix = ["docker", "compose"]
        if project:
            self.prefix.extend(["--project-name", project])
        self.prefix.extend(["--env-file", str(Path(env_file).resolve()), "-f", str(ROOT / "docker-compose.yml")])

    def compose(self, *arguments, data=None, replicas=False):
        command = self.prefix + (["--profile", "replicas"] if replicas else []) + list(arguments)
        result = subprocess.run(command, input=data, text=True, capture_output=True, timeout=600)
        if result.returncode:
            raise RuntimeError("Compose operation failed; check image configuration and service logs")
        return result.stdout

    def config(self):
        return json.loads(self.compose("config", "--format", "json", replicas=True))["services"]

    def registry(self, *arguments, data=None):
        return self.compose("exec", "-T", "service-discovery", "python", "/integration/registry_control.py",
                            *arguments, data=data)

    def expected(self, names):
        config = self.config()
        return [{"serviceName": name.removesuffix("-2"),
                 "baseUrl": config[name]["environment"]["SERVICE_ADVERTISE_URL"].rstrip("/")} for name in names]

    def wait(self, names):
        self.registry("wait", data=json.dumps(self.expected(names)))

    def up(self):
        print("Starting first replicas and waiting for registration/database readiness...", flush=True)
        self.compose("up", "-d")
        self.wait(list(SERVICES))
        print("Primary schema initialization finished; starting second replicas...", flush=True)
        self.compose("up", "-d", replicas=True)
        self.wait([service + suffix for service in SERVICES for suffix in ("", "-2")])
        print("Both registered replica sets report readiness UP.", flush=True)

    def check_instance(self, name):
        if name not in {service + suffix for service in SERVICES for suffix in ("", "-2")}:
            raise ValueError("Select a declared backend replica, not infrastructure")

    def add(self, name):
        self.check_instance(name)
        if name.endswith("-2"):
            self.wait([name.removesuffix("-2")]) # Don't race cold-start schema initialization.
        self.compose("up", "-d", name, replicas=True)
        self.wait([name])

    def deregister(self, name):
        expected = self.expected([name])[0]
        entries = json.loads(self.registry("list"))["instances"]
        for item in entries:
            if item["serviceName"] == expected["serviceName"] and item["baseUrl"] == expected["baseUrl"]:
                self.registry("remove", item["serviceName"], item["instanceId"])

    def remove(self, name):
        self.check_instance(name)
        self.deregister(name)
        self.compose("stop", "--timeout", "5", name, replicas=True)
        # Clean up a registration that raced with the first DELETE during startup.
        self.deregister(name)
        print(f"Removed {name}; new registry lookups no longer select it.", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("up", "add", "remove", "status"))
    parser.add_argument("instance", nargs="?")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--project-name", help="Override Compose's normal project name, e.g. for an isolated check")
    args = parser.parse_args()
    stack = Stack(args.env_file, args.project_name)
    try:
        if args.command == "up": stack.up()
        elif args.command == "status": print(stack.registry("list"))
        elif args.command == "add": stack.add(args.instance)
        else: stack.remove(args.instance)
    except (RuntimeError, ValueError, KeyError, subprocess.SubprocessError, OSError):
        print("Scaled operation failed. Check selected images, registration and readiness; no volumes were deleted.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
