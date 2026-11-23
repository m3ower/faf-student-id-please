"""Read real exports and verify loading in a disposable schema in the Warehouse.

Configure ETL_SOURCES_FILE, all reporting credentials and PG* for a TEST Warehouse.
Never changes source services or their databases. Does not start a shared stack.
"""
import json
import os
from uuid import uuid4

import psycopg
from psycopg import sql
if __package__:
    from .run import ROOT, ETLError, extract, load, settings
else:
    from run import ROOT, ETLError, extract, load, settings

VIEWS = {
    ("player-service", "players"): "player_progression",
    ("session-service", "sessions"): "session_results",
    ("credential-service", "credential-inventory"): "credential_inventory",
    ("rules-service", "rules"): "rule_policy",
    ("applicant-service", "applicants"): "applicant_claims",
    ("university-record-service", "university-records"): "university_record_summary",
    ("moderation-service", "decisions"): "moderation_decisions",
    ("discord-dms-service", "channels"): "dms_channels",
    ("discord-dms-service", "channel-days"): "dms_channel_activity",
}


def verify():
    sources = settings()
    if len(sources) != 8 or not all(os.getenv(k) for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")):
        raise ETLError("INVALID_CONFIGURATION")
    canonical = {s["source"]: s["datasets"] for s in json.loads((ROOT / "sources.json").read_text())}
    if ({(s["source"], name) for s in sources for name in s["datasets"]} != set(VIEWS)
            or any(s["datasets"] != canonical.get(s["source"]) for s in sources)):
        raise ETLError("INVALID_CONFIGURATION")
    snapshots = {s["source"]: extract(s) for s in sources}
    expected = {(s["source"], dataset, identifier): data for s in sources
                for dataset, identifier, data in snapshots[s["source"]][1]}
    schema = "verify_warehouse_" + uuid4().hex
    with psycopg.connect(connect_timeout=3, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            with psycopg.connect(connect_timeout=3, options="-c search_path="+schema+" -c statement_timeout=5000", autocommit=True) as connection:
                fetch = lambda source: snapshots[source["source"]]
                run_id = uuid4()
                load(connection, sources, run_id, fetch=fetch)
                actual = {(source, dataset, identifier): data for source, dataset, identifier, data in connection.execute(
                    "SELECT source,dataset,record_id,data FROM current_warehouse_records")}
                if actual != expected: raise ETLError("VERIFICATION_MISMATCH")
                counts = []
                for (source, dataset), view in VIEWS.items():
                    # Materialize every column, so casts/type projections are checked too.
                    rows = connection.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(view))).fetchall()
                    count = sum(1 for key in expected if key[:2] == (source, dataset))
                    if len(rows) != count: raise ETLError("VERIFICATION_MISMATCH")
                    counts.append({"source": source, "dataset": dataset, "rows": count})
                if not load(connection, sources, run_id, fetch=fetch)["replayed"]:
                    raise ETLError("VERIFICATION_MISMATCH")
                def failed(_): raise ETLError("INJECTED_EXTRACTION_FAILURE")
                try:
                    load(connection, sources, uuid4(), fetch=failed)
                except ETLError as failure:
                    if str(failure) != "INJECTED_EXTRACTION_FAILURE": raise
                else:
                    raise ETLError("VERIFICATION_MISMATCH")
                if connection.execute("SELECT count(*) FROM warehouse_runs").fetchone()[0] != 1:
                    raise ETLError("VERIFICATION_MISMATCH")
                print(json.dumps({"verification": "passed", "sources": 8, "datasets": counts,
                                  "rows": len(expected), "replay": "passed", "injectedFailureRollback": "passed"}))
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    try:
        verify()
    except (ETLError, psycopg.Error) as failure:
        code = str(failure) if isinstance(failure, ETLError) else "WAREHOUSE_UNAVAILABLE"
        print(json.dumps({"verification": "failed", "code": code}))
        raise SystemExit(1)
