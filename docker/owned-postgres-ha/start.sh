#!/bin/sh
set -eu
umask 077
mkdir -p /var/lib/postgresql/ha
chown postgres:postgres /var/lib/postgresql/ha
exec gosu postgres /opt/patroni/bin/python /opt/owned-ha/start.py
