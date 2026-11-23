# Cache sharding with consistent hashing (Lab 5)

> **Lab task.** Research consistent hashing. Scale up the caching solution to implement
> sharding based on consistent hashing. (If you use the ready-made Redis solution, be able to
> compare in detail the differences between the two algorithms.)

Moderation and Discord DMs shard their caches over three independent Redis nodes each. A
**client-side consistent-hash ring with virtual nodes**, written in both services, decides
where each key goes. This page has three parts:
1. what consistent hashing is;
2. how we implemented it, and what we measured;
3. a detailed comparison with the ready-made alternative, Redis Cluster.

It is opt-in through `docker-compose.cache-sharding.yml`, used instead of
`docker-compose.cache.yml`, and needs `lab3-0.13.0` of both services.

## 1. Research: consistent hashing

### The problem with `hash mod N`

To spread keys over `N` cache nodes, the obvious rule is `node = hash(key) mod N`. It spreads
evenly, but the moment `N` changes, almost every key's answer changes:
- going from 3 to 4 nodes moves a key unless `h mod 3 = h mod 4`, which happens for only about
  1 key in 4;
- so about **75%** of the cache suddenly sits on the wrong node.

For a cache, that means a near-total miss storm, which puts the full load on the database at
once.

### The ring

Consistent hashing (Karger et al., 1997) maps both keys and nodes onto the same circular hash
space, here 0 to 2⁶⁴−1:

1. **Nodes:** each node is hashed to a point on the ring.
2. **Keys:** a key is hashed to a point, and belongs to the **first node clockwise** from it,
   at or after its hash, wrapping around at the top.

**When a node is added,** it takes over only the arc between itself and the previous node:
those keys move to it, and nothing else moves. **When a node is removed,** only its keys move,
to the next node clockwise. On average **K/N keys** move instead of almost all of them.

### Virtual nodes

With one point per node, the arcs are random lengths, so one node can own far more of the
ring than another. The fix is **virtual nodes**: each physical node is placed `V` times, at
`hash("<node>#0")` through `hash("<node>#V-1")`. Each node then owns many small arcs, and the
total evens out as `V` grows (the spread shrinks roughly as 1/√V). Virtual nodes also mean that
a node which leaves hands its keys to *all* the remaining nodes, not just one neighbour.

## 2. Our implementation

| | |
| --- | --- |
| Hash | MD5 of the UTF-8 string; the first 8 bytes, big-endian, compared as an **unsigned** 64-bit number (the "ketama" convention). Stable across processes, replicas and languages, unlike Java's `hashCode` or Go's map hash. |
| Node identity | Its stable service name, `host:port` (`moderation-cache-2:6379`), never an IP |
| Virtual nodes | 160 per node (`MODERATION_CACHE_VNODES`, `MEMBERSHIP_CACHE_VNODES`) |
| Lookup | Binary search for the first point ≥ `hash(key)`, wrapping to the first point |
| Hash tags | As in Redis Cluster: a key containing `{tag}` is placed by `tag` alone |
| Code | Moderation `cache/HashRing.java`, `cache/ShardedCacheStore.java`; DMs `internal/cachering/ring.go`, `internal/session/cached.go` |

**Same ring in Java, Go and Python.** The two services implement the same function in two
languages. An independent Python implementation computed golden key-to-node mappings, and both
test suites pin them, so all three implementations provably agree.

### Decisions that make sharding safe for these caches

- **Hash tags keep a group together.** Moderation invalidates by *generation*: a group's
  counter (`gen:{policies}`) versions every cached view of it (`{policies}:list:g…`). The tag
  places the counter and its views on one node, so a node failure never splits a group.
- **Generations start at a random value, never 0.** A node that restarts empty (no
  persistence), evicts a counter (LRU), or newly owns a group after the ring changes starts a
  fresh counter. It can therefore never point back at an old entry.
- **A dead node only turns its own keys into misses.** The cache is not a source of truth: a
  miss is answered from PostgreSQL or Session. Only the failing node is skipped for 5 s, the
  others keep caching, and `GET /status` lists every node and whether it is `suspended`.
- **No automatic re-mapping on failure.** Moving a dead node's keys elsewhere automatically
  could split a group's counter and serve stale views when the node returns. Ring membership
  changes only through configuration.
- **One set of nodes per service.** Moderation's `moderation-cache-1..3` and DMs'
  `dms-cache-1..3` are separate, each with its own password, as with our private databases.
  DMs' main Redis (channels, history; replicated with Sentinel) is not sharded. Only its
  membership cache moves to the ring.

### Measured

