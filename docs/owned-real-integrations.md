# Applicant and Record HTTP integration contract (candidate)

Issue [#124](https://github.com/m3ower/faf-student-id-please/issues/124).
The executable operation catalog is
[service-operations.json](../contracts/http/service-operations.json), with generated [OpenAPI](../contracts/http/openapi.json).
It extends the membership candidate, not the Message Broker implementation.
These routes require Gateway's owner to register their exact caller allowlists
and separate target credentials. They are not implemented by Gateway PR #48.

## Authentication and ownership

Callers send their own `GATEWAY_SERVICE_TOKEN` to Gateway. Gateway authenticates
the caller, checks the catalog operation allowlist and substitutes the receiving
service's `SERVICE_INTERNAL_TOKEN`, setting `X-Service-Name` from authenticated
identity. Receivers validate both before dispatch. User JWTs cannot use these
internal operations. No caller provides a destination URL or an asserted role.

All legacy management CRUD requires an independent `X-Management-Token` matching
`MANAGEMENT_TOKEN`. User JWTs alone cannot list or mutate hidden university data.
The JSON schemas of existing CRUD requests are retained. Clients must add this
new administrative credential; it must not be stored in Postman exports or Git.
Existing generated entities cannot be edited/deleted through management CRUD:
`409 INTEGRATION_MANAGED_ENTITY` preserves immutable initialization. Ordinary
non-generated CRUD rows retain their existing behavior for authorized operators.
All backend business ports must remain private behind Gateway.

Applicant owns claims and private deception metadata. Record owns independently
generated university truth. Credential/Rules obtain the authorized internal
Record facts operation, rather than impersonating a junior on a public lookup.
Only Moderation can read Applicant's private deception operation.

## Generation and the shared envelope

`POST /internal/v1/{applicants|records}/generate` receives:

```json
{"requestId":"2b653eb0-6234-4691-a145-d8ef108212c3","applicantId":"77d8ab80-dc3f-484c-9e22-4121d0625c67","sessionId":"c521de8c-2952-48c0-a6bb-ea5cde6cdc74","seed":7281,"difficulty":"NORMAL"}
```

These are example identifiers, not reserved production fixtures. IDs must be
nonzero UUIDs; seed is an integer in `0..9007199254740991`, difficulty is exactly
`EASY`, `NORMAL` or `HARD`. Repeated identical input returns the original persisted
envelope. Reuse of identifiers with different input is 409, without regeneration.

The initializer's eventId is requestId. Its event type is ApplicantInitialized,
version 1, and occurredAt is a UTC instant with millisecond precision, assigned
once. Producer and payload.initiator are the same canonical owning service.
The new HTTP candidate requires payload.sessionId in addition to seed/identity/deception.
It rejects old unbound envelopes; Credential uses the explicit seed/status/callback adapter below.
Each of the
three owners may initiate full-context generation; the Credential wire adapter preserves its separate published protocol.

The generation specification is deliberately independent of fixture IDs:

- Remove dashes from applicantId, lowercase it as `id`; claims name is
  `Applicant ` plus its first 12 characters, studentId is `PAD-` plus uppercase id,
  study year is `1 + seed % 4`, major FAF, role STUDENT, claimed status ENROLLED,
  and claimed course PAD. University email is studentId with dashes removed,
  lowercased, plus `@isa.utm.md`.
- EASY selects by `seed % 3` from NONE, EXPIRED_DOCUMENT, NOT_ENROLLED.
  NORMAL selects by `seed % 6` from NONE, IMPERSONATION, FORGED_DOCUMENT,
  EXPIRED_DOCUMENT, INCONSISTENT_CLAIM, NOT_ENROLLED. HARD adds PREVIOUSLY_BANNED
  as its seventh possibility. This is game generation, not hardcoded lookups.
- IMPERSONATION identifies the claimed studentId in impersonatedStudentId;
  Record stores the name `Verified holder ` plus the first 12 id characters.
  INCONSISTENT_CLAIM identifies exactly `major`; Record's major is OTHER.
  Other scenarios have empty impersonatedStudentId and inconsistentFields.
- NOT_ENROLLED creates no enrollment row, but commits an initialization receipt
  and a negative enrollment link. Other scenarios create ENROLLED truth with
  enrollment date September 1 of `2020 + seed % 5`, group `FAF-Y<year>` and
  course PAD. Record stores an actual FCIM initialization message with the
  original event timestamp. Credential forgery/expiry never alters enrollment.
- PREVIOUSLY_BANNED is private scenario information, not a fabricated Record
  ban-history row. Moderation remains responsible for its own ban data.

## Canonical hashing, conflict handling and delivery

The event hash is SHA-256 of concatenated UTF-8 fields, each encoded as
`<decimal UTF-8 byte length>:<field bytes>`. Fields, in this exact order, are:

1. version; eventId (lowercase UUID); type; occurredAt normalized as
   `YYYY-MM-DDTHH:mm:ss.SSSZ`; producer;
2. payload applicantId (lowercase UUID); seed (decimal integer); initiator;
3. identity name; studentId; year (decimal integer);
4. deception type; impersonatedStudentId; inconsistentFields count (decimal);
   then each inconsistent field in its validated order; finally payload.sessionId (lowercase UUID).

Generation request fingerprint uses the same encoding over requestId,
applicantId, sessionId, seed, difficulty. The envelope hash does not include
database timestamps, delivery status or service-local generated fields.

Initializers commit their own part, immutable envelope, and two pending delivery
rows in one local transaction. Network calls occur after commit. Background
workers lease a bounded batch using SKIP LOCKED and a fencing UUID; expired
leases can be reclaimed after restart. The original producer alone delivers the
full envelope to the other owned peer's `POST /events/applicant-initialized`; Credential receives its explicitly projected seed envelope as described below. A consumer
commits only its own data and deduplication record; it never fans out that event.

Receivers serialize first initialization using a transaction-scoped advisory
lock. Identical replay returns the same receipt; conflicting event IDs, changed
seed/identity/deception or different input for an existing applicant return 409.
Concurrent independent initializers for the same applicant with different
envelopes are conflicts, not distributed consensus: the item remains unavailable
until operators resolve it using a new identity. No service silently overwrites
another initialization.

The receipt is `{applicantId,eventId,eventHash,status:"INITIALIZED"}`. Delivery is
acknowledged only after a matching full-peer receipt, or the separate Credential callback/status proof below; never merely an HTTP 200. Pending
deliveries use bounded exponential backoff, at most eight automatic attempts;
409 remains blocked. `POST /{applicantId}/resume` on the original initializer
explicitly resumes nondelivered work. The receiver remains durably idempotent.

`GET /{applicantId}/initialization` returns a local committed receipt and performs
no remote call. `GET /{applicantId}/readiness` checks the full peer receipt and Credential callback/status proof in parallel, returning 200 only when both succeed; otherwise 202 with
`ready:false,pendingServices:[...]`. Generation always returns 202 after its local commit.
Session profile/claims reads also return 202 without applicant data until both component proofs succeed. This distinction avoids recursive readiness
calls. Session must not offer a pending applicant. A lost dependency never
becomes a fabricated ready response.

Applicant warmup accepts one to three generation requests and commits/queues
them idempotently. It returns 202 with `{status:"PENDING",applicantIds:[...]}`;
Session polls individual aggregate readiness. A partially completed warmup can
be retried with the same request IDs; it is not a distributed transaction.

## Record surfaces and configuration

Record completes its owned player-facing enrollment, Outlook-group, course,
FCIM-message and academic-context reads. Each protected slice checks actual
Session membership and its explicit ENROLLMENT_LIST, OUTLOOK_GROUPS,
COURSE_CATALOG or FCIM_RECORD assignment. Moderator role does not grant slices.
The academic context and course catalog are configured and persisted by an
authorized operator at `PUT /api/v1/university-records/academic-context`:

```json
{"academicYear":"2026-2027","semester":"2026-1","weekOfSemester":10,"courses":[{"code":"PAD","name":"Distributed Applications","year":3}]}
```

An unconfigured academic context returns 503, not invented dates or courses.
The canonical service facts API identifies enrollment truth by applicantId and
returns a separate negative fact for NOT_ENROLLED. Record never reads another
owner's database or substitutes applicant claims for its own truth.

Production configuration requires GATEWAY_URL, a dedicated GATEWAY_SERVICE_TOKEN,
SERVICE_INTERNAL_TOKEN and MANAGEMENT_TOKEN. The three secrets must differ and
contain 32-256 visible ASCII characters. Record uses real Gateway membership;
mock/disabled modes are rejected. Legacy fixture classes live only in tests.
Internal operations have 500 ms total task/context deadlines. HTTP calls have 400 ms total body deadlines, no redirects/ambient proxy and a
16 KiB reply bound. Local database operations have bounded statements and use
the original task deadline where available. Credentials/payloads are not logged;
safe trace IDs link synchronous calls and stable event IDs link recovery work.

## Integration/release boundaries

Gateway's owner must implement every catalog operation and caller allowlist.
Credential's owner must implement the matching consumer, local receipt and
initializer behavior. Current older images do not provide these operations.
Peer contract servers may support unit tests, but cannot prove whole-system
readiness. No broker migration, shared image-pin change, stable publication or
architecture modification is included. Owner implementation/PRs, real cross-owner
acceptance, two-review gates and reviewed releases remain required.

## Exact remaining peer requirements

The current merged canonical catalog defines all Applicant/Record receiving paths.
The explicit Credential seed/status/callback adapter below resolves the owned protocol boundary; actual current private Credential runtime acceptance remains external;
its seed/callback draft is not an approved replacement route. Applicant/Record each use a distinct caller
credential and their own receiving target credential. Gateway issue #51 must include these
new catalog rows; this PR does not modify Gateway or another owner's source.

Applicant's deception read requires a valid matching sessionId and returns 404 for a different
session. Record facts use `/internal/v1/records/{applicantId}/facts` for Credential/Rules only.
Session's owner must accept the warmup/generate/poll-ready protocol; no unagreed shift callback
is labeled implemented. The 7 golden vectors are identical in both owned test suites and cover
the immutable session binding and all scenario types. These are test inputs, not production IDs.

Both owned repositories now have active two-review, code-owner, strict verify-CI and no-bypass
rules on dev/main. Source candidates are 1.0.0 because authentication/configuration changes
are breaking. No stable release or shared image-pin update is part of these feature PRs.


## 2026-11-12 Gateway verification

[Current evidence](owned-http-evidence.md) records 53 checks against the actual owned images,
the unchanged Gateway routing candidate and a historical membership-only Session image.
The current CPR interfaces, schemas, allowlists and Gateway-phase budgets match the peer
registry snapshot. Record player reads now authenticate the receiving target credential and
Gateway caller identity before trusting X-Player-Id or querying Session.

The explicit adapters preserve both receiver-published protocols. Current private Session gameplay
and actual Credential implementation acceptance remain unverified. The user requested this
Gateway baseline before broker migration; broker-only metadata does not alter these tests.

## Credential compatibility configuration

Configure the current Credential deployment with its published consumer-port bindings:

```json
{"applicant.context":"/internal/v1/applicants/context","record.facts":"/internal/v1/records/facts","applicant.ready":"/internal/v1/applicants/events/credentials-ready","record.ready":"/internal/v1/records/events/credentials-ready"}
```

Set that object as `BUSINESS_HTTP_BINDINGS_JSON`. Caller and downstream credentials remain
separate per service; these are not public routes. The Gateway runtime must load the candidate
38-operation catalog. New operations are review candidates, not a deployed registry claim.

Applicant context returns its persisted seed, claim identity, private generation input and
immutable revision to Credential only. Record POST facts returns the published authoritative
projection to Credential/Rules. Record persists role, institutional game email, confirmation
and a real SVG data-URI asset; these are fictional game data, not real university credentials.
NOT_ENROLLED has no confirmation or courses and zero enrollment years. Existing GET facts and
Moderation's separate answer-key operation retain their original permissions.

Credential receives its seed-only ApplicantInitialized message with original event metadata.
INITIALIZE/RECOVER delivery stages persist, recover404 returns to INITIALIZE without resetting
the eight-attempt bound, and no per-request retry is added. Callbacks require matching parent
causationId, unique nonzero credentialIds and an immutable callback eventId/content. They
commit before acknowledgement, reject conflicts409/missing parent503 and never fan out.
The callback digest uses length-prefixed UTF-8 fields: eventId, type, occurredAt normalized
to UTC with nine fractional digits, producer, version, applicantId, causationId, then sorted
credentialIds. The shared golden vector proves Java/Go agreement.

A callback alone does not establish readiness. Both owned services require the other full
peer's matching receipt, the local durable callback, and Credential's correlated READY status
with pendingDeliveries=0. Credential outage makes readiness pending and withholds Session data.
A seed-only initialization cannot invent sessionId/difficulty: use full generate/warmup first,
including when Credential initiates. Context reads fail if that prerequisite is absent.

[Reproducible evidence](owned-http-evidence.md) distinguishes actual owned/Gateway handlers
from the test-only Credential protocol peer and historical Session membership image. No
teammate application source, broker transport, deployment pins or architecture were changed.
