# Lab 4 subscriber queues and topic messaging

Review candidate for CPR #145, Discovery #38, Broker #15 and Gateway #57.
Implementation in these branches does not establish merge, publication, deployment,
or adoption by the eight individual services. No Compose/image pins change here.

## Ownership and release order

1. Release Discovery's additive subscriptions and readiness observations first.
2. Release Broker 0.4.0 with the reviewed bindings bundled in its image.
3. Release Gateway lab4-2.1.0, which requires the new Broker queue API.
4. Each owner adopts its subscription list and topic clients, tests against the
   shared candidate, then publishes its services. Existing business handlers,
   authorization, schemas, persistence, hashes and outboxes remain owner-managed.
5. Promote image pins/Compose separately and verify the real full stack. Source
   tests with receiver doubles do not prove individual integrations or publication.

This is a custom Python Broker, not RabbitMQ/Kafka. Existing business HTTP routes
remain available on Broker during this migration; topic clients never fall back
to them. Gateway exposes no internal business routes, balancing or circuit state.
Durability, dead letters, gRPC, load-based routing and thread-per-request are
separate tasks. Queues/results/deduplication are in memory in one Broker process.

## APIs and trust

Private APIs at `BROKER_URL`, with `Authorization: Bearer <caller credential>`,
`Content-Type: application/json`, `X-Trace-Id` equal to envelope `traceId`:

| Method/path | Caller | Result |
| --- | --- | --- |
| `POST /internal/v1/messaging/requests` | Gateway only | Service-addressed request/reply |
| `POST /internal/v1/messaging/publications` | Authenticated service only | Operation-topic request/reply or event-topic publication |
| `GET /internal/v1/messaging/results/{messageId}` | Original authenticated caller | `202` while pending, `200` when terminal, `404` if absent/expired/not yours |

Gateway result ownership also includes the verified player UUID: supply its
`X-Player-Id` when polling a protected public request. Service result ownership
ignores player headers. Results contain private business bodies and are never
published through Gateway. TLS is required outside the trusted container network.

Caller identities use Broker's existing distinct `BROKER_CALLER_TOKENS_JSON`
entries. Broker enforces the reviewed publisher/caller/group table, then sends
the existing target bearer and authenticated `X-Service-Name` to the receiver.
Topic registration is not an authorization grant. Discovery still uses one
shared machine credential: authorized registry writers are trusted, not independently
authenticated as a service. No new per-service registration identity is claimed.

User JWTs never reach Broker. Gateway alone supplies verified player identity;
spoofed credentials/identity/hop headers are stripped. Receivers keep resource
authorization. No publisher-supplied target URL, callback URL, subscriber list or
arbitrary topic creation API exists.

## Envelope and payload projection

```json
{
  "messageId": "10000000-0000-0000-0000-000000000001",
  "schemaVersion": 1,
  "kind": "request",
  "topic": "operation.session.verifyMembership.v1",
  "traceId": "messaging.example",
  "correlationId": "10000000-0000-0000-0000-000000000002",
  "deadlineAt": "2030-01-01T00:00:01Z",
  "payload": {
    "sessionId": "55555555-5555-5555-5555-555555555555",
    "playerId": "22222222-2222-2222-2222-222222222222"
  }
}
```

IDs are nonzero UUID strings. `causationId` is optional. `deadlineAt` must carry
a UTC offset; examples use future timestamps for illustration, not live budgets.
Exactly one nonempty `topic` or `queue` is required. Extra envelope fields,
duplicate JSON keys and non-finite numbers are rejected. Maximum wire envelope:
96 KiB. Business handlers still validate their own payload schemas.

`operation.<exact catalog operation name>.v1` always has `kind=request`, one
reviewed consumer group, and the same method/path/body/result as that operation:

- POST with a body: `payload` is the original JSON body. UUIDs in URI templates
  go in the envelope's `arguments` object. No body is injected or renamed.
- GET: `payload` contains exactly the named UUID path/query arguments;
  `arguments` is empty. Broker substitutes the fixed path/query template; it
  never guesses a URI from a body or forwards a publisher-chosen query.
- POST without a body: `payload` is absent/null, URI UUIDs are in `arguments`.
  Example: `operation.credential.initialization.recover.v1` uses
  `arguments:{"eventId":"<uuid>"}`.

The exact mappings are in [catalog.json](../contracts/messaging/catalog.json).
The existing [HTTP catalog](../contracts/http/service-operations.json) remains
the authority for receiver methods, schemas, caller permissions and semantics.
Generate/check mappings with `python scripts/validate_messaging_contracts.py`;
after an agreed business-catalog change use `--write`, then update Broker's
bundled copy in its reviewed PR. `--broker-root PATH` checks both copies.

