"""Validated local Patroni configuration. Never logs secrets or writes into legacy PGDATA."""
import json
import os
from pathlib import Path
import re


def configuration(env):
    def value(key, pattern):
        item = env.get(key, "")
        if not re.fullmatch(pattern, item):
            raise ValueError("Invalid HA setting: " + key)
        return item
    name = value("HA_NAME", r"[a-z][a-z0-9-]{0,62}")
    scope = value("HA_SCOPE", r"(?:applicant|record)")
    hosts = value("HA_ETCD_HOSTS", r"[a-z0-9-]+:2379(?:,[a-z0-9-]+:2379){2}")
    value("HA_APP_USER", r"[a-z][a-z0-9_]{0,62}")
    value("HA_APP_DATABASE", r"[a-z][a-z0-9_]{0,62}")
    secrets = [value(k, r"[A-Za-z0-9_-]{32,256}") for k in
               ("HA_ADMIN_PASSWORD", "HA_REPLICATION_PASSWORD", "HA_REST_PASSWORD", "HA_APP_PASSWORD")]
    if len(set(secrets)) != len(secrets):
        raise ValueError("HA credentials must be distinct")
    admin, replication, rest, _ = secrets
    hba = ["local all all trust", "host replication replicator 0.0.0.0/0 scram-sha-256",
           "host all all 0.0.0.0/0 scram-sha-256"]
    parameters = {"wal_level": "replica", "max_wal_senders": 10, "max_replication_slots": 10,
                  "wal_keep_size": "128MB", "wal_log_hints": "on", "password_encryption": "scram-sha-256",
                  "log_statement": "none", "log_min_error_statement": "panic"}
    return {
        "scope": scope, "namespace": "/owned-postgres/", "name": name,
        "restapi": {"listen": "0.0.0.0:8008", "connect_address": name + ":8008",
                    "authentication": {"username": "patroni", "password": rest}},
        "etcd3": {"hosts": hosts},
        "bootstrap": {"dcs": {"ttl": 20, "loop_wait": 2, "retry_timeout": 3,
                                "maximum_lag_on_failover": 1048576, "check_timeline": True,
                                "postgresql": {"use_pg_rewind": True, "parameters": parameters}},
                      "initdb": [{"encoding": "UTF8"}, "data-checksums"], "pg_hba": hba,
                      "post_bootstrap": "/opt/owned-ha/bootstrap.py"},
        "postgresql": {"listen": "0.0.0.0:5432", "connect_address": name + ":5432",
                       "data_dir": "/var/lib/postgresql/ha/data", "bin_dir": "/usr/lib/postgresql/16/bin",
                       "pgpass": "/tmp/owned-ha.pgpass", "pg_hba": hba,
                       "authentication": {"superuser": {"username": "postgres", "password": admin},
                                          "replication": {"username": "replicator", "password": replication}},
                       "basebackup": [{"checkpoint": "fast"}],
                       "use_pg_rewind": True, "remove_data_directory_on_rewind_failure": False,
                       "remove_data_directory_on_diverged_timelines": False},
        "watchdog": {"mode": "off"},
    }


if __name__ == "__main__":
    try:
        config = configuration(os.environ)
    except ValueError as failure:
        raise SystemExit(str(failure)) from None
    path = Path("/tmp/owned-patroni.json")
    path.write_text(json.dumps(config), encoding="utf-8")
    path.chmod(0o600)
    os.execv("/opt/patroni/bin/patroni", ["patroni", str(path)])
