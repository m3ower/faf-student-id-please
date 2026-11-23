"""Populated contract peers for all eight sources; not private-service code."""
import copy
from datetime import datetime, timezone
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from etl.run import ROOT, ETLError, extract, load, settings, validate
from etl.verify_exports import verify
from psycopg.conninfo import conninfo_to_dict
from test_etl import ExportPeer

VIEWS = ("player_progression", "session_results", "credential_inventory", "rule_policy",
         "applicant_claims", "university_record_summary", "moderation_decisions", "dms_channels", "dms_channel_activity")
NEW_SOURCES = ("applicant-service", "university-record-service", "moderation-service", "discord-dms-service")


def snapshot(source):
    identifier = str(uuid4())
    values = {
        "player-service": {"players": {"level": 1, "xp": 100, "shiftsCompleted": 1, "accuracyTotal": 1.0, "disciplinaryActions": 0}},
        "session-service": {"sessions": {"teamId": identifier, "difficulty": "NORMAL", "state": "LOBBY", "applicationsProcessed": 0, "score": 0, "penalties": 0, "rulesetVersion": 0, "revision": 0}},
        "credential-service": {"credential-inventory": {"credentialType": "STUDENT_ID", "documentCount": 2, "issuedDateCount": 2, "expiryDateCount": 1}},
        "rules-service": {"rules": {"type": "ONLY_FAF", "severity": "MAJOR", "active": True}},
        "applicant-service": {"applicants": {"year": 2, "universityStatus": "ENROLLED", "role": "STUDENT", "courseCount": 3}},
        "university-record-service": {"university-records": {"status": "ENROLLED", "courseCount": 3, "outlookGroupCount": 2, "fcimMessageCount": 4}},
        "moderation-service": {"decisions": {"sessionId": identifier, "moderatorId": identifier, "action": "ACCEPT", "expectedAction": "ACCEPT", "correct": True, "penalty": 0, "scoreDelta": 100, "penaltyRefunded": 0, "appealStatus": "NONE", "violatedRuleCount": 0, "decidedAtEpochMs": 1795435200000}},
        "discord-dms-service": {
            "channels": {"sessionId": identifier, "channel": "#general-mod-chat", "readOnly": False, "messageCount": 3},
            "channel-days": {"sessionId": identifier, "channel": "#general-mod-chat", "day": "2026-11-23", "messages": 3, "playerMessages": 2, "systemMessages": 1, "distinctSenders": 2}},
    }[source["source"]]
    datasets = []
    for name, data in values.items():
        key = "STUDENT_ID" if name == "credential-inventory" else identifier
        if name.startswith("channel"):
            key += ":general-mod-chat" + (":2026-11-23" if name == "channel-days" else "")
        datasets.append({"name": name, "records": [{"id": key, "data": data}]})
    return {"schemaVersion": 1, "source": source["source"], "capturedAt": datetime.now(timezone.utc).isoformat(), "datasets": datasets}


class AllSourceContractTests(unittest.TestCase):
    def test_manifests_are_activated_without_drift_and_all_datasets_validate(self):
        configured = json.loads((ROOT / "sources.json").read_text())
        self.assertEqual(len(configured), 8)
        self.assertEqual(sum(len(s["datasets"]) for s in configured), 9)
        for name in NEW_SOURCES:
            manifest = json.loads((ROOT.parent / "contracts" / "analytics" / (name + ".json")).read_text())
            self.assertEqual(next(s for s in configured if s["source"] == name), manifest)
        with patch.dict(os.environ, {s["tokenEnv"]: "test_"+str(i)+"x"*40 for i, s in enumerate(configured)}):
            self.assertEqual(len(settings()), 8)
        for source in configured:
            value = snapshot(source)
            self.assertEqual(len(validate(source, value)[1]), len(source["datasets"]))
            bad = copy.deepcopy(value)
            bad["datasets"][0]["records"][0]["data"]["privateText"] = "synthetic-private-content"
            with self.assertRaises(ETLError): validate(source, bad)
        dms = next(s for s in configured if s["source"] == "discord-dms-service")
        missing = snapshot(dms); missing["datasets"].pop()
        with self.assertRaises(ETLError): validate(dms, missing)