Gateway uses `queue:service.<canonical service-name>.v1`, `kind=request`.
Its payload is `{method,path,query,bodyBase64,headers:[[name,value]],playerId}`.
`path` is the original encoded `/api/v1/...` path, `query` excludes `?`, body is
base64 bytes (64 KiB decoded maximum), headers retain duplicate HTTP values.
Broker verifies the route actually belongs to that queue. Anonymous routes omit
player identity. Replies preserve the business HTTP status/body, cookies,
redirects, HEAD and application headers; the browser never receives a queue ID
instead of its business result. Reply body limit is 1 MiB, headers 8 KiB.

## True event fan-out and acknowledgments

| Topic | Producer | Independent required groups |
| --- | --- | --- |
| `event.DecisionRecorded.v1` | moderation-service | session-service, discord-dms-service |
| `event.ShiftStarted.v1` | session-service | discord-dms-service |
| `event.CredentialsReady.v1` | credential-service | applicant-service, university-record-service |
| `event.SessionCompleted.v1` | session-service | player-service |
| `event.PlayerProgressed.v1` | player-service | session-service |

Use `kind=event`, `topic` above, and put the **entire existing business envelope**
`{eventId,type,occurredAt,producer,version:1,payload}` in the transport `payload`.
Broker verifies the producer/type/version and routes unchanged JSON to each
group's existing handler. Replicas compete within a group; there is one
delivery per group, not one per replica. All required groups must have an
eligible registration at admission, so a missing group refuses publication
before any fan-out. Later failures may still produce partial results.

Full ApplicantInitialized and Credential's seed-only initialization have
incompatible wire shapes. They remain separate `operation.applicant.initialize.v1`,
`operation.record.initialize.v1` and `operation.credential.initialization.accept.v1`
bindings with owner-managed adapters and receipt validation; no generic
`event.ApplicantInitialized.v1` broadcast is invented. Consumers must not
republish initialization and create loops.

Publication initially returns `202` while pending. Poll the result until every
required group is terminal. A group processing acknowledgment requires HTTP 200,
matching business `eventId`, and `status:PROCESSED|DUPLICATE`; CredentialsReady
instead requires matching `eventId` and `accepted:true`. ACK only after the
receiver commits its transaction. A 202/mismatched/malformed receipt is **not**
processing success. For request/reply, `acknowledged=true` only means the HTTP
operation returned a 2xx; its business status/receipt may still require follow-up.

```json
{
  "messageId": "10000000-0000-0000-0000-000000000001",
  "correlationId": "10000000-0000-0000-0000-000000000002",
  "state": "COMPLETED",
  "groups": {
    "session-service": {
      "state": "SUCCEEDED", "acknowledged": true, "status": 200,
      "bodyBase64": "eyJtZW1iZXIiOnRydWV9",
      "headers": [["content-type", "application/json"]]
    }
  }
}
```

`state` is PENDING, COMPLETED or FAILED. Pending groups contain only
`{state:PENDING,acknowledged:false}`. Terminal groups add the original status,
base64 body and header pairs; group state is SUCCEEDED or FAILED. COMPLETED means
all groups acknowledged; FAILED means every group is terminal and at least one
did not. Internal body replies are bounded to 16 KiB. Business refusals, including
DMs `409 SESSION_CHAT_NOT_INITIALIZED`, remain unchanged in their group result.

## Discovery subscriptions and readiness

Each business replica adds `subscriptions:[{topic,group}]` to its existing startup
registration. Exact per-owner arrays are generated in
[subscriptions.json](../contracts/messaging/subscriptions.json), including both
operation and event subscriptions. All entries use the canonical service name
as group. Replicas of one service use identical subscriptions and distinct
instance UUIDs/reachable origins. Omitted subscriptions mean `[]`; max 64 unique
entries, no extra subscription fields, existing 4096-byte registration limit.
New subscriptions require the new Discovery release; old Discovery rejects them.

The authenticated instance listing adds server-owned
`readiness:{ready,checkedAt,validUntil}`. Discovery separately queries `/health/ready`
with bounded workers/timeouts/bodies; only HTTP 200 `{status:"UP"}` (and matching
`service` if supplied) marks ready. Missing/failed observations, expired validity,
future timestamps or samples older than 30s fail closed in Broker. The registry
POST never accepts caller-supplied readiness. Refresh uses the existing
`DISCOVERY_POLL_INTERVAL_SECONDS`, timeout and concurrency settings; validity is
two intervals plus probe timeout. Keep interval+scan duration below 30s. Disabling
polling means no eligible queue/stream targets. Initial registration can take a
poll cycle to become eligible. Pressure polling/notifications/circuit removal
remain separate and retain their existing behavior.

