#!/bin/sh
# Runs once, when the first Moderation node initialises an empty cluster
# (docker-entrypoint-initdb.d). Replicas copy all of this with pg_basebackup.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=repl_user="${REPLICATION_USER:-replicator}" --set=repl_pass="$REPLICATION_PASSWORD" <<'SQL'
CREATE ROLE :"repl_user" WITH LOGIN REPLICATION PASSWORD :'repl_pass';
-- Keep enough WAL for a replica that fell behind or is re-pointed after a failover.
ALTER SYSTEM SET wal_keep_size = '512MB';
SQL

echo "host replication ${REPLICATION_USER:-replicator} all scram-sha-256" >> "$PGDATA/pg_hba.conf"
