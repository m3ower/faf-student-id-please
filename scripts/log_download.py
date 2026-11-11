"""Local operational HTTP endpoint for bounded Compose log snapshots (Lab 4 Task 4)."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SERVICE = "log-download-service"
MAX_BYTES = 5 * 1024 * 1024
NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,127}")
LOG_LOCK = threading.Lock()


class ExportError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class Options:
    service: str | None = None
    since: str = "15m"
    tail: int = 200

    @classmethod
    def parse(cls, query):
        try:
            fields = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
            if set(fields) - {"service", "since", "tail"} or any(len(v) != 1 for v in fields.values()):
                raise ValueError
            service = fields.get("service", [None])[0]
            since = fields.get("since", ["15m"])[0]
            tail_text = fields.get("tail", ["200"])[0]
            if service is not None and not NAME.fullmatch(service):
                raise ValueError
            if since not in {"5m", "15m", "1h", "24h"} or not re.fullmatch(r"[0-9]{1,4}", tail_text):
                raise ValueError
            tail = int(tail_text)
            if not 1 <= tail <= 1000:
                raise ValueError
            return cls(service, since, tail)
        except ValueError:
            raise ExportError(400, "INVALID_LOG_QUERY", "Use service, since=5m|15m|1h|24h and tail=1..1000") from None


def terminate(process):
    """Stop this command and its Compose-plugin descendants, not the containers."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)
            if process.poll() is None:
                process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()


