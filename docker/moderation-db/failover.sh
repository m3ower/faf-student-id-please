#!/bin/sh
# Moderation PostgreSQL failover monitor (Lab 5: replication and failover).
#
# Every CHECK_INTERVAL seconds it asks each node for its role:
#   - one primary:  every replica must stream from it; a replica still pointed elsewhere
#                   (the old primary after a failover) is re-pointed and reloaded.
#   - no primary for FAILOVER_AFTER checks in a row, with a replica up: promote the replica
#                   that has received the most WAL (pg_promote), so the least is lost.
#   - two primaries (a former primary started before it saw the promotion): the one on the
#                   older timeline is fenced read-only and its client sessions are ended, so
#                   applications reconnect to the real primary. Restarting it makes node.sh
#                   re-clone it as a replica.
# The service never needs to know: its JDBC URL lists every node with
# targetServerType=primary, so the driver connects to whichever is primary now.
set -u

: "${NODES:?NODES lists every node as host:port}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${REPLICATION_USER:=replicator}"
# The monitor keeps the replication role on the primary in step with this password, so a
# cluster created before replication can adopt it. Replicas read it from the passfile each
# node writes at boot (node.sh); primary_conninfo only names that file.
: "${REPLICATION_PASSWORD:?REPLICATION_PASSWORD is required}"
: "${REPLICATION_PASSFILE:=/var/lib/postgresql/replication.pgpass}"
: "${CHECK_INTERVAL:=2}"
: "${FAILOVER_AFTER:=5}"
: "${PG_BIN:=}"
export LC_ALL=C

log() {
    printf '{"ts":"%s","service":"moderation-db-failover","event":"%s"%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${2:-}"
}

host() { echo "${1%:*}"; }
port() { echo "${1##*:}"; }

q() {
    PGPASSWORD="$POSTGRES_PASSWORD" PGCONNECT_TIMEOUT=2 "${PG_BIN}psql" -h "$(host "$1")" -p "$(port "$1")" \
        -U "$POSTGRES_USER" -d postgres -Atqc "$2" 2>/dev/null | tr -d '\r' || true
}

role() {
    q "$1" "SELECT CASE WHEN pg_is_in_recovery() THEN 'replica'
                        WHEN current_setting('default_transaction_read_only') = 'on' THEN 'fenced'
                        ELSE 'primary' END"
}

timeline() { q "$1" "SELECT ('x' || substr(pg_walfile_name(pg_current_wal_lsn()), 1, 8))::bit(32)::int"; }

received() { q "$1" "SELECT pg_wal_lsn_diff(COALESCE(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()), '0/0')::bigint"; }

# host:port the replica is configured to stream from.
upstream() {
    info=$(q "$1" "SHOW primary_conninfo")
    h=$(echo "$info" | sed -n 's/.*host=\([^ ]*\).*/\1/p')
    p=$(echo "$info" | sed -n 's/.*port=\([^ ]*\).*/\1/p')
    echo "$h:$p"
}

repoint() {
    app=$(echo "$1" | tr ':.-' '___')
    q "$1" "ALTER SYSTEM SET primary_conninfo = 'host=$(host "$2") port=$(port "$2") user=$REPLICATION_USER passfile=$REPLICATION_PASSFILE application_name=$app'" >/dev/null
    q "$1" "SELECT pg_reload_conf()" >/dev/null
    log replica.repointed ",\"replica\":\"$1\",\"primary\":\"$2\""
}

fence() {
    q "$1" "ALTER SYSTEM SET default_transaction_read_only = on" >/dev/null
    q "$1" "SELECT pg_reload_conf()" >/dev/null
    q "$1" "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()" >/dev/null
    log primary.fenced ",\"node\":\"$1\""
}

# The replication role (with the current password) and WAL retention, on a primary. The
# statements carry a password, so this session never logs a failing statement's text.
ensure_replication() {
    if PGPASSWORD="$POSTGRES_PASSWORD" PGCONNECT_TIMEOUT=2 "${PG_BIN}psql" -h "$(host "$1")" -p "$(port "$1")" \
        -U "$POSTGRES_USER" -d postgres -Atq -v ON_ERROR_STOP=1 \
        -c "SET log_min_error_statement = panic" -c "SET log_statement = 'none'" \
        -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$REPLICATION_USER') THEN CREATE ROLE \"$REPLICATION_USER\" WITH LOGIN REPLICATION; END IF; END \$\$" \
        -c "ALTER ROLE \"$REPLICATION_USER\" WITH LOGIN REPLICATION PASSWORD '$REPLICATION_PASSWORD'" \
        -c "ALTER SYSTEM SET wal_keep_size = '512MB'" -c "SELECT pg_reload_conf()" >/dev/null 2>&1; then
        log replication.ensured ",\"primary\":\"$1\""
    else
        log replication.ensure_failed ",\"primary\":\"$1\""
    fi
}

seen_primary=0
missing=0
current=""
log monitor.started ",\"nodes\":\"$NODES\",\"failoverAfterChecks\":$FAILOVER_AFTER"
while :; do
    primaries=""
    replicas=""
    for n in $NODES; do
        case "$(role "$n")" in
            primary) primaries="$primaries $n" ;;
            replica) replicas="$replicas $n" ;;
        esac
    done
    set -- $primaries
    if [ "$#" -gt 1 ]; then
        best=""
        best_tli=-1
        for n in $primaries; do
            t=$(timeline "$n")
            case "$t" in '' | *[!0-9]*) t=0 ;; esac
            if [ "$t" -gt "$best_tli" ]; then best=$n; best_tli=$t; fi
        done
        for n in $primaries; do
            [ "$n" != "$best" ] && fence "$n"
        done
        log split_brain.resolved ",\"primary\":\"$best\""
    elif [ "$#" -eq 1 ]; then
        primary=$1
        if [ "$primary" != "$current" ]; then
            log primary.seen ",\"primary\":\"$primary\""
            ensure_replication "$primary"
            current=$primary
        fi
        seen_primary=1
        missing=0
        for r in $replicas; do
            [ "$(upstream "$r")" != "$primary" ] && repoint "$r" "$primary"
        done
    elif [ -n "$replicas" ]; then
        missing=$((missing + 1))
        log primary.missing ",\"checks\":$missing"
        # After a monitor restart with no primary in sight, wait longer before acting alone.
        if [ "$missing" -ge "$FAILOVER_AFTER" ] && { [ "$seen_primary" = 1 ] || [ "$missing" -ge $((FAILOVER_AFTER * 6)) ]; }; then
            best=""
            best_lsn=-1
            for r in $replicas; do
                l=$(received "$r")
                case "$l" in '' | *[!0-9]*) continue ;; esac
                if [ "$l" -gt "$best_lsn" ]; then best=$r; best_lsn=$l; fi
            done
            if [ -n "$best" ] && [ "$(q "$best" "SELECT pg_promote(true, 30)")" = "t" ]; then
                log failover.promoted ",\"primary\":\"$best\",\"receivedLsnBytes\":$best_lsn"
                current=$best
                missing=0
            else
                log failover.promotion_failed ",\"candidate\":\"$best\""
            fi
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