Selection also checks the exact topic/group pair and Broker's existing per-instance
circuit; public queues require readiness but no topic subscription. Registration
alone is not readiness. Re-registration invalidates the old observation; stale
in-flight probes cannot mark the replacement ready. Registry restart still loses
registrations; services must re-register/restart. No heartbeat or persistence is
claimed.

## Bounds, deadlines, retry and cancellation

Default per `(topic or queue,group)` waiting capacity256, global queued deliveries
4096, retained result records4096, reserved message/result memory64 MiB,
admission/waiters4096; each lane admits at most256 concurrent submissions.
One async worker per lane by default (`BROKER_GROUP_WORKERS`, max 16). These are
fixed bounded workers, **not** the later thread-per-request implementation.
Different operations have independent workers so a parent awaiting a nested
operation does not hold its child's only worker. Avoid synchronous self-cycles.

Broker's absolute deadline covers preflight Discovery lookup, queue waiting and
delivery. It is capped by `BROKER_OPERATION_TIMEOUT_SECONDS`/catalog budget
(default 750ms) or public timeout 4s, task deadline 5s, and pending maximum 30s.
Result retention is 60s after completion. Configurable bounds are documented in
Broker's environment example; `/status.messaging` exposes counts/bytes, not bodies.
Expiry gives group504. Client cancellation removes work not yet started; already
started work is ambiguous and stays bounded by its deadline. Shutdown cancels
workers. No delivery may start after its deadline.

Broker forwards trusted `X-Deadline-At`, `X-Message-Id`, `X-Correlation-Id` and
optional `X-Causation-Id`, plus the original trace. Receivers must validate and
cap the parent deadline and derive any child deadline from remaining time. The
receiver must never trust these fields from public clients. Existing 400ms/1s
caller budgets are not enlarged: callers subtract their own elapsed work and
reserve time for result polling. Adoption of this cross-hop contract is part
of each owner's individual implementation, not already proven by shared code.

Identical messageId + envelope under the same caller/player returns the retained
result without redelivery; different content yields409 MESSAGE_CONFLICT. Reusing
an ID with a different deadline is different content. Repeating an in-flight
request returns202; poll it. After a known terminal failure/expiry, use a new
transport messageId/deadline while retaining the immutable business eventId/
requestId. Delivery itself only fails over once if a connection was never
established. No timeout/5xx/business conflict is automatically replayed. Publishers
own durable retry/outboxes and consumers own durable business deduplication.
For partial fan-out, a new publication may redeliver to a previously acknowledged
group; that group must return its persisted DUPLICATE receipt without effects.

Broker restart discards queues/results/dedup. A result404 after restart/retention
is **unknown delivery**, never proof of non-delivery. Producers retain their
durable outboxes and reconcile/retry by business IDs. Task 9 durability remains
unfinished; never clear an outbox on Broker 202, merely HTTP 2xx, or a missing result.

| HTTP | Ingress error code |
| --- | --- |
| 400 | INVALID_MESSAGE, TRACE_ID_MISMATCH, INVALID_ARGUMENTS, UNEXPECTED_PAYLOAD, INVALID_EVENT, INVALID_PUBLIC_REQUEST, STREAM_NOT_QUEUEABLE, INVALID_MESSAGE_ID |
| 401/403 | UNAUTHENTICATED / CALLER_NOT_ALLOWED |
| 404 | TOPIC_NOT_FOUND, QUEUE_NOT_FOUND, RESULT_NOT_FOUND |
| 409 | MESSAGE_CONFLICT |
| 413 | MESSAGE_TOO_LARGE |
| 429 | MESSAGE_CAPACITY_REACHED |
| 503 | NO_READY_SUBSCRIBERS, BROKER_STOPPING, SERVICE_AUTH_NOT_CONFIGURED |
| 504 | DEADLINE_EXCEEDED |

Ingress errors use the existing shared envelope. Once accepted, delivery failures
appear inside group results with original status/body, not as false successful
business calls. Gateway unwraps that status/body for browsers.

## Streaming exceptions and owner handoff

Session SSE remains the established HTTP streaming relay through Gateway/Broker,
with separate stream lifetime/capacity. DMs negotiation remains an authenticated
Broker selection followed by a direct browser WebSocket to DMs. Both select
fresh-ready instances; frames are never queued or replayed. Their existing
reconnection, authorization and shared Session/DMs state requirements remain.

Send each owner [messaging-owner-handoff.md](messaging-owner-handoff.md) after the
reviewed shared schemas are available. Moderation's unused caller grants
(session-state.get, applicant.getProfile, applicant.getClaims, rules.shift.read,
credential.validateApplicant) are removed in a separate reviewed catalog change.
The remaining pending business-catalog issue: CredentialsReady receivers require1-32 unique nonzero credential
UUIDs, which the existing business schema does not fully express. Preserve that
receiver validation and agree its separate schema correction.
