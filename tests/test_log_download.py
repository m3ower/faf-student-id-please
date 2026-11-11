import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

from scripts.log_download import (
    ComposeLogs, ExportError, LogServer, Options, bounded_command, emit, main,
)


TOKEN = "local_test_only_" + "a" * 32


class QueryTests(unittest.TestCase):
    def test_defaults_and_valid_filters(self):
        self.assertEqual(Options.parse(""), Options())
        self.assertEqual(Options.parse("service=applicant-service&since=1h&tail=25"),
                         Options("applicant-service", "1h", 25))

    def test_invalid_or_duplicate_options_fail_closed(self):
        for query in ("service=../secret", "service=--all", "service=", "tail=0", "tail=1001",
                      "tail=-1", "tail=abc", "tail=1&tail=2", "since=forever", "token=private",
                      "follow=true", "tail", "service=a&since=5m&tail=1&extra=x"):
            with self.subTest(query=query), self.assertRaises(ExportError) as raised:
                Options.parse(query)
            self.assertEqual(raised.exception.status, 400)


class CommandTests(unittest.TestCase):
    def command(self, source, limit=4096, timeout=5, **kwargs):
        return bounded_command([sys.executable, "-c", source], time.monotonic() + timeout, limit, **kwargs)

    def test_stdout_and_successful_stderr_logs_are_collected(self):
        output = self.command("import sys; print('out'); print('err', file=sys.stderr)", include_stderr=True)
        self.assertIn(b"out", output)
        self.assertIn(b"err", output)

    def test_nonzero_exit_never_echoes_diagnostics(self):
        with self.assertRaises(ExportError) as raised:
            self.command("import sys; print('private-database-password'); sys.exit(2)", include_stderr=True)
        self.assertEqual(raised.exception.status, 503)
        self.assertNotIn("private-database-password", str(raised.exception))

    def test_output_limit_stops_a_running_process(self):
        with self.assertRaises(ExportError) as raised:
            self.command("import sys,time; sys.stdout.buffer.write(b'x'*10000); sys.stdout.flush(); time.sleep(10)", limit=128)
        self.assertEqual(raised.exception.code, "LOG_EXPORT_TOO_LARGE")

    def test_timeout_stops_a_running_process(self):
        started = time.monotonic()
        with self.assertRaises(ExportError) as raised:
            self.command("import time; time.sleep(10)", timeout=0.25)
        self.assertEqual(raised.exception.status, 504)
        self.assertLess(time.monotonic() - started, 5)

    def test_already_expired_deadline_does_not_start_a_process(self):
        with self.assertRaises(ExportError) as raised:
            bounded_command(["not-executed"], time.monotonic() - 1, 100)
        self.assertEqual(raised.exception.status, 504)

    def test_missing_docker_returns_sanitized_unavailable(self):
        with self.assertRaises(ExportError) as raised:
            bounded_command(["nonexistent-pad-log-command-117"], time.monotonic() + 2, 100)
        self.assertEqual(raised.exception.status, 503)

    def test_operations_token_is_not_inherited_by_the_child(self):
        with patch.dict(os.environ, {"LOG_DOWNLOAD_TOKEN": TOKEN}):
            output = self.command("import os; print('LOG_DOWNLOAD_TOKEN' in os.environ)")
        self.assertEqual(output.strip(), b"False")


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.collector = ComposeLogs([Path("docker-compose.yml"), Path("override.yml")], Path(".env"), "pad-test")

    def test_all_declared_services_and_overrides_stay_in_the_selected_project(self):
        with patch("scripts.log_download.bounded_command", side_effect=[b"gateway-service\npostgres\napplicant-service\n", b"applicant-service | line\n"]) as run:
            content, filename = self.collector.snapshot(Options())
        command = run.call_args_list[1].args[0]
        self.assertEqual(command[:4], ["docker", "compose", "--project-name", "pad-test"])
        self.assertEqual(command.count("--file"), 2)
        self.assertIn("--timestamps", command)
        self.assertIn("--no-color", command)
        self.assertNotIn("--follow", command)
        self.assertEqual(command[-3:], ["applicant-service", "gateway-service", "postgres"])
        self.assertIn(b"project=pad-test", content)
        self.assertIn(b"applicant-service | line", content)
        self.assertRegex(filename, r"^student-id-logs-\d{8}T\d{6}Z\.log$")
        self.assertEqual(run.call_args_list[0].args[1], run.call_args_list[1].args[1])

    def test_owned_service_filter_includes_only_its_declared_numeric_replicas(self):
        catalog = b"applicant-service\napplicant-service-2\napplicant-service-3\napplicant-service-other\npostgres\n"
        with patch("scripts.log_download.bounded_command", side_effect=[catalog, b""]) as run:
            self.collector.snapshot(Options("applicant-service", "5m", 1))
        self.assertEqual(run.call_args.args[0][-3:], ["applicant-service", "applicant-service-2", "applicant-service-3"])

    def test_unknown_service_cannot_reach_the_log_command(self):
        with patch("scripts.log_download.bounded_command", return_value=b"applicant-service\n") as run:
            with self.assertRaises(ExportError) as raised:
                self.collector.snapshot(Options("foreign-project-container"))
        self.assertEqual(raised.exception.code, "UNKNOWN_LOG_SERVICE")
        self.assertEqual(run.call_count, 1)

    def test_invalid_catalog_and_oversized_header_are_refused(self):
        for catalog in (b"", b"\xff", b"--env-file=private\n", b"\n", "\n".join(f"svc-{i}" for i in range(129)).encode()):
            with self.subTest(catalog=catalog[:30]), patch("scripts.log_download.bounded_command", return_value=catalog):
                with self.assertRaises(ExportError) as raised:
                    self.collector.snapshot(Options())
                self.assertEqual(raised.exception.status, 503)
        self.collector.max_bytes = 10
        with patch("scripts.log_download.bounded_command", return_value=b"applicant-service\n"):
            with self.assertRaises(ExportError) as raised:
                self.collector.snapshot(Options())
        self.assertEqual(raised.exception.status, 413)