Over 100,000 keys, from the test suites, which assert these bounds:

| Measure | Consistent-hash ring | `hash mod N` |
| --- | --- | --- |
| Keys moved when a 4th node is added | **21.9%** (ideal 25%), every one *to the new node* | **75.1%** |
| Keys moved when a node is removed | Only that node's keys | Almost all |
| Worst node's deviation from an even third, 160 vnodes | **9.2%** | (even) |
| Same, 1 vnode per node | 56.9% | |

**Live,** with two Moderation replicas on a real 3-node Redis ring, in front of PostgreSQL
(5/5 checks, no secret in any log):
- 300 applicants' cached facts were spread **119 / 95 / 86** over the nodes. A small sample
  is lumpier than 100,000 keys.
- No group's counter and views were ever split across nodes.
- Replica B hit what replica A cached, and a write on B was seen by A's next read.
- With one node stopped, every request was still 200. All 60 reads of groups on the other
  nodes were hits, and only the stopped node was marked suspended.
- The node came back empty and cached again, with nothing stale.

## 3. Comparison with Redis Cluster

Redis Cluster is the ready-made sharding of Redis itself. It does **not** use a consistent-hash
ring.

| | Our consistent-hash ring | Redis Cluster |
| --- | --- | --- |
| Key placement | `MD5(key)` on a 2⁶⁴ ring; first node point clockwise | `CRC16(key) mod 16384` gives one of **16,384 fixed hash slots**, and each slot is assigned to a master |
| Balance | Statistical: virtual nodes (160 each) even it out to within ~10% | Explicit: slots are assigned in ranges, so balance is exact by slot count but not by load |
| Adding a node | Automatically takes ~1/N of the keys, only from its ring neighbours | Gets no slots until an operator moves some (`redis-cli --cluster reshard/rebalance`) |
| Moving data | None: a cache re-fills on a miss | Slot migration moves the keys (`MIGRATE`), live, with `ASK` redirects during it |
| Who routes | The client computes the node; servers know nothing of each other | Cluster-aware clients cache the slot map; a wrong guess gets `MOVED` / `ASK` and is redirected |
| Membership and failure | Static configuration; a dead node's keys are misses | Gossip bus between nodes; replicas are promoted automatically when a master fails |
| Replication | None (it is a cache) | Each master can have replicas |
| Keeping keys together | `{tag}` hash tags (implemented the same way) | `{tag}` hash tags; multi-key commands only within one slot |
| Multi-key operations | Only within one node, which hash tags make possible | Only within one slot (`CROSSSLOT` error otherwise) |
| Databases | Any `/db` per node | Only database 0 |
| Clients | Any plain Redis client (Jedis, go-redis); ring code in the service | Needs cluster-aware clients (JedisCluster, go-redis `ClusterClient`) |
| Operations | N independent Redis servers | At least 3 masters (6 nodes with replicas), cluster bus port +10000, `cluster-enabled`, slot management |

**Why slots instead of a ring?** Fixed slots make ownership an explicit, small table (16,384
entries) that every node and client can agree on and that can be moved one slot at a time.
That is what lets Redis Cluster migrate *data* safely, replicate, and fail over, because it is
a database, not just a cache. A consistent-hash ring needs no shared table at all. Placement
is a pure function of the node names, so any client computes it with no coordination. That is
exactly right for a cache, where a moved key only costs a miss.

**Why we chose the ring.** Our PostgreSQL databases stay the source of truth (and are
replicated separately, see `docs/moderation-dms-replication.md`), so cache nodes need no
replication or data migration. The ring shows the algorithm the lab names, works with the
clients we already use, and runs on plain Redis containers. Redis Cluster would be the better
choice where the cache data itself had to survive a node failure, or where an operator wants
explicit control over which node holds what.

## Run and show it

Add `.env.cache-sharding.example`'s variables to the private `.env`, then:

```bash
F="-f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.cache-sharding.yml"
docker compose --env-file .env $F up -d
# Both replicas report the same ring and every node:
docker compose $F exec moderation-cache-1 wget -qO- http://moderation-service:8080/status | grep -o '"cache":{.*\]}'
# Keys are spread over the three nodes:
for n in 1 2 3; do docker compose $F exec moderation-cache-$n redis-cli dbsize; done
# One node down: nothing fails; only its keys miss, and /status shows it suspended.
docker compose $F stop moderation-cache-2
```

## Not verified

The containers of this overlay were not started, because Docker does not run on the verifying
machine. `docker compose config` of the overlay is valid, alone and after the replication
overlay. The rings were verified by the services' test suites and the live run above, against
real Redis processes.
