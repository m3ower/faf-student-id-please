"""Run INSIDE Discovery: inspect readiness or deregister without exposing its token."""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from uuid import UUID


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def registry_request(method="GET", suffix=""):
    token = os.getenv("DISCOVERY_REGISTRATION_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
        raise ValueError("Registry machine credential is not configured")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request("http://127.0.0.1:8089/internal/v1/instances" + suffix,
                                     headers={"Authorization": "Bearer " + token}, method=method)
    with opener.open(request, timeout=2) as response:
        if response.status == 204:
            return None
        data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Registry response too large")
        return json.loads(data)


def ready(expected, timeout):
    """One deployment readiness wait, NOT ongoing health polling or registry eviction."""
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    while time.monotonic() < deadline:
        try:
            entries = registry_request()["instances"]
            found = {(item["serviceName"], item["baseUrl"]): item for item in entries}
            if not all((item["serviceName"], item["baseUrl"]) in found for item in expected):
                raise ValueError("Instances have not registered")
            for item in expected:
                registration = found[(item["serviceName"], item["baseUrl"])]
                if registration["readinessPath"] != "/health/ready":
                    raise ValueError("Unexpected readiness path")
                with opener.open(item["baseUrl"] + "/health/ready", timeout=2) as response:
                    if response.status != 200:
                        raise ValueError("Instance is not ready")
            return
        except (OSError, ValueError, KeyError, TypeError):
            time.sleep(1)
    raise ValueError("Registration/readiness deadline exceeded")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "remove", "wait"))
    parser.add_argument("service", nargs="?")
    parser.add_argument("instance", nargs="?")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        if args.command == "list":
            print(json.dumps(registry_request()))
        elif args.command == "wait":
            ready(json.load(sys.stdin), args.timeout)
        else:
            if not args.service or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", args.service):
                raise ValueError("Invalid service name")
            identifier = str(UUID(args.instance))
            registry_request("DELETE", f"/{args.service}/{identifier}")
    except (OSError, ValueError, TypeError, KeyError):
        # No raw exception, request URL, token, body or Compose environment is printed.
        print("Registry operation failed; check registration/configuration and service logs.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