class FakeCollector:
    def __init__(self):
        self.options = []
        self.failure = None
        self.release = None

    def snapshot(self, options):
        self.options.append(options)
        if self.release is not None:
            self.release.wait(3)
        if self.failure:
            raise self.failure
        return b"# snapshot\napplicant-service | example\n", "student-id-logs-20261111T000000Z.log"


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = FakeCollector()
        cls.server = LogServer(cls.collector, TOKEN, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def setUp(self):
        self.collector.options.clear()
        self.collector.failure = None
        self.collector.release = None

    def request(self, target="/internal/v1/logs", *, token=TOKEN, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        actual = {"Authorization": "Bearer " + token} if token is not None else {}
        actual.update(headers or {})
        connection.request(method, target, headers=actual)
        response = connection.getresponse()
        result = response.status, dict(response.headers), response.read()
        connection.close()
        return result

    def test_health_checks_only_the_exporter(self):
        status, _, body = self.request("/health", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "UP")
        self.assertEqual(self.collector.options, [])
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_download_is_a_private_attachment_with_the_requested_filters(self):
        status, headers, body = self.request("/internal/v1/logs?service=applicant-service&since=1h&tail=20",
                                             headers={"X-Trace-Id": "task4.trace-117"})
        self.assertEqual(status, 200)
        self.assertEqual(self.collector.options, [Options("applicant-service", "1h", 20)])
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment; filename=", headers["Content-Disposition"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Trace-Id"], "task4.trace-117")
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_missing_wrong_and_malformed_auth_never_call_docker(self):
        for token, extra in ((None, {}), ("wrong", {}), (None, {"Authorization": "Bearer"}),
                             (None, {"Authorization": "Basic abc"}), ("wrong \u00e9", {})):
            with self.subTest(token=token):
                status, headers, body = self.request(token=token, headers=extra)
                self.assertEqual(status, 401)
                self.assertEqual(headers["WWW-Authenticate"], "Bearer")
                error = json.loads(body)["error"]
                self.assertEqual(error["code"], "UNAUTHORIZED")
                self.assertEqual(error["traceId"], headers["X-Trace-Id"])
        self.assertEqual(self.collector.options, [])

    def test_duplicate_auth_is_rejected_and_duplicate_trace_is_replaced(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.putrequest("GET", "/internal/v1/logs")
        for _ in range(2):
            connection.putheader("Authorization", "Bearer " + TOKEN)
            connection.putheader("X-Trace-Id", "duplicate")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 401)
        self.assertNotEqual(response.getheader("X-Trace-Id"), "duplicate")
        response.read()
        connection.close()

    def test_invalid_trace_is_replaced_and_request_alias_is_accepted(self):
        _, headers, _ = self.request(headers={"X-Trace-Id": "contains spaces"})
        self.assertNotEqual(headers["X-Trace-Id"], "contains spaces")
        _, headers, _ = self.request(headers={"X-Request-Id": "old-alias"})
        self.assertEqual(headers["X-Trace-Id"], "old-alias")

    def test_invalid_query_path_and_method_are_sanitized(self):
        status, _, _ = self.request("/internal/v1/logs?token=private-query")
        self.assertEqual(status, 400)
        status, _, _ = self.request("/../../.env")
        self.assertEqual(status, 404)
        status, headers, _ = self.request(method="POST")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET")
        status, _, body = self.request(method="HEAD")
        self.assertEqual(status, 405)
        self.assertEqual(body, b"")

    def test_collector_failure_and_unexpected_failure_do_not_leak_details(self):
        for failure, expected in ((ExportError(504, "LOG_EXPORT_TIMEOUT", "Snapshot timed out"), 504),
                                  (RuntimeError("private-database-password"), 500)):
            self.collector.failure = failure
            status, _, body = self.request()
            self.assertEqual(status, expected)
            self.assertNotIn(b"private-database-password", body)
        self.collector.failure = None
        self.assertEqual(self.request()[0], 200)  # Failure released its download slot.

    def test_saturation_refuses_without_queueing_and_keeps_health_available(self):
        self.collector.release = threading.Event()
        completed = []
        workers = [threading.Thread(target=lambda: completed.append(self.request())) for _ in range(2)]
        for worker in workers:
            worker.start()
        try:
            deadline = time.monotonic() + 2
            while len(self.collector.options) != 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(self.collector.options), 2)
            status, headers, _ = self.request()
            self.assertEqual(status, 429)
            self.assertEqual(headers["Retry-After"], "1")
            self.assertEqual(self.request("/health", token=None)[0], 200)
            self.assertEqual(len(self.collector.options), 2)
        finally:
            self.collector.release.set()
            for worker in workers:
                worker.join(5)
        self.assertEqual([result[0] for result in completed], [200, 200])

    def test_access_logs_never_include_credentials_query_strings_or_contents(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.request("/internal/v1/logs?secret=private-query", token="private-bearer")
            self.request()
        for value in (TOKEN, "private-query", "private-bearer", "applicant-service | example"):
            self.assertNotIn(value, output.getvalue())
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(all(record["event"] in {"request.out", "error"} for record in records))
        self.assertTrue(any(record.get("code") == "UNAUTHORIZED" for record in records))


class StartupTests(unittest.TestCase):
    def test_invalid_operations_secret_does_not_open_a_listener(self):
        for token in ("", "short", "a" * 257, "a" * 32 + " "):
            with self.subTest(token=token), self.assertRaises(ValueError):
                LogServer(FakeCollector(), token, port=0)

    def test_main_validates_configuration_and_closes_after_interrupt(self):
        root = Path(__file__).resolve().parents[1]
        arguments = ["--project-name", "pad-test", "--compose-file", str(root / "docker-compose.yml"),
                     "--env-file", str(root / ".env.example")]
        with patch.dict(os.environ, {"LOG_DOWNLOAD_TOKEN": TOKEN}), patch("scripts.log_download.LogServer") as server, patch("scripts.log_download.emit"):
            server.return_value.serve_forever.side_effect = KeyboardInterrupt
            main(arguments)
            server.return_value.server_close.assert_called_once()
        for extra in (["--port", "0"], ["--project-name", "../foreign"], ["--env-file", str(root / "missing-task4.env")]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(arguments + extra)
        with patch.dict(os.environ, {"LOG_DOWNLOAD_TOKEN": ""}), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(arguments)

    def test_structured_event_has_service_identity(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            emit("startup", port=8092)
        self.assertEqual(json.loads(output.getvalue())["service"], "log-download-service")


if __name__ == "__main__":
    unittest.main()
