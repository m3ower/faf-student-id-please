import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from etl.run import ETLError, ROOT, extract, load, main, settings, strict_json, validate


def fixture(source):
    data = ({"level": 1, "xp": 100, "shiftsCompleted": 1, "accuracyTotal": 1.0, "disciplinaryActions": 0}
        if source["source"] == "player-service" else
        {"teamId": str(uuid4()), "difficulty": "NORMAL", "state": "COMPLETED", "applicationsProcessed": 1,
         "score": 100, "penalties": 0, "rulesetVersion": 1, "revision": 2})
    return {"schemaVersion": 1, "source": source["source"], "capturedAt": datetime.now(timezone.utc).isoformat(),
        "datasets": [{"name": next(iter(source["datasets"])), "records": [{"id": str(uuid4()), "data": data}]}]}


class ExportPeer:
    def __init__(self, source):
        self.value, self.status, self.calls = fixture(source), 200, 0
        peer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                peer.calls += 1
                if self.headers.get("Authorization") != "Bearer " + os.environ[source["tokenEnv"]] or self.headers.get("X-Service-Name") != "warehouse-etl":
                    self.send_error(401); return
                self.send_response(peer.status)
                if peer.status == 302: self.send_header("Location", "/redirected")
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(peer.value).encode())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        source["url"] = f"http://127.0.0.1:{self.server.server_port}/internal/v1/analytics/snapshot"

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.sources = json.loads((ROOT / "sources.json").read_text())
        self.env = patch.dict(os.environ, {s["tokenEnv"]: ("p" if i == 0 else "s") * 40 for i, s in enumerate(self.sources)})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_strict_schema_and_privacy_allowlists(self):
        source = self.sources[0]; value = fixture(source)
        self.assertEqual(len(validate(source, value)[1]), 1)
        value["datasets"][0]["records"][0]["data"]["accuracyTotal"] = 1
        self.assertIsInstance(validate(source, value)[1][0][2]["accuracyTotal"], float)
        for mode in ("version", "source", "timezone", "pii", "missing", "bool", "duplicate", "unknown-dataset", "nonfinite", "null"):
            bad = copy.deepcopy(value)
            if mode == "version": bad["schemaVersion"] = 2
            if mode == "source": bad["source"] = "other-service"
            if mode == "timezone": bad["capturedAt"] = "2026-01-01T00:00:00"
            if mode == "pii": bad["datasets"][0]["records"][0]["data"]["email"] = "synthetic@example.test"
            if mode == "missing": bad["datasets"] = []
            if mode == "bool": bad["datasets"][0]["records"][0]["data"]["xp"] = True
            if mode == "duplicate": bad["datasets"][0]["records"] *= 2
            if mode == "unknown-dataset": bad["datasets"][0]["name"] = "auth"
            if mode == "nonfinite": bad["datasets"][0]["records"][0]["data"]["accuracyTotal"] = float("nan")
            if mode == "null": bad["datasets"] = None
            with self.subTest(mode=mode), self.assertRaises(ETLError): validate(source, bad)
        for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(ValueError): strict_json(raw)

    def test_configuration_and_http_refusals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.json"
            path.write_text(json.dumps(self.sources)); self.assertEqual(len(settings(path)), 2)
            for mode in ("token", "url", "duplicate-source", "schema"):
                bad = copy.deepcopy(self.sources)
                if mode == "token": bad[1]["tokenEnv"] = bad[0]["tokenEnv"]
                if mode == "url": bad[0]["url"] = "http://user:password@host/internal/v1/analytics/snapshot"
                if mode == "duplicate-source": bad[1]["source"] = bad[0]["source"]
                if mode == "schema": bad[0]["datasets"]["players"]["xp"] = "anything"
                path.write_text(json.dumps(bad))
                with self.subTest(mode=mode), self.assertRaises(ETLError): settings(path)
        peer = ExportPeer(self.sources[0]); self.addCleanup(peer.close)
        self.assertEqual(len(extract(self.sources[0])[1]), 1)
        peer.status = 302
        with self.assertRaises(ETLError): extract(self.sources[0])
        self.assertEqual(peer.calls, 2, "redirect must not forward the reporting token")
        peer.status = 401
        with self.assertRaises(ETLError): extract(self.sources[0])

    def test_failure_logging_contains_no_configuration_values(self):
        with patch.dict(os.environ, {"PLAYER_WAREHOUSE_EXPORT_TOKEN": ""}), patch("builtins.print") as output:
            self.assertEqual(main(), 1)
            text = output.call_args.args[0]
            self.assertEqual(json.loads(text), {"event": "etl_failed", "code": "INVALID_CONFIGURATION"})


@unittest.skipUnless(os.getenv("ETL_TEST_DSN"), "Use a disposable ETL_TEST_DSN")
class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.sources = json.loads((ROOT / "sources.json").read_text())
        self.env = patch.dict(os.environ, {s["tokenEnv"]: ("p" if i == 0 else "s") * 40 for i, s in enumerate(self.sources)})
        self.env.start(); self.addCleanup(self.env.stop)
        self.admin = psycopg.connect(os.environ["ETL_TEST_DSN"], autocommit=True)
        self.schema = "test_etl_" + uuid4().hex
        self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.connection = psycopg.connect(os.environ["ETL_TEST_DSN"], autocommit=True, options="-c search_path=" + self.schema)
        self.peers = [ExportPeer(s) for s in self.sources]

    def tearDown(self):
        for peer in self.peers: peer.close()
        self.connection.close()
        self.admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))); self.admin.close()

    def test_real_http_to_postgres_replays_updates_deletes_and_retains_history(self):
        run_id = uuid4()
        result = load(self.connection, self.sources, run_id)
        self.assertEqual(result["rows"], 2)
        before = [p.calls for p in self.peers]
        self.assertTrue(load(self.connection, self.sources, run_id)["replayed"])
        self.assertEqual([p.calls for p in self.peers], before)
        self.assertEqual(self.connection.execute("SELECT xp FROM player_progression").fetchone()[0], 100)
        self.peers[0].value["datasets"][0]["records"][0]["data"]["xp"] = 200
        load(self.connection, self.sources, uuid4(), retain=2)
        self.assertEqual(self.connection.execute("SELECT xp FROM player_progression").fetchone()[0], 200)
        self.peers[0].value["datasets"][0]["records"] = []
        load(self.connection, self.sources, uuid4(), retain=2)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM player_progression").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM session_results").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM warehouse_runs").fetchone()[0], 2)

    def test_failed_source_or_invalid_schema_never_replaces_previous_batch(self):
        load(self.connection, self.sources, uuid4())
        for mode in ("down", "wrong-schema"):
            self.peers[1].status = 503 if mode == "down" else 200
            self.peers[1].value["schemaVersion"] = 2
            with self.assertRaises(ETLError): load(self.connection, self.sources, uuid4())
            self.assertEqual(self.connection.execute("SELECT count(*) FROM warehouse_runs").fetchone()[0], 1)
            self.assertEqual(self.connection.execute("SELECT xp FROM player_progression").fetchone()[0], 100)

    def test_concurrent_job_refused_without_waiting(self):
        with self.admin.transaction():
            self.admin.execute("SELECT pg_advisory_xact_lock(5003001)")
            with self.assertRaisesRegex(ETLError, "ETL_ALREADY_RUNNING"):
                load(self.connection, self.sources, uuid4())
