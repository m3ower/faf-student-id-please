# Applicant and University Record PostgreSQL HA (Lab 5 Grade 5)

This opt-in addition changes only Andrei's PostgreSQL deployments and the owned
services' failover error handling. It preserves the independently owned
Moderation/DMs replication overlay, shared Warehouse, business transports and
architecture diagram. It is a source candidate, not a deployed/published release.

## Topology and behavior

Each service has one PostgreSQL 16 writer and **two physical streaming replicas**:

| Scope | Nodes | Application database / owner |
| --- | --- | --- |
| Applicant | `applicant-db`, `applicant-db-2`, `applicant-db-3` | `applicant_db` / `applicant_user` |
| Record | `university-record-db`, `university-record-db-2`, `university-record-db-3` | `record_db` / `record_user` |

Patroni 4.1.5 runs with each PostgreSQL instance; three etcd 3.5.17 members keep
separate leadership scopes in one control quorum. Quorum metadata is not shared
business storage. A replica follows PostgreSQL WAL from its own scope's writer;
no service reads another's database. All three database volumes and all three
etcd volumes persist. Names are stable across container restart.

Patroni owns promotion and rejoining. It uses a 20-second leadership TTL,
2-second loop and 3-second DCS retry budget, timeline checking and a 1 MiB maximum
sampled failover lag. With quorum, an eligible replica is promoted after primary
loss; the other replica follows it. A former primary uses `pg_rewind` (data
checksums and WAL hints enabled) to rejoin. Rewind failure stops recovery for
operator review; automatic deletion/re-cloning of diverged data is disabled.
When the etcd majority is unavailable, Patroni demotes rather than intentionally
running an independent writer. Database roles and leadership are checked in the
isolated acceptance test, not inferred from container health alone.

Replication is **asynchronous**. WAL not yet replicated can be lost even after
client acknowledgment; the sampled lag threshold is not a strict RPO guarantee.
This is single-host Compose HA for process/container failures, not protection
against losing that machine/drive. Hardware watchdog/STONITH, TLS transport and
arbitrary network/OS-stall split-brain certification are not included. Do not
manually promote behind Patroni or run duplicate controllers for a scope.

## Application connections and failure contract

The overlay supplies all three hosts, with pgJDBC `targetServerType=primary` for
Applicant and pgx `target_session_attrs=read-write` for Record. New connections
must select a writer; old broken connections are discarded. Both primary and
second application instances receive the same selector. Promotion does not need
an application restart. Existing business task deadlines/admission remain.

The owned 1.5.0 source candidates classify connection/shutdown/recovery and
read-only-role errors as sanitized HTTP/gRPC business status 503
`DATABASE_UNAVAILABLE`. HTTP supplies `Retry-After: 1`; existing task timeout,
capacity, authorization and business errors keep their mappings. Probes stay
outside business admission and fail closed without a usable database connection.

There is no automatic mutation replay. An interrupted call may have committed;
reconcile resource state first. Existing initialization IDs, hashes, receipts,
outboxes and durable consumer deduplication are preserved. Only existing
idempotent operations may be replayed with their original business identifiers.

## Private configuration

Use `.env.owned-postgres-ha.example` with the same ignored private deployment
environment. `HA_APPLICANT_IMAGE` and `HA_RECORD_IMAGE` require reviewed,
failover-aware 1.5.0+ images; no stable tag or source pointer is silently changed.
Build the infrastructure image from `docker/owned-postgres-ha` locally, or select
a separately reviewed published image with `OWNED_POSTGRES_HA_IMAGE`.

For each scope, use four distinct URL-safe 32..256-character credentials:
application password (existing `APPLICANT_DB_PASSWORD` / `RECORD_DB_PASSWORD`),
`*_HA_ADMIN_PASSWORD`, `*_HA_REPLICATION_PASSWORD`, and `*_HA_REST_PASSWORD`.
Patroni creates the application owner without superuser/role-creation/database-
creation/replication privileges; it owns only its application database. Admin,
replication and control credentials never enter the application or Warehouse.
The local Patroni configuration/passfile uses restrictive permissions and never
prints secrets. Tests scan node, controller and service logs for test secrets.

The etcd network `owned-ha-control` is internal and attached only to etcd and
Patroni/PostgreSQL nodes. Applications keep their existing separate networks.
No PostgreSQL, etcd or Patroni REST host ports are published. Patroni mutation
control requires its distinct REST credential; control-plane addresses are not
business catalog entries. HTTP control and PostgreSQL operate on private Docker
networks without TLS in this lab.

## Existing data and safe activation

**Fresh HA volumes are intentional.** `volumes: !override` replaces only each
service's mount selection. It never deletes/reuses `applicant-pg-data` or
`record-pg-data`; those original volumes remain available for backup/rollback.
Starting the overlay on fresh HA volumes does not migrate existing data.

Before connecting existing traffic:

1. Back up and verify both owned databases separately. Preserve the Compose
   project name and all original volumes. Plan downtime for application writes
   and owner background delivery workers; snapshot/dump while writes are stopped.
