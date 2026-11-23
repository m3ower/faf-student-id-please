# Applicant and University Record caching (Lab 5 Grade 6)

Source candidates **1.6.0** add optional service-owned Redis read caches. This
covers Andrei's two services; teammate implementations and the architecture
diagram are unchanged. Source completion is not a published or deployed release.

| Service | Cached reads | Authentication data |
| --- | --- | --- |
| Applicant | Management `GET /api/v1/applicants/{id}` and internal profile/claims projections, including native gRPC | Existing receiver/management authentication stays live; Applicant is not a player-session issuer |
| Record | `GET /api/v1/records/academic-context`, internal enrollment facts and identity facts, including native gRPC and the existing read-only identity POST adapter | Explicit Session membership denials only, scoped by session/player/permission, TTL one second; grants always live |

Do not cache positive permissions, private deception/answer keys, readiness,
receipts, pending initialization state, outboxes, errors or missing resources.
Session's readiness check still precedes Applicant profile delivery. Record's
protected public slices retain explicit live assignment authorization. A newly
granted assignment can remain denied for one second; revocations take effect
on the next authorization attempt. Failed dependencies never become grants.
The denial-cache tests use the real Redis implementation and a controlled test
verifier; they do not establish live Session interoperability.

## Invalidation and bounds

Successful data projections have a 30-second TTL. Each service owns a UUID
`cache_generations` row changed by PostgreSQL statement triggers in the same
transaction as relevant inserts, updates, deletes and truncates. Cache lookups
first read the authoritative writer's generation. Commits invalidate across
replicas even when Redis is unavailable; rollbacks do not. A late fill under an
old generation is unreachable by subsequent reads. Random generations avoid
reuse when asynchronous failover rewinds database state. Grade 5's possible
loss of unreplicated commits remains; caching does not repair it.

Applicant fences applicants, courses and initialization rows. Record fences
records, initialization links/envelopes, identity facts, academic context and
course catalog. Identity-facts keys also include the UTC date. One generation
per service deliberately favors correctness and conservatively invalidates
unrelated keys. Relevant writes serialize briefly on that row. Cache hits still
perform a generation query; this reduces hydration work rather than eliminating
all database access. No throughput or zero-loss guarantee is claimed.

Keys contain hashed identifiers, not raw identities or tokens. HMAC signatures
bind the key, expiry and JSON body using a domain-separated receiver credential;
credential rotation makes old entries unusable. HMAC is integrity protection,
not encryption. Bodies are limited to 16 KiB and envelopes to 32 KiB, with bounded
Redis reads. Invalid, unavailable or oversized entries fall back to the source
and increment error/miss counters as appropriate. Errors trigger a one-second
cooldown. Database failure does not serve stale cached data.

Applicant shares a 50 ms Redis I/O budget within the trusted parent deadline,
with socket/connect waits capped at 15 ms and DNS off the business thread.
Generation queries retain the existing database/task deadline.
Record caps Redis operations at 20 ms within the parent deadline, without
retries; membership's one-second total budget includes cache and live Broker
work. No business deadlines, payloads, allowlists or admission accounting change.

`GET /status` retains its database/readiness/load fields and adds actual
per-process counters, for example:

```json
{"cache":{"enabled":true,"hits":12,"misses":3,"errors":0}}
```

Counters reset on restart. `enabled` means configured, not healthy. Probes do not
load business cache entries. Redis availability is not a readiness prerequisite.

## Configuration and adoption

Add `.env.owned-cache.example` names to the existing ignored private environment:

- `CACHE_APPLICANT_IMAGE`, `CACHE_RECORD_IMAGE`: reviewed cache-capable 1.6.0+
  release images, preferably immutable digests. No placeholder tag is published.
- `APPLICANT_CACHE_PASSWORD`, `RECORD_CACHE_PASSWORD`: distinct URL-safe
  32..256-character secrets, also distinct from every business, Discovery,
  reporting and database credential. Never commit real values.

