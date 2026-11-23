#!/bin/sh
set -eu
umask 077
case "${CACHE_PASSWORD:-}" in *[!A-Za-z0-9_-]*|'') echo 'Configure a private URL-safe CACHE_PASSWORD' >&2; exit 1;; esac
[ "${#CACHE_PASSWORD}" -ge 32 ] && [ "${#CACHE_PASSWORD}" -le 256 ] || { echo 'Invalid cache credential length' >&2; exit 1; }
config=/tmp/owned-cache.conf
{
  printf '%s\n' 'bind 0.0.0.0' 'protected-mode yes' 'port 6379' 'save ""' 'appendonly no' 'maxmemory 64mb' 'maxmemory-policy allkeys-lru' 'maxclients 128' 'timeout 5'
  printf 'requirepass %s\n' "$CACHE_PASSWORD"
} > "$config"
chown redis:redis "$config"
chmod 600 "$config"
exec /usr/local/bin/docker-entrypoint.sh redis-server "$config"