2. Start only the owned etcd/PostgreSQL HA nodes, validate one writer/two replicas
   in each scope, and restore each logical dump into its own new database using
   the appropriate owner. Retain ownership/privileges; check schema migrations,
   initialization IDs, outboxes/receipts and ordinary row counts.
3. Confirm replication catch-up and validate the restored data before starting
   the failover-aware applications with their multi-host URL. Check both public
   and internal paths, real readiness, load and reporting exports.
4. Rollback requires a deliberate write freeze and data reconciliation. Do not
   reconnect an old, now-stale single-node volume and call it current. Never use
   `down -v` when keeping data or rely on copying live PGDATA between timelines.

This change does not perform a migration or start your shared deployment.

## Build and run in an appropriate environment

The overlay requires Docker Compose with `!override` support. Append it **last**,
including after the Warehouse overlay if used, so the HA client/image choices
remain in effect. It can also follow the teammate replication overlay because
its service/resource names are distinct.

```powershell
docker compose --env-file <private-env> -f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.owned-postgres-ha.yml build applicant-db
# Follow the existing-data procedure above before connecting existing applications.
docker compose --env-file <private-env> -f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.owned-postgres-ha.yml up -d
```

Use the same project/private environment and `-f` list for subsequent commands.
Inspect replication with `SELECT application_name,state FROM pg_stat_replication`
on the current writer and `SELECT pg_is_in_recovery()` on every node. There must
be exactly one writer per scope. Inspect leadership using the private Patroni
status endpoint; do not change roles by issuing raw `pg_promote()`.

## Verification

`scripts/verify_owned_postgres_ha.py` builds no images and touches only resources
under a generated UUID prefix. Supply local tested application images and the
built HA image; its default helper image contains Python gRPC tooling:

```text
python scripts/verify_owned_postgres_ha.py --postgres-image <local-ha-image> --applicant-image <local-applicant-image> --record-image <local-record-image> --helper-image <python-grpc-tools-image>
```

It starts three private etcd nodes and two isolated three-node PostgreSQL clusters,
then uses actual Java/Go HTTP and authenticated native gRPC handlers. It checks
replica catch-up before a crash, automatic promotion, unchanged persistent
initialization receipts, same-ID deduplication, former-primary rejoining, DCS
majority loss/readiness failure and quorum restoration. It never retries an
ambiguous non-idempotent write. Only sanitized pass/fail evidence is retained;
cleanup removes only its own containers, volumes and networks. None of these
checks prove an already deployed or published full-team release.

Configuration follows [PostgreSQL streaming replication](https://www.postgresql.org/docs/16/warm-standby.html),
[Patroni configuration](https://patroni.readthedocs.io/en/latest/yaml_configuration.html),
[Patroni replication modes](https://patroni.readthedocs.io/en/latest/replication_modes.html),
[pgJDBC multi-host selection](https://jdbc.postgresql.org/documentation/use/),
and [pgx connection settings](https://github.com/jackc/pgx/blob/master/pgconn/config.go).


### Executed acceptance ? 2026-11-24

All **42 isolated real-container checks passed** against the owned 1.5.0 builds.
This includes actual HTTP CRUD and authenticated native gRPC initialization;
catch-up of both physical replicas; automatic promotion after crashing each
primary; unchanged receipt hashes and duplicate-ID handling; fresh HTTP writes
on each promoted writer; preservation of both pending owner outbox records;
former-primary rewind/rejoin; demotion/readiness failure on etcd majority loss;
restoration of quorum, connections and two replicas; and credential-free logs
from all eleven containers. The test restarted no application containers.
All uniquely scoped test containers, volumes and networks were removed.

Exact private source candidates:

- [Applicant PR #40](https://github.com/Andreiisthebest/student-id-applicant-service/pull/40),
  issue #39, revision `291ed9d4a08095e5cef804a19ad7b26266c0012e`.
  Full isolated PostgreSQL suite: 63 tests, 94.16% application line coverage.
- [Record PR #40](https://github.com/Andreiisthebest/student-id-university-record-service/pull/40),
  issue #39, revision `3b14aa382543699591eb3af073a5b50295e78d7f`.
  Full race/database suite: 78.2% line and 81.8% statement coverage.

The live test identified and fixed a real Docker DNS failure mode: stopped node
hostnames may disappear. Record now limits each multi-host DNS lookup to 200 ms
and each connect to at most 500 ms inside the parent deadline, preserving time
for a healthy fallback; single-host settings, including TLS prefer/allow fallbacks,
are preserved by a focused compatibility test. Query/task deadlines
are not enlarged and mutations are not automatically retried.

Three configuration boundary tests pass (scope/host validation, distinct
credentials and non-destructive storage/recovery settings). The combined base,
Broker, Warehouse, teammate replication and owned HA Compose files validate with
the `replicas` profile: six owned DB nodes, four writer-aware app instances and
three private etcd members. Resolved environment/credentials were not printed.
The official PostgreSQL/etcd base images are pinned by verified manifest digest.
No application image, infrastructure image or existing deployment was published
or activated by this work. Existing-data migration and reviewed release selection
remain operator tasks before a rollout; asynchronous data-loss and single-host
limits above still apply.
