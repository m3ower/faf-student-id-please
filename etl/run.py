"""Bounded, authenticated service snapshots -> atomic PostgreSQL reporting batches."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 8 * 1024 * 1024
TOKEN = re.compile(r"[A-Za-z0-9_-]{32,256}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,128}")


class ETLError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Nonfinite number")
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def settings(path=None):
    try:
        sources = strict_json(Path(path or os.getenv("ETL_SOURCES_FILE", ROOT / "sources.json")).read_text())
        if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
            raise ValueError()
        names, credentials = set(), set()
        for source in sources:
            if set(source) != {"source", "url", "tokenEnv", "datasets"}:
                raise ValueError()
            name, url = source["source"], urlsplit(source["url"])
            if not NAME.fullmatch(name) or name in names:
                raise ValueError()
            names.add(name)
            if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password
                    or url.path != "/internal/v1/analytics/snapshot" or url.query or url.fragment):
                raise ValueError()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", source["tokenEnv"]):
                raise ValueError()
            token = os.environ.get(source["tokenEnv"], "")
            if not TOKEN.fullmatch(token) or token in credentials:
                raise ValueError()
            credentials.add(token)
            datasets = source["datasets"]
            if not isinstance(datasets, dict) or not 1 <= len(datasets) <= 8:
                raise ValueError()
            for name, fields in datasets.items():
                if not NAME.fullmatch(name) or not isinstance(fields, dict) or not 1 <= len(fields) <= 32:
                    raise ValueError()
                if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", k) or v not in ("integer", "number", "string", "uuid", "boolean") for k, v in fields.items()):
                    raise ValueError()
        return sources
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ETLError("INVALID_CONFIGURATION") from None


def validate(source, value):
    try:
        if set(value) != {"schemaVersion", "source", "capturedAt", "datasets"} or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1 or value["source"] != source["source"]:
            raise ValueError()
        captured = datetime.fromisoformat(value["capturedAt"].replace("Z", "+00:00"))
        if captured.tzinfo is None or captured.utcoffset().total_seconds() != 0:
            raise ValueError()
        seen, records, keys = set(), [], set()
        for dataset in value["datasets"]:
            name = dataset["name"]
            if set(dataset) != {"name", "records"} or name not in source["datasets"] or name in seen or not isinstance(dataset["records"], list):
                raise ValueError()
            seen.add(name)
            for row in dataset["records"]:
                if set(row) != {"id", "data"} or not isinstance(row["id"], str) or not IDENTIFIER.fullmatch(row["id"]) or (name, row["id"]) in keys:
                    raise ValueError()
                keys.add((name, row["id"]))
                fields = source["datasets"][name]
                if not isinstance(row["data"], dict) or set(row["data"]) != set(fields):
                    raise ValueError()
                normalized = {}
                for field, kind in fields.items():
                    item = row["data"][field]
                    if kind == "integer" and (type(item) is not int or not -(2**63) <= item < 2**63): raise ValueError()
                    if kind == "number" and (type(item) not in (int, float) or not math.isfinite(item)): raise ValueError()
                    if kind == "boolean" and type(item) is not bool: raise ValueError()
                    if kind in ("string", "uuid") and (not isinstance(item, str) or len(item) > 128): raise ValueError()
                    if kind == "uuid" and (len(item) != 36 or UUID(item).int == 0): raise ValueError()
                    # Transform into the canonical reporting representation before load.
                    normalized[field] = float(item) if kind == "number" else str(UUID(item)) if kind == "uuid" else item
                records.append((name, row["id"], normalized))
                if len(records) > 10000:
                    raise ValueError()
        if seen != set(source["datasets"]):
            raise ValueError()
        return captured, records
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ETLError("INVALID_EXPORT") from None


def extract(source):
    request = Request(source["url"], headers={"Authorization": "Bearer " + os.environ[source["tokenEnv"]],
        "X-Service-Name": "warehouse-etl", "Accept": "application/json"})
    try:
        began = time.monotonic()
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=2) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ETLError("EXPORT_REFUSED")
            data = bytearray()
            while chunk := response.read1(min(65536, MAX_BYTES + 1 - len(data))):
                data.extend(chunk)
                if len(data) > MAX_BYTES or time.monotonic() - began > 5:
                    raise ETLError("EXPORT_LIMIT_EXCEEDED")
        return validate(source, strict_json(data.decode("utf-8")))
    except ETLError:
        raise
    except HTTPError as failure:
        failure.close()
        raise ETLError("EXPORT_UNAVAILABLE") from None
    except (URLError, OSError, ValueError, UnicodeError):
        raise ETLError("EXPORT_UNAVAILABLE") from None


def load(connection, sources, run_id, *, fetch=extract, retain=30):
    if not 1 <= retain <= 1000 or UUID(str(run_id)).int == 0:
        raise ETLError("INVALID_CONFIGURATION")
    with connection.transaction():
        if not connection.execute("SELECT pg_try_advisory_xact_lock(5003001)").fetchone()[0]:
            raise ETLError("ETL_ALREADY_RUNNING")
        connection.execute((ROOT / "schema.sql").read_text())
        existing = connection.execute("SELECT row_count FROM warehouse_runs WHERE run_id=%s", (run_id,)).fetchone()
        if existing:
            return {"runId": str(run_id), "rows": existing[0], "replayed": True}
        # Fetch/validate every configured source before writing any reporting batch.
        snapshots = [(source, *fetch(source)) for source in sources]
        count = sum(len(records) for _, _, records in snapshots)
        connection.execute("INSERT INTO warehouse_runs(run_id,source_count,row_count) VALUES(%s,%s,%s)", (run_id, len(sources), count))
        for source, captured, records in snapshots:
            connection.execute("INSERT INTO warehouse_sources VALUES(%s,%s,%s)", (run_id, source["source"], captured))
            with connection.cursor() as cursor:
                cursor.executemany("INSERT INTO warehouse_records VALUES(%s,%s,%s,%s,%s)",
                    [(run_id, source["source"], dataset, identifier, Jsonb(data)) for dataset, identifier, data in records])
        connection.execute("DELETE FROM warehouse_runs WHERE run_id NOT IN (SELECT run_id FROM warehouse_runs ORDER BY loaded_at DESC,run_id DESC LIMIT %s)", (retain,))
    return {"runId": str(run_id), "rows": count, "replayed": False}


def main():
    run_id = os.getenv("ETL_RUN_ID", str(uuid4()))
    try:
        sources = settings()
        try:
            identifier = UUID(run_id)
            retain = int(os.getenv("WAREHOUSE_RETAIN_RUNS", "30"))
            if identifier.int == 0 or not 1 <= retain <= 1000: raise ValueError()
        except ValueError:
            raise ETLError("INVALID_CONFIGURATION") from None
        if not all(os.getenv(k) for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")):
            raise ETLError("INVALID_CONFIGURATION")
        with psycopg.connect(connect_timeout=3, options="-c statement_timeout=5000", autocommit=True) as connection:
            result = load(connection, sources, identifier, retain=retain)
        print(json.dumps({"event": "etl_completed", **result}))
        return 0
    except (ETLError, ValueError, psycopg.Error) as failure:
        code = str(failure) if isinstance(failure, ETLError) else "WAREHOUSE_UNAVAILABLE"
        print(json.dumps({"event": "etl_failed", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
