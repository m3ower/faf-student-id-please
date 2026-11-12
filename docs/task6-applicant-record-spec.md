# Task 6 owner specification: Applicant and University Record

Specification only, checked on 2026-11-12; tracked by
[CPR #143](https://github.com/m3ower/faf-student-id-please/issues/143).
Vasile owns shared Task 6 infrastructure. No subscriptions, new messaging client,
new event transport, deadline header or Discovery extension is implemented by this document.
No credentials or credential values are included.

## Source and contract baseline

- [Applicant repository](https://github.com/Andreiisthebest/student-id-applicant-service),
  broker migration [PR #25](https://github.com/Andreiisthebest/student-id-applicant-service/pull/25)
  merged into dev as `b3036296564b312baf45ff948dc84f88e7318a7b`.
- [University Record repository](https://github.com/Andreiisthebest/student-id-university-record-service),
  broker migration [PR #27](https://github.com/Andreiisthebest/student-id-university-record-service/pull/27)
  merged into dev as `3661467f4a6d7ed8c4c5721dd474e89cd06906d1`.
- Shared migration [CPR #141](https://github.com/m3ower/faf-student-id-please/pull/141)
  merged as `24dbe6a73d9589ae5839a3acd1735a13f9a334c1`; inspected CPR dev is
  `38df07d`, including Gateway handoff #142. Its catalog has 39 operations.
- Canonical [catalog](../contracts/http/service-operations.json),
  [OpenAPI](../contracts/http/openapi.json), [operation examples](../contracts/http/examples/)
  and [hash vectors](../contracts/http/test-vectors/) remain the single source of truth.
  The [current transport evidence](applicant-record-broker-migration.md) reports
  actual Broker/Discovery tests and explicitly distinguishes private-peer acceptance gaps.

## 1. Operations and subscriptions

Confirmed: all 19 owned internal receiver names, methods, paths, request/response
schema references and caller allowlists correspond to the current implementations:
11 Applicant and 8 Record operations. The exact names below are case-sensitive;
do not substitute service names for catalog prefixes or normalize camelCase.
Each running replica will register the same service-level consumer group and its
consumed operation topics using the agreed additive registration schema. One
member of the group processes a message; an acknowledgement is not required from
every replica. Runtime registration is future work after the shared schema lands.

### applicant-service

Consumer group: **`applicant-service`** for all 11 consumed operations.

| Exact operation topic | Existing handler | Request ? response schema |
| --- | --- | --- |
| `operation.applicant.getDeception.v1` | `GET /internal/v1/applicants/{applicantId}/deception?sessionId={sessionId}` | `no body` ? `deceptionResponse` |
| `operation.applicant.generate.v1` | `POST /internal/v1/applicants/generate` | `ownedGeneration` ? `ownedReadiness; 202:ownedReadiness` |
| `operation.applicant.initialize.v1` | `POST /internal/v1/applicants/events/applicant-initialized` | `ownedApplicantInitialized` ? `ownedReceipt` |
| `operation.applicant.getInitialization.v1` | `GET /internal/v1/applicants/{applicantId}/initialization` | `no body` ? `ownedReceipt` |
| `operation.applicant.getReadiness.v1` | `GET /internal/v1/applicants/{applicantId}/readiness` | `no body` ? `ownedReadiness; 200:ownedReadiness, 202:ownedReadiness` |
| `operation.applicant.resumeInitialization.v1` | `POST /internal/v1/applicants/{applicantId}/resume` | `no body` ? `ownedReadiness; 202:ownedReadiness` |
| `operation.applicant.getProfile.v1` | `GET /internal/v1/applicants/{applicantId}/profile` | `no body` ? `ownedProfileResponse; 200:ownedProfileResponse, 202:ownedReadiness` |
| `operation.applicant.getClaims.v1` | `GET /internal/v1/applicants/{applicantId}/claims` | `no body` ? `ownedClaims; 200:ownedClaims, 202:ownedReadiness` |
| `operation.applicant.warmup.v1` | `POST /internal/v1/applicants/warmup` | `ownedWarmup` ? `ownedWarmupResponse; 202:ownedWarmupResponse` |
| `operation.applicant.credentialContext.v1` | `POST /internal/v1/applicants/context` | `ownedApplicantOnly` ? `ownedApplicantContextPort` |
| `operation.applicant.credentialsReady.v1` | `POST /internal/v1/applicants/events/credentials-ready` | `ownedCredentialsReady` ? `ownedReadyAcknowledgement` |

### university-record-service

Consumer group: **`university-record-service`** for all 8 consumed operations.

| Exact operation topic | Existing handler | Request ? response schema |
| --- | --- | --- |
| `operation.record.enrollmentFacts.v1` | `GET /internal/v1/records/{applicantId}/facts` | `no body` ? `ownedRecordFacts` |
| `operation.record.generate.v1` | `POST /internal/v1/records/generate` | `ownedGeneration` ? `ownedReadiness; 202:ownedReadiness` |
| `operation.record.initialize.v1` | `POST /internal/v1/records/events/applicant-initialized` | `ownedApplicantInitialized` ? `ownedReceipt` |
| `operation.record.getInitialization.v1` | `GET /internal/v1/records/{applicantId}/initialization` | `no body` ? `ownedReceipt` |
| `operation.record.getReadiness.v1` | `GET /internal/v1/records/{applicantId}/readiness` | `no body` ? `ownedReadiness; 200:ownedReadiness, 202:ownedReadiness` |
| `operation.record.resumeInitialization.v1` | `POST /internal/v1/records/{applicantId}/resume` | `no body` ? `ownedReadiness; 202:ownedReadiness` |
| `operation.record.credentialFacts.v1` | `POST /internal/v1/records/facts` | `ownedApplicantOnly` ? `ownedRecordFactsPort` |
| `operation.record.credentialsReady.v1` | `POST /internal/v1/records/events/credentials-ready` | `ownedCredentialsReady` ? `ownedReadyAcknowledgement` |

The canonical per-operation caller allowlist remains enforced by authenticated
transport metadata AND the receiving handler. A topic/group subscription is not
an authorization grant. Private deception/context must never become public,
player-scoped messages or unrestricted broadcasts. Preserve the existing Session
binding on getDeception and Session readiness gating on profile/claims.

Public CRUD, Record's player record-slice routes and its management academic-context
route are not missing internal operations: they are public/management HTTP surfaces,
not Task 6 subscriptions. Record's public player identity remains Gateway-authenticated.

Outbound operation dependencies (these are NOT subscriptions owned by these services):

| Caller | Exact peer catalog operation names |
| --- | --- |
| Applicant | `record.initialize`, `record.getInitialization`, `credential.initialization.accept`, `credential.initialization.recover`, `credential.initialization.status` |
| Record | `applicant.initialize`, `applicant.getInitialization`, `credential.initialization.accept`, `credential.initialization.recover`, `credential.initialization.status`, `session.verifyMembership` |

### Catalog accuracy items to reconcile before Task 6 implementation

This is not an unconditional claim that every JSON Schema constraint is complete.
The current receivers enforce more than parts of the shared schema express:

- CredentialsReady requires 1..32 distinct, nonzero credential UUIDs, nonzero event/
  applicant/causation IDs, an existing full parent and matching causation. The current
  `ownedCredentialsReady` schema has `minItems=1` but lacks `maxItems=32` / `uniqueItems=true` and
  nonzero-ID restrictions. These actual receiver constraints must be reflected in
  Vasile's shared schemas/examples without loosening the business handlers.
- Full ApplicantInitialized requires millisecond-precision occurredAt, producer equal
  to payload.initiator, matching authenticated producer and nonzero IDs. Its semantic
  scenario/identity constraints remain mandatory beyond basic date-time/uuid validation.
- Correlated Credential READY requires pendingDeliveries=0 plus the local durable
  callback; matching full peer receipt is also required. Generic catalog prose saying
  that all three services return identical receipts is historical and must not define
  the Task 6 protocol. Credential Status is NOT a full initialization hash receipt.
- Catalog statusEvidence/status labels still reference older unmerged PR candidates;
  use the merged source revisions above for this owner's current implementation state.

These are shared-spec reconciliation points, not permission to change payloads,
hashes, business authorization or initialization behavior locally.

## 2. Existing business events and real event-topic delivery

Current production transport is authenticated HTTP callbacks through Broker.
The following are implemented business events, not log-only fixture publishers.
Task 6 must carry these through actual event topics alongside operation request/reply,
reusing existing handlers/deduplication. Do not both publish an event AND invoke its
mutating operation for the same delivery as two independent business actions.

| Event / wire schema | Current publisher | Current consumers | Processing acknowledgement needed? |
| --- | --- | --- | --- |
| ApplicantInitialized, FULL `ownedApplicantInitialized` | Applicant or Record when that service is original initializer | The other owned service; receivers also authorize a full Credential-origin envelope if Credential actually supplies it | Yes: exact durable full receipt from each required destination group |
| ApplicantInitialized, SEED `ownedInitialization` | The same original Applicant/Record initializer, projecting its persisted full event for Credential | Credential only | Yes: accepted-in-memory is insufficient; current owned delivery completes only after correlated Credential READY/zero-pending and a local committed callback |
| CredentialsReady, `ownedCredentialsReady` | Credential (external owner) | Applicant and Record | Yes: each owned consumer commits first and returns its correlated accepted acknowledgement; Credential owner must confirm its publisher/outbox implementation |

The two ApplicantInitialized bodies intentionally have the same business type/
version but different schemas. They CANNOT be put on one unrestricted topic and
assumed interchangeable. Proposed event-topic labels for Vasile's agreement are
`event.ApplicantInitialized.full.v1`, `event.ApplicantInitialized.seed.v1` and
`event.CredentialsReady.v1`; these labels are NOT an existing or finalized shared
contract. Equivalent explicitly schema-distinct topics are acceptable after review.
Keep the fixed `operation.<exact catalog name>.v1` convention above unchanged.

Full-event routing must target only the required other owning group, not the
already-committed original producer. Never broaden the existing receiver caller
allowlist merely to permit a producer to consume its own broadcast. The seed variant
is Credential-only. CredentialsReady requires both owned destination groups. All
replicas of one owner share its group; required-group acknowledgement and per-instance
acknowledgement are different. Consumers never republish initialization into a loop.

### Exact existing envelope shapes

These are synthetic business-ID examples matching current schemas, not deployment
configuration. Field names/casing, version and payload shape are normative; IDs,
seed and timestamps are sample values.

Full ApplicantInitialized (`ownedApplicantInitialized`):

```json
{
  "eventId": "00000000-0000-0000-0000-000000008000",
  "type": "ApplicantInitialized",
  "occurredAt": "2026-11-11T12:00:00.123Z",
  "producer": "applicant-service",
  "version": 1,
  "payload": {
    "applicantId": "00000000-0000-0000-0000-000000007000",
    "seed": 0,
    "initiator": "applicant-service",
    "identity": {
      "name": "Applicant 000000000000",
      "studentId": "PAD-00000000000000000000000000007000",
      "year": 1
    },
    "deception": {
      "type": "NONE",
      "impersonatedStudentId": "",
      "inconsistentFields": []
    },
    "sessionId": "00000000-0000-0000-0000-000000009000"
  }
}
```

Credential seed projection (`ownedInitialization`): keep the SAME original eventId,
metadata, applicantId and seed; omit full identity/deception/session fields rather
than replacing their meaning or hashing this projection as a full event.

```json
{
  "eventId": "00000000-0000-0000-0000-000000008000",
  "type": "ApplicantInitialized",
  "occurredAt": "2026-11-11T12:00:00.123Z",
  "producer": "applicant-service",
  "version": 1,
  "payload": {
    "applicantId": "00000000-0000-0000-0000-000000007000",
    "seed": 0
  }
}
```

CredentialsReady (`ownedCredentialsReady`): causationId is the original initialization
eventId. Credential owns its immutable callback eventId and generated credential IDs.

```json
{
  "eventId": "af71af6d-7bb2-431d-a32b-6027ffb7d258",
  "type": "CredentialsReady",
  "occurredAt": "2026-11-12T00:00:00.000Z",
  "producer": "credential-service",
  "version": 1,
  "payload": {
    "applicantId": "00000000-0000-0000-0000-000000007000",
    "causationId": "00000000-0000-0000-0000-000000008000",
    "credentialIds": [
      "bf91aecf-cdf3-4f72-a024-9bf6b94c282a"
    ]
  }
}
```

No active ShiftStarted event receiver/publisher exists in these current owned
production integrations. Historical Grade 9 fixture/design mentions do not establish
an implemented subscriber. Session uses the actual applicant.warmup/generate/readiness
operations. Neither service owns DecisionRecorded, score events or Rules delivery.

## 3. Persistent mutations, retries and final delivery success

| Flow | Current persistent identity / deduplication / outbox |
| --- | --- |
| generate / full initialization | requestId becomes eventId; immutable applicantId/full event plus content digest; generation request digest includes sessionId/seed/difficulty. Unique IDs and transaction-scoped per-applicant locks prevent conflicting/concurrent initialization. Identical semantic replay returns stored data; conflicts return 409. |
| warmup | 1..3 individual generation requests; no separate batch idempotency ID. Each item has the same durable generation protection and its own outbox. A partial batch is retried with the SAME per-item requests. |
| original initializer delivery | The same local transaction commits the owner data, immutable envelope and two per-target outbox rows. Only the original initializing service fans out; consumers do not create a second outbox. |
| CredentialsReady receiver | Durable per-applicant callback receipt, unique callback eventId, canonical content digest and credential IDs bound to immutable parent eventId. Identical semantic replay acknowledges; changed/reused/wrong causation is 409, missing parent 503. No consumer outbox/fanout. |
| explicit resume | Resets only undelivered retry/lease state in the original initializing service. Does not regenerate or undo committed domain data. |
| public management CRUD | No general persistent event/request deduplication/outbox contract. These surfaces are not catalog mutations and must not be enabled for at-least-once topic delivery by assumption. |

The durable outbox uses SKIP LOCKED, a fenced UUID lease (2 seconds), at most eight
automatic attempts and exponential delay currently 1, 2, 4, 8, 16, 32 seconds (the formula
caps at 60 but its exponent is capped at 5). Conflict 409 schedules infinity until an
explicit original-service resume. Other failed/pending attempts remain persistent;
there is no automatic in-request retry or successful synthetic fallback. INITIALIZE/
RECOVER stage persists for Credential. Recover 404 returns to INITIALIZE without
resetting the attempt count. Workers tick approximately once per second and process
at most two items per tick.

CURRENT successful delivery is content-based, not merely a network status:

- Full peer: receiving business transaction committed AND HTTP 200/201 carries the
  exact `{applicantId,eventId,eventHash,status:INITIALIZED}` receipt matching the
  immutable full event. A wrong receipt, malformed body or bare 200 fails.
- Credential: response/status must match eventId AND applicantId; READY must have
  zero pendingDeliveries AND the publisher's own durable CredentialsReady receipt
  must already exist. Pending/DELIVERY_PENDING/202 do not mark the outbox delivered.
  Global readiness additionally verifies the other full peer receipt.
- CredentialsReady: each receiver returns `{eventId,accepted:true}` only AFTER its
  local receipt transaction commits. This is not a promise about the external
  Credential publisher's persistence; that owner must confirm it separately.

For Task 6, Broker's initial 202 acknowledges in-memory acceptance ONLY. It must
NOT clear an owned outbox, release a durable delivery as complete, signal queue-ready
Applicant data, or substitute for a final handler result. Require a correlated
processing result per required service GROUP after commit. Preserve eventId,
applicantId, causationId, expected content/receipt and authenticated sender on retries;
use the same business IDs after process/broker restart. A transport correlation ID
is separate from a business idempotency ID. Unknown/lost/timed-out outcomes remain
pending and replay safely. Do not label the system exactly-once.

Also distinguish a HANDLER result 202 from BROKER acceptance 202: generate/warmup/resume
currently return 202 after their local work has committed, while applicant readiness
can still be pending. The shared request/reply envelope must preserve that business
status distinctly from transport acceptance. A final operation result is not always
completion of the whole cross-service workflow.

Full event hashing uses length-prefixed UTF-8 fields and includes sessionId last;
see canonical vectors. Callback hashing normalizes time to UTC/nine fractional digits
and sorts credential IDs before hashing. Do not use reserialized JSON bytes or a
seed-only envelope as a replacement digest. Preserve fencing so a late response
cannot acknowledge unrelated/replaced work.

## 4. Current timeouts, deadline propagation and special traffic

| Surface | Actual current limit |
| --- | --- |
| Applicant business outbound | 400 ms HTTP/connect/future bound; parallel readiness has a shared 400 ms wait budget and cancels outstanding children |
| Record initialization/status/receipt outbound | 400 ms HTTP timeout; parent Go context can shorten it; parallel readiness uses the parent context |
| Record Session membership | 1 second HTTP timeout, shortened by parent context; no in-request retry |
| Owned internal handler | 500 ms task/context budget, also limited by configured task budget; generation/readiness/callback receivers use this budget |
| Broker operation | Current shared 750ms default; membership chain is caller1s/Broker750ms/Session500 ms. Owned400 ms child calls are deliberately tighter, not a request to expand them. |
| Owned DB initialization/callback transaction | 450 ms PostgreSQL statement timeout inside the receiver budget |
| Record background delivery | 1200 ms parent context per leased job; HTTP child remains400 ms |
| Other owned task handlers | TASK_TIMEOUT_MS default 2000 ms; not a substitute for the stricter 500 ms internal-operation budget |
| Direct Discovery registration | Both clients use 2 s HTTP limits, at most 3 attempts with 1 s / 2 s backoff; this is control-plane traffic, not a business operation/event topic |

Responses/bodies remain bounded; redirects, ambient proxies and automatic HTTP
request retries are disabled for the business clients. X-Trace-Id is propagated on
current synchronous hops; deferred delivery uses stable `init-<eventId>` correlation.
There is currently NO shared cross-hop deadline header/envelope implemented by these
clients. Local deadlines/cancellation do not establish end-to-end deadline propagation.
After publication, the owner will adopt the agreed remaining-deadline contract and
fit queue wait plus execution plus child calls inside it; this document invents no
header name or clock/expiry rule. If no budget remains, fail before beginning work;
exact accepted-but-expired event handling needs Vasile's common delivery contract.

Neither Applicant nor Record serves SSE or WebSockets, and neither needs a streaming
exception. Java CompletionStage responses are asynchronous ordinary HTTP, not streams.
Player REST remains Gateway-facing. Keep direct Discovery traffic and health/status
probes outside business queues; do not infer consumer readiness from process liveness.

## 5. Owner implementation commitment after shared schemas/examples

Confirmed scope for the Applicant/Record owner after Vasile publishes the agreed
schemas/examples and the Discovery owner accepts registration/readiness extensions:

1. Add startup/reconnect subscriptions for the exact operation topics/groups above
   plus approved event-topic variants. Gate consumer-ready state on actual handler,
   owned DB/migration and subscription readiness; coordinate refresh/unregister behavior.
2. Adapt outbound request/reply AND real business-event publication, not just routing
   every notification as an RPC operation. Retain full/seed separation and approved
   target-group fanout. Invoke existing business logic and durable deduplication once.
3. Validate authenticated caller identity/allowlists, schemas, response correlation,
   processing acknowledgements and shared deadlines without trusting payload identity
   as authorization. Preserve session/privacy guards and all current business payloads.
4. Persist pending delivery until the required processing acknowledgements; preserve
   bounded recovery/fencing and prove loss/restart/duplicate/late-result safety. An
   in-memory broker acceptance cannot become a durable success.
5. Test actual subscriptions, group/replica routing, real event fanout, authorization,
   queue expiration/deadlines, failure recovery and current real-peer business flows.
   Existing contract doubles/historical membership evidence are not full Task 6 proof.

This is an implementation commitment, not a claim those clients/subscriptions exist
already. No Task 6 runtime, release, image or shared-deployment changes are made here.

## Discovery owner coordination

Asked the owner directly in
[Discovery issue #37](https://github.com/CmMarin/student-id-service-discovery/issues/37),
assigned to CmMarin:

> We plan the additive subscriptions registration change and readiness information
> needed by Broker. Do you have any ongoing Discovery branches or PRs to coordinate
> with, and what health/readiness state can its current API expose?

Inspected Discovery dev `0f4c538f2b5d6eab6c128cd251c959b8e7872a39`: no open PR was
visible during this check. Existing branch names include feature/discovery-circuit-eviction
and fix/discovery-release-lab3-0.3.0; owner confirmation of active work is requested.
The current README/API describes registration fields serviceName/instanceId/baseUrl/
readinessPath plus returned registeredAt, and rejects extra fields. Instance listings
are registrations, not a verified healthy-target or per-subscription readiness list.
Its /health and /health/ready report process UP; /status describes registry health/
configuration/capacity. Poller observations do not change the registration response
shape. These facts do not establish a subscription-ready API; the owner must confirm
and coordinate the additive contract before clients send new registration fields.
