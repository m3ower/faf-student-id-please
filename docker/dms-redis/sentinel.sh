#!/bin/sh
# Discord DMs Redis Sentinel (Lab 5: replication and failover).
#
# Three Sentinels watch the master named MASTER_NAME. When QUORUM of them cannot reach it for
# DOWN_AFTER_MS, they elect a leader that promotes the most up-to-date replica and re-points
# the others; a master that comes back is turned into a replica. The configuration is written
# once into the Sentinel's own volume, because Sentinel rewrites it as the cluster changes:
# a restarted Sentinel must remember a failover, not start over from INITIAL_MASTER.
set -eu

: "${SELF:?SELF is this Sentinel as host:port}"
: "${INITIAL_MASTER:?INITIAL_MASTER is the first master as host:port}"
: "${MASTER_NAME:=dms-redis}"
: "${QUORUM:=2}"
: "${DOWN_AFTER_MS:=5000}"
: "${FAILOVER_TIMEOUT_MS:=30000}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
: "${SENTINEL_PASSWORD:?SENTINEL_PASSWORD is required}"
: "${CONF:=/data/sentinel.conf}"
: "${REDIS_BIN:=}"
# The image's entrypoint takes ownership of /data (this configuration included) and drops
# from root to the redis user. Local tests start redis-server directly.
: "${START_CMD:=docker-entrypoint.sh redis-server}"
: "${BIND:=}"
# Docker service names instead of container IPs (Redis 6.2+). Local tests on IPs set "no".
: "${HOSTNAMES:=yes}"

host() { echo "${1%:*}"; }
port() { echo "${1##*:}"; }

if [ ! -s "$CONF" ]; then
    umask 077
    {
        echo "port $(port "$SELF")"
        [ -n "$BIND" ] && echo "bind $BIND"
        echo "dir $(dirname "$CONF")"
        if [ "$HOSTNAMES" = yes ]; then
            echo "sentinel resolve-hostnames yes"
            echo "sentinel announce-hostnames yes"
            echo "sentinel announce-ip $(host "$SELF")"
        fi
        echo "sentinel monitor $MASTER_NAME $(host "$INITIAL_MASTER") $(port "$INITIAL_MASTER") $QUORUM"
        echo "sentinel auth-pass $MASTER_NAME $REDIS_PASSWORD"
        echo "sentinel down-after-milliseconds $MASTER_NAME $DOWN_AFTER_MS"
        echo "sentinel failover-timeout $MASTER_NAME $FAILOVER_TIMEOUT_MS"
        echo "sentinel parallel-syncs $MASTER_NAME 1"
        # Clients and the other Sentinels authenticate with this password.
        echo "requirepass $SENTINEL_PASSWORD"
    } > "$CONF"
    printf '{"service":"dms-redis-sentinel","sentinel":"%s","event":"sentinel.configured","master":"%s"}\n' "$SELF" "$INITIAL_MASTER"
fi
# shellcheck disable=SC2086
exec $START_CMD "$CONF" --sentinel
