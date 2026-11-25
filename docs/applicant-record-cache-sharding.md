# Applicant and Record: consistent-hash cache sharding (Lab 5 Grade 7)

Candidate **1.7.0** scales each owned Grade 6 cache into three independent Redis
instances. Applicant and Record keep separate stores/networks/credentials: six
Redis instances in total. Teammate caches, Broker, Discovery, business transports
and the architecture diagram are unchanged. This is source/deployment preparation,
not a claim of a published image or full team deployment.

## Ring protocol

Each process constructs an immutable sorted ring. The default is 128 virtual
nodes per physical node (384 points for three nodes); allowed values are 16..1024
and 1..16 physical nodes. Configuration is:

```text
CACHE_REDIS_NODES=a=cache-a:6379,b=cache-b:6379,c=cache-c:6379
CACHE_VIRTUAL_NODES=128
```

Stable lowercase IDs are independent of addresses. Duplicate IDs, duplicate
endpoints and invalid bounds fail startup when caching is enabled. Lists may be
reordered without changing ownership. Legacy single-node settings still work
when the list is blank. Membership and virtual-node count must match on all
replicas. Node identities are local cache configuration, not business topics.

Both Java and Go hash UTF-8 bytes with full SHA-256:

- Node point: `owned-cache-ring-v1\nnode\n<ID>\n<zero-based decimal virtual index>`.
- Key point: `owned-cache-ring-v1\nkey\n<complete physical cache key>`.
- Compare unsigned 256-bit values (equivalently lowercase fixed-length hex).
  Choose the first token greater than or equal to the key point, wrapping to
  the first token if needed. Hash collisions are rejected at construction.

Build cost is O(NV log(NV)), lookup is O(log(NV)), ring space is O(NV).
Virtual nodes spread each physical owner's ranges around the ring. They reduce
imbalance; they do not split a single hot key, guarantee equal load, replicate
values or increase a node's memory. The existing key includes a database
generation and hashed identity. A generation change can route the new projection
to a different shard, which is safe because the old key is unreachable.

The common fixture `contracts/cache/hash-ring-v1.json` is copied into both owned
test suites; SHA-256 is
`5ffd1bdc5cb8f5505cdbb7fe76d93b4cd72e22de6a99da7c39b357350c81af71`.
An independent Python oracle checks it in CPR CI. Unicode examples ensure Java,
Go and Python agree on encoding; tests also cover exact points and wraparound.

## Membership changes and failures

Adding node `d` changes only keys that `d` now owns; removing `c` changes only
keys previously owned by `c`. Address replacement under the same ID leaves the
ring unchanged but the replacement cache begins cold. Membership is explicit
and fixed at startup. No node is automatically removed because a request fails.
Change the list consistently across application replicas, allow lazy source
refill and let obsolete entries expire. No cache value migration is required.
Changing IDs, the hash protocol or virtual-node count can cause broader movement.

Each owner has an independent cooldown. A missing/slow/failed Redis owner falls
back to the database or live authorization source, without trying a different
shard. Healthy owners remain usable. On recovery the same owner resumes hits
or refills on a miss. These are independent caches, **not Redis replication or
automatic cache failover**. There is no Redis Cluster protocol or Sentinel.
One shard's loss reduces cache capacity, not durable business data availability.

All Grade 6 protections remain: transactional UUID generation fences across
replicas, 30-second projection TTL, bounded signed entries, private credentials,
no stale data during database outage, and no cached readiness/receipts/outboxes
or deception keys. Record's explicit membership denials use the same ring and
one-second TTL; positive grants always stay live. No authorization decision is
relaxed by sharding. Existing cache I/O and business deadlines are not reset.
`/status.cache` adds `shards` and `virtualNodes` to existing per-process counters.

## Comparison and research

