"""Owned reporting allowlists and typed views; no peer-private code or credentials."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from etl.run import ROOT, ETLError, settings, validate, load, extract
from test_etl import ExportPeer


def sources():
    return [s for s in json.loads((ROOT / "sources.json").read_text())
            if s["source"] in {"credential-service", "rules-service"}]


def snapshot(source):
    credential = source["source"] == "credential-service"
    return {"schemaVersion":1,"source":source["source"],"capturedAt":datetime.now(timezone.utc).isoformat(),
        "datasets":[{"name":next(iter(source["datasets"])),"records":[{"id":"STUDENT_ID" if credential else str(uuid4()),
        "data":{"credentialType":"STUDENT_ID","documentCount":2,"issuedDateCount":1,"expiryDateCount":0}
               if credential else {"type":"ONLY_FAF","severity":"MAJOR","active":True}}]}]}


class OwnedSchemaTests(unittest.TestCase):
    def test_extracts_owned_shapes_over_authenticated_http(self):
        for source in sources():
            with patch.dict(os.environ,{source["tokenEnv"]:"test_reporting_"+"x"*40}):
                peer=ExportPeer(source)
                try:
                    peer.value=snapshot(source)
                    self.assertEqual(len(extract(source)[1]),1)
                    self.assertEqual(peer.calls,1)
                finally:peer.close()

    def test_actual_shared_source_configuration_uses_four_distinct_credentials(self):
        configured=json.loads((ROOT / "sources.json").read_text())
        with patch.dict(os.environ,{s["tokenEnv"]:str(i)+"x"*39 for i,s in enumerate(configured)}):
            self.assertEqual(len(settings()),4)
        for source in sources():
            value=snapshot(source)
            self.assertEqual(len(validate(source,value)[1]),1)
            bad=copy.deepcopy(value)
            bad["datasets"][0]["records"][0]["data"]["email"]="private@example.test"
            with self.assertRaises(ETLError):validate(source,bad)
            bad=copy.deepcopy(value)
            field="documentCount" if source["source"]=="credential-service" else "active"
            bad["datasets"][0]["records"][0]["data"][field]=None
            with self.assertRaises(ETLError):validate(source,bad)


@unittest.skipUnless(os.getenv("ETL_TEST_DSN"),"Use a disposable ETL_TEST_DSN")
class OwnedReportingViewsTests(unittest.TestCase):
    def test_owned_snapshots_replace_current_views_and_failure_keeps_previous_batch(self):
        schema="owned_etl_"+uuid4().hex
        admin=psycopg.connect(os.environ["ETL_TEST_DSN"],autocommit=True)
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection=psycopg.connect(os.environ["ETL_TEST_DSN"],autocommit=True,options="-c search_path="+schema)
        try:
            selected=sources()
            values={s["source"]:snapshot(s) for s in selected}
            def fetch(source):return validate(source,values[source["source"]])
            first=uuid4()
            result=load(connection,selected,first,fetch=fetch)
            self.assertEqual(result["rows"],2)
            self.assertTrue(load(connection,selected,first,fetch=fetch)["replayed"])
            self.assertEqual(connection.execute("SELECT document_count,issued_date_count FROM credential_inventory").fetchone(),(2,1))
            self.assertEqual(connection.execute("SELECT active FROM rule_policy").fetchone(),(True,))
            values["rules-service"]["datasets"][0]["records"][0]["data"]["active"]=False
            values["credential-service"]["datasets"][0]["records"]=[]
            load(connection,selected,uuid4(),fetch=fetch)
            self.assertEqual(connection.execute("SELECT count(*) FROM credential_inventory").fetchone()[0],0)
            self.assertEqual(connection.execute("SELECT active FROM rule_policy").fetchone(),(False,))
            values["rules-service"]["datasets"]=[]
            with self.assertRaises(ETLError):load(connection,selected,uuid4(),fetch=fetch)
            self.assertEqual(connection.execute("SELECT count(*) FROM warehouse_runs").fetchone()[0],2)
            self.assertEqual(connection.execute("SELECT active FROM rule_policy").fetchone(),(False,))
        finally:
            connection.close()
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            admin.close()