def bounded_command(command, deadline, limit, *, include_stderr=False):
    """Bound bytes and elapsed time without buffering unlimited command output."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExportError(504, "LOG_EXPORT_TIMEOUT", "Log snapshot exceeded its deadline")
    environment = dict(os.environ)
    environment.pop("LOG_DOWNLOAD_TOKEN", None)
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT if include_stderr else subprocess.DEVNULL,
                                   env=environment, **flags)
    except OSError:
        raise ExportError(503, "LOG_SOURCE_UNAVAILABLE", "Docker Compose logs are unavailable") from None
    expired = threading.Event()

    def expire():
        expired.set()
        terminate(process)

    timer = threading.Timer(remaining, expire)
    timer.daemon = True
    timer.start()
    output = bytearray()
    try:
        while chunk := process.stdout.read1(min(65536, limit + 1 - len(output))):
            output.extend(chunk)
            if len(output) > limit:
                raise ExportError(413, "LOG_EXPORT_TOO_LARGE", "Use a smaller time window or tail count")
        result = process.wait()
        if expired.is_set():
            raise ExportError(504, "LOG_EXPORT_TIMEOUT", "Log snapshot exceeded its deadline")
        if result:
            raise ExportError(503, "LOG_SOURCE_UNAVAILABLE", "Docker Compose logs are unavailable")
        return bytes(output)
    finally:
        timer.cancel()
        terminate(process)
        process.wait()
        process.stdout.close()


class ComposeLogs:
    def __init__(self, compose_files, env_file, project, *, timeout=15, max_bytes=MAX_BYTES):
        self.prefix = ["docker", "compose", "--project-name", project,
                       "--env-file", str(Path(env_file).resolve()), "--profile", "*"]
        for filename in compose_files:
            self.prefix.extend(["--file", str(Path(filename).resolve())])
        self.project, self.timeout, self.max_bytes = project, timeout, max_bytes

    def snapshot(self, options):
        deadline = time.monotonic() + self.timeout
        catalog = bounded_command(self.prefix + ["config", "--services"], deadline, 65536)
        try:
            names = sorted(set(catalog.decode("utf-8").splitlines()))
        except UnicodeError:
            names = []
        if not names or len(names) > 128 or any(not NAME.fullmatch(name) for name in names):
            raise ExportError(503, "LOG_SOURCE_UNAVAILABLE", "Compose service configuration is unavailable")
        if options.service is not None:
            if options.service not in names:
                raise ExportError(400, "UNKNOWN_LOG_SERVICE", "Select a declared Compose service")
            pattern = re.compile(re.escape(options.service) + r"(?:-[0-9]+)?")
            names = [name for name in names if pattern.fullmatch(name)]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        header = (f"# Student ID system logs; exported at {stamp} (UTC)\n"
                  f"# project={self.project}; services={','.join(names)}\n"
                  f"# since={options.since}; tail={options.tail} per container\n").encode("utf-8")
        if len(header) >= self.max_bytes:
            raise ExportError(413, "LOG_EXPORT_TOO_LARGE", "Use a smaller time window or tail count")
        logs = bounded_command(self.prefix + ["logs", "--no-color", "--timestamps", "--since", options.since,
                                              "--tail", str(options.tail), *names],
                               deadline, self.max_bytes - len(header), include_stderr=True)
        return header + logs, f"student-id-logs-{stamp}.log"


def emit(event, **fields):
    with LOG_LOCK:
        print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "service": SERVICE,
                          "level": "INFO", "event": event, **fields}), flush=True)


class LogServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, collector, token, *, port=8092, max_downloads=2):
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
            raise ValueError("LOG_DOWNLOAD_TOKEN must be a URL-safe secret of 32-256 characters")
        self.collector, self.token = collector, token.encode("utf-8")
        self.slots = threading.BoundedSemaphore(max_downloads)
        super().__init__(("127.0.0.1", port), LogHandler)

    def handle_error(self, request, client_address):
        emit("error", code="HTTP_CONNECTION_ERROR")


class LogHandler(BaseHTTPRequestHandler):
    timeout = 5
    server_version = "StudentIDLogDownload"
    sys_version = ""

    def log_message(self, *args):
        pass  # Base access logs contain raw request targets, including query secrets.

    def trace(self):
        if not hasattr(self, "trace_id"):
            headers = getattr(self, "headers", {})
            values = headers.get_all("X-Trace-Id") if hasattr(headers, "get_all") else None
            if values is None and hasattr(headers, "get_all"):
                values = headers.get_all("X-Request-Id")
            candidate = values[0] if values and len(values) == 1 else ""
            self.trace_id = candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else str(uuid4())
        return self.trace_id

    def send(self, status, body, *, content_type="application/json", headers=None):
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Trace-Id", self.trace())
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        emit("request.out", traceId=self.trace(), method=self.command, status=status)

    def error(self, status, code, message, *, headers=None):
        emit("error", level="ERROR" if status >= 500 else "WARN", traceId=self.trace(), status=status, code=code)
        body = json.dumps({"error": {"code": code, "message": message, "service": SERVICE,
                                     "traceId": self.trace(), "details": {}}}).encode("utf-8")
        self.send(status, body, headers=headers)

    def send_error(self, code, message=None, explain=None):
        self.error(405 if code == 501 else code, "METHOD_NOT_ALLOWED" if code == 501 else "INVALID_REQUEST",
                   "HTTP request is not supported", headers={"Allow": "GET"} if code == 501 else None)

    def authenticated(self):
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1:
            return False
        scheme, separator, token = values[0].partition(" ")
        return scheme.lower() == "bearer" and bool(separator) and hmac.compare_digest(token.encode("utf-8"), self.server.token)

    def do_GET(self):
        try:
            route = urlsplit(self.path)
            if route.path == "/health" and not route.query:
                self.send(200, json.dumps({"service": SERVICE, "status": "UP"}).encode("utf-8"))
                return
            if route.path != "/internal/v1/logs":
                self.error(404, "ROUTE_NOT_FOUND", "Unknown operational route")
                return
            if not self.authenticated():
                self.error(401, "UNAUTHORIZED", "Valid operations bearer token is required",
                           headers={"WWW-Authenticate": "Bearer"})
                return
            options = Options.parse(route.query)
            if not self.server.slots.acquire(blocking=False):
                self.error(429, "TASK_LIMIT_REACHED", "Two log downloads are already in progress",
                           headers={"Retry-After": "1"})
                return
            try:
                content, filename = self.server.collector.snapshot(options)
                self.send(200, content, content_type="text/plain; charset=utf-8",
                          headers={"Content-Disposition": f'attachment; filename="{filename}"'})
            finally:
                self.server.slots.release()
        except ExportError as error:
            self.error(error.status, error.code, error.message)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.error(500, "INTERNAL_ERROR", "Log export failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", required=True, help="Exact project name used by the running stack")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--compose-file", type=Path, action="append", help="Repeat for the stack's overrides")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args(argv)
    files = args.compose_file or [ROOT / "docker-compose.yml"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", args.project_name) or not 1 <= args.port <= 65535:
        parser.error("Select a valid Compose project name and port 1..65535")
    if not args.env_file.is_file() or any(not path.is_file() for path in files):
        parser.error("The selected Compose and environment files must exist")
    try:
        server = LogServer(ComposeLogs(files, args.env_file, args.project_name), os.getenv("LOG_DOWNLOAD_TOKEN", ""), port=args.port)
    except (ValueError, OSError):
        parser.error("Set a valid LOG_DOWNLOAD_TOKEN and select an available localhost port")
    emit("startup", port=args.port, project=args.project_name)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        emit("shutdown")


if __name__ == "__main__":
    main()
