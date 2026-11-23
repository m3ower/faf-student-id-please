# Moderation and Discord DMs: caching (Lab 5)

Lab 5 asks for caching of "commonly accessed GET requests and authentication data (sessions,
tokens, or user lookups)". Both services cache in Redis, shared by all their replicas. Caching
is opt-in through `docker-compose.cache.yml`, and needs Moderation and DMs `lab3-0.12.0`.

| | Moderation | Discord DMs |
| --- | --- | --- |
| Cache | `moderation-cache`: a Redis of its own, no persistence, 64 MB, LRU | The Redis DMs already uses (single, or Sentinel with the replication overlay) |
| Commonly accessed GETs | Penalty policies (list, single, effective matrix); decision facts that Rules asks for on every evaluation | Its data already lives in Redis; what its GETs waited on was authorization |
| Authentication data | Session membership (reads) | Session membership (REST reads, WebSocket handshake) |

## What is cached and how it stays correct

### Moderation

- **Penalty policies.** `GET /api/v1/penalty-policies`, `/effective` and `/{id}`, plus the
  penalty looked up for every decision. Uncached, the effective matrix is 12 database lookups.
  Each policy write bumps the `policies` generation after its transaction commits.
- **Decision facts.** `GET /internal/v1/moderation/applicants/{id}/decision-facts`, which
  Rules calls (through the Broker) for every applicant it evaluates. Recording or voiding a
  decision about that applicant bumps its own generation.
- **Membership.** Session's membership answer, used by reads such as
  `GET /api/v1/decisions/session/{id}`. Otherwise every request calls Session through the
  message broker.

### DMs

- **Membership.** Session's membership answer for `GET /api/v1/channels`, `/channels/{name}`,
  `/history` and the WebSocket handshake. Without the cache, every request asks Session through
  the message broker.

### Rules for both services

- **Generations instead of deletes.** A cached view is stored under its group's current
  generation. A write bumps the generation after its transaction commits. A reader that loaded
  old data just before the bump stores it under the old generation, which nobody reads again,
  so a write on any replica is visible to the next read on every replica.
- **Writes never trust a cached membership.** Decisions, voids, appeals, messages and channel
  changes always ask Session, and replace the cached answer. Reads may trust a cached "member"
  for 30 s and a "not a member" for 5 s. A failed lookup is never cached. So a removed player
  is stopped on their next write, and DMs' WebSocket re-check still closes their socket on
  time.
- **The cache never fails a request.** An unreachable, slow (Moderation: 250 ms timeout) or
  unreadable cache is a miss, answered from PostgreSQL, Redis data or Session. After a failure
  the cache is skipped for 5 s, so requests do not each pay its timeout.
- **What is observable.** `GET /status` of both services adds `"cache": {"enabled", "hits",
  "misses", "errors"}`; Moderation's also has `"store"`. Logs: `cache.configured`,
  `cache.unavailable` and `cache.resumed`, with the error type only.

## Run

Add `.env.cache.example`'s variables to the private `.env`, then:

```bash
F="-f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.cache.yml"
docker compose --env-file .env $F up -d
```

With replication as well, list `docker-compose.replication.yml` before
`docker-compose.cache.yml`, and use the same `lab3-0.12.0` for both overlays' versions.

### Show it

```bash
# Hits climb on repeated reads; a policy write is seen at once by both replicas.
docker compose $F exec moderation-cache wget -qO- http://moderation-service:8080/status | grep -o '"cache":{[^}]*}'
# What is in the cache: views under generations, membership entries with a TTL.
docker compose $F exec moderation-cache redis-cli --scan --pattern 'moderation:cache:*'
docker compose $F exec dms-redis redis-cli --scan --pattern 'dms:cache:membership:*'
# The cache going away fails nothing: requests keep answering from the source.
docker compose $F stop moderation-cache
```

## Verification

The test suites ran in each service's CI.

**Moderation:** `mvn verify`, 215 tests, 91.2% line coverage.
- **`CacheEnabledTest`:** on the real application, cached views ignore a change made behind
  the service's back, and the service's own writes (create, update, delete, decision, void) are
  seen by the very next read.
- **Membership:** answers are cached, writes always ask Session, and an outage is never cached.
- **An unreachable cache** fails no request.
- **The Redis store** was tested against a real Redis. CI now runs that test against a Redis
  service.

**DMs:** `go test -race`, 76.6% total coverage.
- **The membership cache:** expiry, the short refusal TTL, failures never cached, fresh
  lookups, a Redis outage and unreadable entries.
- **Through the real router:** 6 reads cost one Session call, a revoked player's write is
  refused at once, and an open WebSocket is still closed by the periodic re-check.

**Live run:** two Moderation replicas sharing one real Redis, with real PostgreSQL. 5/5 checks
pass, and no secret appeared in any log.
- **Hits:** reads are served from Redis.
- **Shared invalidation:** a change made directly in the database is not seen while cached,
  and a write through replica B is seen by replica A's next read.
- **Speed:** the effective matrix answers in 1.23 ms cached against 2.90 ms uncached (medians,
  one persistent connection each, interleaved).
- **Outage:** with Redis stopped, every request still answers 200, and caching resumes when
  Redis is back.

**Not verified:**
- **Containers:** the containers of this overlay were not started, because Docker does not run
  on the verifying machine. `docker compose config` of the overlay, alone and after the
  replication overlay, is valid.
- **DMs live:** DMs' membership cache was not run live, because that needs a reachable Session
  through the Broker. It is covered by the router-level tests against a Redis implementation.