@unittest.skipUnless(os.getenv("ETL_TEST_DSN"), "Use a disposable ETL_TEST_DSN")
class AllSourceWarehouseTests(unittest.TestCase):
    def setUp(self):
        self.sources = json.loads((ROOT / "sources.json").read_text())
        self.env = patch.dict(os.environ, {s["tokenEnv"]: "test_"+str(i)+"x"*40 for i, s in enumerate(self.sources)})
        self.env.start(); self.addCleanup(self.env.stop)
        self.admin = psycopg.connect(os.environ["ETL_TEST_DSN"], autocommit=True)
        self.schema = "all_etl_" + uuid4().hex
        self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.connection = psycopg.connect(os.environ["ETL_TEST_DSN"], autocommit=True, options="-c search_path="+self.schema)
        self.peers = []
        for source in self.sources:
            peer = ExportPeer(source); peer.value = snapshot(source); self.peers.append(peer)

    def tearDown(self):
        for peer in self.peers: peer.close()
        self.connection.close()
        self.admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))); self.admin.close()

    def test_all_nine_views_replay_updates_deletion_and_failure_atomicity(self):
        first = uuid4()
        self.assertEqual(load(self.connection, self.sources, first)["rows"], 9)
        calls = [p.calls for p in self.peers]
        self.assertTrue(load(self.connection, self.sources, first)["replayed"])
        self.assertEqual([p.calls for p in self.peers], calls)
        for view in VIEWS:
            self.assertEqual(self.connection.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(view))).fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT claimed_year,claimed_course_count FROM applicant_claims").fetchone(), (2, 3))
        self.assertEqual(self.connection.execute("SELECT legacy_fcim_message_count FROM university_record_summary").fetchone()[0], 4)
        self.assertEqual(self.connection.execute("SELECT correct,score_delta FROM moderation_decisions").fetchone(), (True, 100))
        self.assertEqual(self.connection.execute("SELECT utc_day,player_messages,system_messages FROM dms_channel_activity").fetchone(), ("2026-11-23", 2, 1))
        peers = {s["source"]: p for s, p in zip(self.sources, self.peers)}
        peers["university-record-service"].value["datasets"][0]["records"][0]["data"]["courseCount"] = 7
        peers["applicant-service"].value["datasets"][0]["records"] = []
        for dataset in peers["discord-dms-service"].value["datasets"]: dataset["records"] = []
        load(self.connection, self.sources, uuid4())
        self.assertEqual(self.connection.execute("SELECT course_count FROM university_record_summary").fetchone()[0], 7)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM applicant_claims").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM dms_channel_activity").fetchone()[0], 0)
        for name in NEW_SOURCES:
            peer = peers[name]; peer.status = 503
            with self.subTest(source=name), self.assertRaises(ETLError): load(self.connection, self.sources, uuid4())
            peer.status = 200
            self.assertEqual(self.connection.execute("SELECT count(*) FROM warehouse_runs").fetchone()[0], 2)
            self.assertEqual(self.connection.execute("SELECT xp FROM player_progression").fetchone()[0], 100)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM warehouse_records WHERE run_id=%s", (first,)).fetchone()[0], 9)

    def test_acceptance_runner_reads_every_real_http_peer_and_cleans_its_schema(self):
        info = conninfo_to_dict(os.environ["ETL_TEST_DSN"])
        env = {"PG"+key: info[name] for key, name in
               (("HOST", "host"), ("PORT", "port"), ("DATABASE", "dbname"), ("USER", "user"), ("PASSWORD", "password"))}
        before = self.admin.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'verify_warehouse_%'").fetchone()[0]
        with patch.dict(os.environ, env), patch("etl.verify_exports.settings", return_value=self.sources), patch("builtins.print") as output:
            verify()
        result = json.loads(output.call_args.args[0])
        self.assertEqual((result["verification"], result["sources"], result["rows"]), ("passed", 8, 9))
        self.assertEqual(len(result["datasets"]), 9)
        self.assertTrue(all(peer.calls == 1 for peer in self.peers))
        after = self.admin.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'verify_warehouse_%'").fetchone()[0]
        self.assertEqual(before, after)
