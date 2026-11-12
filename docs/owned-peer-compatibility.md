# Owned service compatibility gate before Broker migration

Tracked by CPR #135, Rules #33, Credential #39, Gateway #53 and Broker #9.
Source handoff: [Applicant/Record at 42f69b9](https://github.com/m3ower/faf-student-id-please/blob/42f69b980bca01568152d29ba86e5fe526a86ac3/docs/owned-credential-integration-handoff.md).

## Protocol reconciliation

Applicant/Record keep their full, session-bound ApplicantInitialized/hash/receipt
protocol and explicitly adapt it to Credential's existing seed-only envelope,
initialization Status and correlated CredentialsReady callbacks. A Credential
Status is never a fabricated full receipt. The adapter routes, schemas and examples
are imported unchanged from that receiver-owner candidate; review CPR #126 with
this PR. The single catalog adds the existing receiver-owned Credential batch
validation operation, giving 39 operations/examples and generated OpenAPI.

Credential's initialization, recovery, status and batch receivers enforce 500 ms.
Timeouts leave durable work to replay/recovery; no timeout or empty validation
counts as success. Callbacks require matching eventId, applicantId and causation.
Use the handoff's four bindings in Credential's .env.example, with private secrets.

Rules sends Session only sessionId, checks ACTIVE/READY/currentApplicantId and
compares persisted shift ruleset versions. It uses the exact wrapped Applicant
profile GET (not Credential-only generation/deception context), records a labelled
profile content digest rather than inventing a revision, calls Record POST facts
and Credential batch validation, and uses Moderation's read-only decision facts.
Only Record facts requires a configurable POST binding. Channel ownership is
deferred; a channel-dependent pinned policy fails closed, never defaults to general.

Gateway bundles the same 39-operation catalog with exact caller allowlists and
target credentials. Broker #8 already supplies the shared 31-operation routing
baseline; our independent Broker fix isolates local probes from business deadlines.
No Broker route expansion or owned-caller migration is enabled here. Public client
traffic remains through Gateway, and the compatibility baseline still uses its
explicitly permitted transitional service routes.

## Real-owner acceptance is a release gate

Required peer sources are Applicant 43d8a27134b8cbe02d4ff0bd88b54ce7945399d3 and
Record 5d8bcd331b68bd517f206fa384a09134c9b52934. Their handoff reports no published
matching images. Obtain the private source archive or pullable images with source
labels; do not substitute old latest tags or a protocol double as evidence.
Session's reviewed state/membership/binding build and actual Moderation are also
required for the complete acceptance run. Their private source/builds are not
certified by this account's contract-only inspection.

On isolated databases, correlate one trace across actual application calls:

1. Full-context generation -> real Applicant/Record data -> Credential generation
   -> both durable callbacks -> matching Credential READY/zero-pending status.
2. Replay, conflicting causation, concurrent calls, restart/recovery and another
   replica: compare durable counts/IDs and prove no duplicate effects.
3. Moderation's real Credential list/validation and Rules evaluation -> actual
   Session state, Applicant profile, Record facts, Credential checks and history.
4. Denied caller, missing credentials, unknown IDs, pending state, malformed data,
   outage and timeout must fail closed, followed by successful durable recovery.

Unit/database/network-peer tests are necessary but not that real-owner proof.

Latest local verification: Credential 72 tests, 94.92% line coverage with disposable
PostgreSQL; Rules full database suite, 83.9% total / 89.2% rules-package statement
coverage; Gateway 352 tests, 98.44% coverage; Broker 42 tests, 95.81% coverage;
CPR 43 tests and 39 operation/example pairs validated. Gateway's bundled catalog
is byte-identical to this CPR candidate. Broker's real cancellation test uses an
injected circuit clock to isolate scheduler jitter; separate clock-driven tests
still verify real failure-window expiration. No production budgets were relaxed.

Keep compatibility PRs draft until this gate and reviews pass. Do not promote
shared pins/images or claim Task 5 migration complete. After acceptance, migrate
the agreed operation catalog and actual callers to Broker in a separate change.