The opt-in `docker-compose.owned-cache.yml` adds one pinned Redis per owned
service on its existing private network, without host ports or persisted data.
Each is limited to 64 MB with LRU eviction; authentication is configured through
a restricted temporary file, not a secret-bearing server command argument.
All four application replicas receive matching cache settings. Their existing
gRPC transport, subscriptions and reporting tokens are preserved.

Append this overlay **last** to the normal base and owned-Broker files, after
Warehouse and any replication/caching overlays already in use. If using the
owned PostgreSQL HA overlay (merged CPR #188), place its overlay
before this one. Version 1.6.0 includes the owned HA driver behavior. Never point
an old published 1.4.0 image at the new cache settings and call it enabled.

```text
docker compose --env-file .env -f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.warehouse.yml -f docker-compose.owned-cache.yml config --quiet
```

That command validates only; normal promotion/startup remains a separate step.
Do not print a resolved configuration containing secrets. Omitting this overlay
leaves existing behavior unchanged. The service defaults `CACHE_ENABLED=false`;
Redis is disposable and cache failures do not block source-backed requests.
There is no consistent-hashing/sharding implementation in this grade.

## Reproducible evidence

Both private CI workflows start disposable authenticated Redis alongside their
isolated PostgreSQL database. Applicant passed 68 tests, **94.4% line coverage**;
Record passed its race-enabled full suite, **78.9% line / 82.4% statement** coverage.
Tests cover TTL, committed/rolled-back generation changes, racing fills, corrupt
and oversized entries, disabled/outage behavior, cancellation, authentication
and HTTP/gRPC shared application projections. Coverage gates remain >=70%.

CPR's `scripts/validate_owned_cache_compose.py` validates synthetic configuration
without printing it. It checks no unrelated service/configuration changes,
private Redis isolation, both replicas and compatibility with Warehouse and the
teammate cache overlay. An optional `--ha-overlay <path>` checks the reviewed
owned HA candidate without activating or copying it.

The acceptance driver builds/publishes nothing. Supply locally tested owned
images and a helper image containing Python, grpcio, grpcio-tools and protobuf
(the run used grpcio/grpcio-tools 1.71.0 and protobuf 5.29.4):

```text
python scripts/verify_owned_read_caches.py --applicant-image <local-image> --record-image <local-image> --helper-image <local-python-grpc-tools-image>
```

The isolated run passed **47 checks** using two real replicas of each service,
two independent PostgreSQL databases and two Redis instances. It proves hot
HTTP/gRPC reads, cross-replica updates/deletion, mutation while Redis is paused,
retained old keys that cannot be used after commit, tampering, database failure,
live readiness and credential-free logs. Results go to ignored
`docs-local/owned-cache/live/results.json`. Cleanup affects only its UUID-scoped
containers/networks. Test credentials and private service source are never
exported into CPR. No shared stack, real player data or image pins are changed.

This does not rerun Patroni failover or establish end-to-end Gateway/Session
business acceptance. Grade 5 CPR #188 is merged; owned HA/cache release
publication plus coordinated deployment remain separate gates. The architecture
diagram remains with its owner.

## Review references

- Applicant [issue #41](https://github.com/Andreiisthebest/student-id-applicant-service/issues/41), [PR #42](https://github.com/Andreiisthebest/student-id-applicant-service/pull/42), source `75c924eb8263a38319ad7822d14fe61593c121fc`.
- Record [issue #41](https://github.com/Andreiisthebest/student-id-university-record-service/issues/41), [PR #42](https://github.com/Andreiisthebest/student-id-university-record-service/pull/42), source `c528526d596ec9a68b834debae9187a810b5fffa`.
- Shared [issue #189](https://github.com/m3ower/faf-student-id-please/issues/189).

These are feature source revisions, not release digests. The private source stays
in its owner repositories; CPR contains configuration and public specifications.