[Karger et al., Consistent Hashing and Random Trees (1997)](https://www.cs.princeton.edu/courses/archive/fall09/cos518/papers/chash.pdf)
introduces consistent hashing for distributed caching. Our implementation is a
small centralized client ring, not a distributed membership/DHT protocol.

| Approach | Key mapping | Membership changes | Coordination |
| --- | --- | --- | --- |
| Hash modulo number of nodes | `hash(key) % N` | Changing N remaps most keys | All clients need the same ordered list |
| This virtual-node ring | SHA-256 key to clockwise virtual node | Add/remove affects only the new/removed owner's ranges | Explicit startup configuration on every client; cold source refill |
| Redis Cluster | CRC16 key to one of 16,384 fixed slots, then slot owner | Slot ownership is explicitly moved; slot number stays fixed | Cluster topology, MOVED/ASK redirects, slot migration and optional replica failover |

Redis Cluster's fixed slot indirection is different from placing node tokens on
our hash ring. It does not compute `hash(key) % current-node-count`. Its hash tags
support same-slot multi-key operations; our cache performs only single-key
commands and does not implement slot tags or redirects. See the
[official Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).

For the deterministic `population-0`..`population-19999` experiment with 128
virtual nodes: `a=6885`, `b=6916`, `c=6199` keys. Adding `d` moves **4605/20000
(23.025%)**; removing `c` moves **6199/20000 (30.995%)**, all from `c`. The simple
modulo-3 versus modulo-4 illustrative test changes 75% of integer bucket inputs.
These are test distributions, not live workload or performance guarantees.

## Compose and release procedure

Append `docker-compose.owned-cache-sharding.yml` **last**, after the base,
owned-Broker, optional Warehouse/HA, and Grade 6 `docker-compose.owned-cache.yml`.
It retains the existing `*-read-cache` as stable ID `a` and adds `-b` and `-c` on
the same owner's private network. Each has 64 MB LRU, no persistence, no host
port and the existing authenticated startup script. Total configured cache
memory is 192 MB per service, excluding Redis overhead. Application startup and
readiness do not depend on Redis health.

Add `.env.owned-cache-sharding.example` names to the existing ignored environment.
Set `SHARDED_APPLICANT_IMAGE` and `SHARDED_RECORD_IMAGE` to reviewed 1.7.0+ images,
preferably digests. The preceding Grade 6 image variables are still required;
set them to the same reviewed images. Keep each owner's existing cache password
across that owner's three shards; never share it between owners or with other
business/reporting/database credentials. No actual token belongs in CPR.

```text
docker compose --env-file .env -f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.owned-cache.yml -f docker-compose.owned-cache-sharding.yml config --quiet
```

Validation does not start a deployment. Keep all desired Warehouse/HA overlays
before the two cache overlays. Do not print expanded configurations with secrets.
Removing only the sharding overlay returns to the legacy single-node cache;
values may refill cold. Retaining Grade 7 images is backward compatible. Removing
both cache overlays disables caching by default without deleting business data.

## Verification

The private suites and CPR tests cover deterministic routing, balance, minimal
movement, configuration errors, actual physical owner placement, replica
agreement, failed-owner isolation and preserved Grade 6 behavior. CPR's
`validate_owned_cache_sharding.py` checks all four application replicas, six
private Redis shards, unchanged unrelated configuration and overlay compatibility
with Warehouse, teammate cache and owned HA. `validate_owned_cache_ring.py`
independently checks the common vectors and distribution.

Run the isolated actual-service acceptance with locally built owned images and
the existing Python gRPC helper (grpcio/grpcio-tools 1.71.0, protobuf 5.29.4):

```text
python scripts/verify_owned_cache_sharding.py --applicant-image <local-image> --record-image <local-image> --helper-image <local-python-grpc-helper>
```

It generates fresh credentials, PostgreSQL databases, six Redis instances and
two replicas of each owned service. It performs real HTTP/native gRPC business
requests, checks exact physical placement, peer replica hits, retained old keys
after committed invalidation, corrupted entries, database failure, live readiness,
paused-shard isolation and recovery. Cleanup removes only its UUID-scoped
resources. Sanitized output goes to ignored `docs-local/owned-cache-sharding`.
This does not certify full Gateway/Session gameplay or repeat Patroni failover.
Publication, review and coordinated deployment remain separate.

## Candidate evidence and review references

- Applicant [issue #44](https://github.com/Andreiisthebest/student-id-applicant-service/issues/44), [PR #45](https://github.com/Andreiisthebest/student-id-applicant-service/pull/45), source `fb1b73177156c148d09ffc57e28da5eb02be50d5`. Draft while prerequisite Grade 6 PR #42 remains unmerged; do not merge out of order.
- Record [issue #44](https://github.com/Andreiisthebest/student-id-university-record-service/issues/44), [PR #45](https://github.com/Andreiisthebest/student-id-university-record-service/pull/45), source `4b1d20a684c1f37f455ee47af9f1730927351fc9`.
- Shared [issue #191](https://github.com/m3ower/faf-student-id-please/issues/191).

Applicant's full Maven verification passed **72 tests, 94.5% line coverage**.
Record's full Go race suite passed with **79.4% line / 82.8% statement coverage**.
Both existing >=70% gates pass and both local images build. The isolated actual
owned-service run passed **73 checks** with four application replicas, two
PostgreSQL databases and six independent Redis instances. The synthetic sharded
Compose check passed **89 checks** including Warehouse, teammate cache and owned
HA. The independent ring oracle passed all **57 shared vectors** and 20,000-key
movement/distribution checks. Logs were checked against all generated secrets.

No released 1.7.0 image/digest is claimed. The source revisions identify the
feature candidates tested locally. Review, prerequisite merges, publication and
coordinated deployment are still required before enabling this in a shared stack.
