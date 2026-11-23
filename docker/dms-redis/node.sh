#!/bin/sh
# Discord DMs Redis node (Lab 5: replication and failover).
#
# On every start the node asks the Sentinels which node is master now, and starts as its
# replica (or as master when that is itself). A fixed --replicaof on the command line would
# re-attach a restarted node to the original master even after a failover.
# On the very first start, before any Sentinel knows the cluster, INITIAL_MASTER is master.
set -eu

: "${SELF:?SELF is this node as host:port}"
: "${INITIAL_MASTER:?INITIAL_MASTER is the first master as host:port}"
: "${SENTINELS:?SENTINELS lists the Sentinels as host:port}"
: "${MASTER_NAME:=dms-redis}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
: "${SENTINEL_PASSWORD:?SENTINEL_PASSWORD is required}"
: "${DATA_DIR:=/data}"
# Generated per start, outside the data volume; it holds the passwords, never the command line.
: "${CONF:=/tmp/redis.conf}"
: "${REDIS_BIN:=}"
# The image's entrypoint takes ownership of /data and drops from root to the redis user.
# Local tests start redis-server directly.
: "${START_CMD:=docker-entrypoint.sh redis-server}"
: "${BIND:=}"
# Announce SELF's host name to Sentinel and the master (Docker service names). Local tests on
# plain IPs set "no": the Windows Redis 5 build cannot sync a replica that announces itself.
: "${ANNOUNCE:=yes}"

log() {
    printf '{"ts":"%s","service":"dms-redis","node":"%s","event":"%s"%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SELF" "$1" "${2:-}"
}

host() { echo "${1%:*}"; }
port() { echo "${1##*:}"; }

# The master the Sentinels agree on now, as host:port; empty when none answers.
current_master() {
    for s in $SENTINELS; do
        out=$(REDISCLI_AUTH="$SENTINEL_PASSWORD" "${REDIS_BIN}redis-cli" -h "$(host "$s")" -p "$(port "$s")" \
            SENTINEL get-master-addr-by-name "$MASTER_NAME" 2>/dev/null | tr -d '\r' || true)
        h=$(echo "$out" | sed -n 1p)
        p=$(echo "$out" | sed -n 2p)
        case "$p" in '' | *[!0-9]*) continue ;; esac
        echo "$h:$p"
        return
    done
}

master=$(current_master)
if [ -z "$master" ]; then
    master=$INITIAL_MASTER
    log node.no_sentinel_answer ",\"master\":\"$master\""
fi

umask 077
{
    echo "port $(port "$SELF")"
    [ -n "$BIND" ] && echo "bind $BIND"
    echo "dir $DATA_DIR"
    echo "appendonly yes"
    echo "requirepass $REDIS_PASSWORD"
    echo "masterauth $REDIS_PASSWORD"
    # Sentinel and the other nodes reach this node by its service name, not a container IP.
    [ "$ANNOUNCE" = yes ] && echo "replica-announce-ip $(host "$SELF")"
    if [ "$master" != "$SELF" ]; then
        echo "replicaof $(host "$master") $(port "$master")"
    fi
} > "$CONF"
if [ "$(id -u)" = 0 ] && id redis >/dev/null 2>&1; then
    chown redis "$CONF"
fi

if [ "$master" = "$SELF" ]; then
    log node.starting ",\"role\":\"master\""
else
    log node.starting ",\"role\":\"replica\",\"master\":\"$master\""
fi
# shellcheck disable=SC2086
exec $START_CMD "$CONF" "$@"
