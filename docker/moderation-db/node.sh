#!/bin/sh
# Moderation PostgreSQL node (Lab 5: replication and failover).
#
# Every node runs this before PostgreSQL and decides its role on each start:
#   - empty data, a primary exists      -> clone it with pg_basebackup and stream from it
#   - empty data, no primary, first node -> initialise a new cluster (docker-entrypoint.sh)
#   - a replica                         -> follow whichever node is primary now
#   - a former primary, another primary -> it was failed over: discard and re-clone, so it
#                                          rejoins as a replica, never as a second primary
#   - a former primary, no other primary -> start as primary, unless a peer is on a newer
#                                          timeline (then it is stale and waits)
# Promotion itself is done by failover.sh. Only the official postgres image is used.
set -eu

: "${PGDATA:=/var/lib/postgresql/data}"
: "${SELF:?SELF is this node as host:port}"
: "${NODES:?NODES lists every node as host:port}"
: "${INITIAL_PRIMARY:?INITIAL_PRIMARY is the node that initialises an empty cluster}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${REPLICATION_USER:=replicator}"
: "${REPLICATION_PASSWORD:?REPLICATION_PASSWORD is required}"
# In the container the data belongs to the postgres user; local tests run as themselves.
: "${RUN_AS=su-exec postgres}"
: "${START_CMD:=docker-entrypoint.sh postgres}"
: "${PG_BIN:=}"
# How long a former primary looks for another primary before starting as one itself.
: "${BOOT_WAIT:=10}"
# The replication password lives in this libpq passfile, outside the data volume, so it is
# never written into primary_conninfo, which PostgreSQL logs whenever it changes.
: "${REPLICATION_PASSFILE:=/var/lib/postgresql/replication.pgpass}"
export LC_ALL=C

log() {
    printf '{"ts":"%s","service":"moderation-db","node":"%s","event":"%s"%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SELF" "$1" "${2:-}"
}

host() { echo "${1%:*}"; }
port() { echo "${1##*:}"; }

# One value from a peer, or nothing when it cannot answer. Never prints a password.
q() {
    PGPASSWORD="$POSTGRES_PASSWORD" PGCONNECT_TIMEOUT=2 "${PG_BIN}psql" -h "$(host "$1")" -p "$(port "$1")" \
        -U "$POSTGRES_USER" -d postgres -Atqc "$2" 2>/dev/null | tr -d '\r' || true
}

# The node that accepts writes now: not in recovery and not fenced read-only.
find_primary() {
    for n in $NODES; do
        [ "$n" = "$SELF" ] && continue
        if [ "$(q "$n" "SELECT NOT pg_is_in_recovery() AND current_setting('default_transaction_read_only') = 'off'")" = "t" ]; then
            echo "$n"
            return
        fi
    done
}

# The newest timeline any reachable peer is on. A promotion starts a new timeline.
peer_timeline() {
    max=0
    for n in $NODES; do
        [ "$n" = "$SELF" ] && continue
        t=$(q "$n" "SELECT CASE WHEN pg_is_in_recovery()
                        THEN COALESCE((SELECT received_tli FROM pg_stat_wal_receiver), (SELECT timeline_id FROM pg_control_checkpoint()))
                        ELSE ('x' || substr(pg_walfile_name(pg_current_wal_lsn()), 1, 8))::bit(32)::int END")
        case "$t" in '' | *[!0-9]*) ;; *) [ "$t" -gt "$max" ] && max=$t ;; esac
    done
    echo "$max"
}

own_timeline() {
    t=$(${RUN_AS} "${PG_BIN}pg_controldata" "$PGDATA" | sed -n "s/^Latest checkpoint's TimeLineID: *//p" | tr -d '\r')
    echo "${t:-0}"
}

conninfo() {
    echo "host=$(host "$1") port=$(port "$1") user=$REPLICATION_USER passfile=$REPLICATION_PASSFILE application_name=$(echo "$SELF" | tr ':.-' '___')"
}

# Point this node's replica configuration at primary $1.
follow() {
    ${RUN_AS} touch "$PGDATA/standby.signal"
    ${RUN_AS} sed -i '/^primary_conninfo/d' "$PGDATA/postgresql.auto.conf"
    printf "primary_conninfo = '%s'\n" "$(conninfo "$1")" | ${RUN_AS} tee -a "$PGDATA/postgresql.auto.conf" >/dev/null
    log node.following ",\"primary\":\"$1\""
}

clone() {
    log node.cloning ",\"primary\":\"$1\""
    find "$PGDATA" -mindepth 1 -delete
    if ! PGPASSFILE="$REPLICATION_PASSFILE" ${RUN_AS} "${PG_BIN}pg_basebackup" -h "$(host "$1")" -p "$(port "$1")" \
        -U "$REPLICATION_USER" -D "$PGDATA" -X stream -c fast -w; then
        # The primary may not have the replication role yet (failover.sh adds it); retry.
        log node.clone_failed ",\"primary\":\"$1\""
        find "$PGDATA" -mindepth 1 -delete
        return 1
    fi
    follow "$1"
}

# A cluster created before replication was added has no replication entry in pg_hba.conf.
allow_replication() {
    if [ -s "$PGDATA/pg_hba.conf" ] && ! grep -q "^host replication $REPLICATION_USER " "$PGDATA/pg_hba.conf"; then
        echo "host replication $REPLICATION_USER all scram-sha-256" | ${RUN_AS} tee -a "$PGDATA/pg_hba.conf" >/dev/null
        log node.replication_allowed
    fi
}

mkdir -p "$PGDATA"
if [ "$(id -u)" = 0 ]; then
    chown postgres:postgres "$PGDATA"
fi
chmod 700 "$PGDATA" 2>/dev/null || true
printf '*:*:*:%s:%s\n' "$REPLICATION_USER" "$REPLICATION_PASSWORD" | ${RUN_AS} tee "$REPLICATION_PASSFILE" >/dev/null
${RUN_AS} chmod 600 "$REPLICATION_PASSFILE"

waited=0
while :; do
    primary=$(find_primary)
    if [ ! -s "$PGDATA/PG_VERSION" ]; then
        if [ -n "$primary" ]; then
            clone "$primary" && break
            sleep 2
            continue
        fi
        if [ "$SELF" = "$INITIAL_PRIMARY" ]; then
            log node.initialising
            break
        fi
        log node.waiting_for_primary
        sleep 2
        continue
    fi
    if [ -f "$PGDATA/standby.signal" ]; then
        [ -n "$primary" ] && follow "$primary"
        log node.starting ",\"role\":\"replica\""
        break
    fi
    if [ -n "$primary" ]; then
        # This node was primary, and another node has been promoted since: rejoin as its
        # replica. Writes it took after the failover was decided are discarded, never merged.
        log node.rejoining ",\"primary\":\"$primary\""
        clone "$primary" && break
        sleep 2
        continue
    fi
    mine=$(own_timeline)
    newest=$(peer_timeline)
    if [ "$newest" -gt "$mine" ]; then
        log node.stale_waiting ",\"timeline\":$mine,\"peerTimeline\":$newest"
        sleep 2
        continue
    fi
    if [ "$waited" -lt "$BOOT_WAIT" ]; then
        waited=$((waited + 2))
        sleep 2
        continue
    fi
    log node.starting ",\"role\":\"primary\",\"timeline\":$mine"
    break
done

allow_replication
# shellcheck disable=SC2086
exec $START_CMD "$@"
