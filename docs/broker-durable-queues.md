# Broker durable queues and dead letters

Lab 4 Task 9 implementation candidate: Broker 0.7.0. Publication and full-stack
acceptance are separate release steps. No service payload, topic, consumer group,
gRPC signature, delivery receipt or authentication credential changes.

## Storage and delivery

The Broker persists acceptance, dispatch intent and per-group receipts to SQLite
WAL with FULL synchronization. The opt-in `docker-compose.owned-broker.yml`
mounts `broker-data:/data` and sets `BROKER_STATE_PATH=/data/broker.sqlite3`.
One process exclusively owns this journal; do not share it across Broker replicas.
Source runs must explicitly configure a persistent path. Empty disables durability
for disposable tests only. Do not delete volumes (`down -v`) to restart a system
whose accepted messages must survive.

HTTP and gRPC publications use the same queues. PENDING/202 means persisted
acceptance, not processing success. Existing exact processing receipts remain
required from every group. Recovery preserves message IDs, owner scope, partial
receipts and effective deadlines. Only never-started work within its original
deadline and unchanged catalog resumes. Unknown started deliveries become
`DELIVERY_OUTCOME_UNKNOWN` dead letters; expired groups become
`DEADLINE_EXCEEDED`; a changed catalog produces `CATALOG_CHANGED`.

No blind replay of ambiguous business mutations, fresh deadline on restart or
automatic retry after a refusal/timeout is added. Existing connection-only
failover and publisher-owned outboxes/business deduplication remain. A later
transport attempt must preserve the immutable business identity and reconcile
any unknown outcome. Task 10 availability is separate.

Dead letters survive result-retention expiry. Capacity defaults to 8192 groups,
configured with `BROKER_DEAD_LETTER_CAPACITY` (1..65536). Pending groups reserve
capacity; saturation rejects new admission with 429
`DEAD_LETTER_CAPACITY_REACHED` instead of dropping failures. No automatic
dead-letter eviction, HTTP replay or delete API is introduced. Operators reconcile
and archive privately offline. Disk errors fail closed with 503
`DURABLE_STORAGE_UNAVAILABLE` and readiness DOWN; corrupt/locked/incompatible
storage prevents startup. Successful terminal inputs are scrubbed; failed input
and processing results remain private business data in the volume. Protect volume
access/backups. This is not replicated storage or exactly-once delivery.

## Internal listing endpoint

`GET /internal/v1/messaging/dead-letters?after=0&limit=50`

Use the existing caller-specific `Authorization: Bearer <service-token>`. The
verified service sees only its own publications. Missing/invalid auth: 401.
Gateway identity: 403 (this is not a user route). No payload, response body,
credential or message header is returned. Existing trace/error envelopes apply.

```json
{
  "items": [{
    "id": 1,
    "messageId": "55555555-5555-5555-5555-555555555555",
    "correlationId": "66666666-6666-6666-6666-666666666666",
    "traceId": "example.trace",
    "topic": "event.DecisionRecorded.v1",
    "queue": null,
    "group": "session-service",
    "status": 503,
    "reason": "DELIVERY_OUTCOME_UNKNOWN",
    "failedAt": 1800000000.0,
    "attempts": 1
  }],
  "nextAfter": null
}
```

`failedAt`: UTC Unix seconds. `attempts`: 0 before dispatch, 1 after dispatch
intent, not proof of receipt. Follow `nextAfter` as the next `after` cursor;
null means no next page currently. `after`: integer 0..9223372036854775807;
`limit`: integer 1..100. Unknown/duplicate/invalid parameters return 400
`INVALID_QUERY`. Storage unavailable returns 503. Empty listing is 200 with an
empty array and null cursor. This HTTP operational endpoint adds no broker topic
or business RPC; gRPC Publish/GetResult retain their current contract.

## Release and verification

The Broker's `tests/test_durable.py` tests actual SQLite restart and abrupt exit,
receipts, deduplication, deadline expiry, ownership, capacity and failure behavior.
Run its complete coverage/image checks before release. Deploy only the published
reviewed image selected through `OWNED_BROKER_IMAGE`. This document does not
assert publication, live cross-owner delivery or durable consumer-side state.
Discovery remains a separate volatile registry; re-register services if it restarts.
