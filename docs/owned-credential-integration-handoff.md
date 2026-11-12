# Applicant/Record handoff for real Credential and Rules integration

Status checked on 2026-11-12. The owned implementations are merged into their
private `dev` branches. The shared contract changes remain a candidate in
[CPR #126](https://github.com/m3ower/faf-student-id-please/pull/126).
This handoff does not certify whole-system readiness or enable broker migration.

## Exact source and release status

| Component | PR | Merged `dev` commit |
| --- | --- | --- |
| Applicant | [#23](https://github.com/Andreiisthebest/student-id-applicant-service/pull/23) | `43d8a27134b8cbe02d4ff0bd88b54ce7945399d3` |
| University Record | [#25](https://github.com/Andreiisthebest/student-id-university-record-service/pull/25) | `5d8bcd331b68bd517f206fa384a09134c9b52934` |

Both merged source trees match their passing tested PR heads exactly. The squash
commit IDs differ from the tested feature commits; compare trees rather than
assuming an ancestor comparison means unmerged changes. Exact tested images and
earlier checks are recorded in [the evidence report](owned-http-evidence.md).

**No published image tag is available for this new compatibility implementation.**
The Docker Hub tag lists contain no `lab3-1.0.0*` tags for either owned image;
their `latest` tags were last updated on 2026-10-27 and predate this work. Local
`pad-owned-*:integration-candidate` images are not shared published releases.
Do not use an older tag as evidence that the merged implementation is running.
Build disposable acceptance images from the exact merged commits, or complete
the normal release process and record published tags, digests and source labels.

CPR `dev` still pins the older Applicant `7b33b46a5900ecd35e791cd5e6b4f160f513fbfb`
and Record `aefdd93e198ee2824ca1c5c394cfe37aabf599de` sources. This handoff does
not promote those pins or images before joint acceptance.

## One shared contract

Use [the single operation catalog](../contracts/http/service-operations.json),
[generated OpenAPI](../contracts/http/openapi.json),
[operation examples](../contracts/http/examples/), and
[protocol vectors](../contracts/http/test-vectors/).
The implementation contract snapshot is CPR commit
`776ac33cd2b0f153a0b5b8d28f879ac7120ef993` in PR #126: 38 operations/examples.
Review that candidate before integrating; older CPR `dev` alone lacks the new
adapter operations. The catalog's schemas, callers, errors and success statuses
are authoritative. Operation registration must use that same snapshot.

There are two deliberately separate protocols:

- Applicant/Record exchange a full, immutable, session-bound ApplicantInitialized
  envelope. They return matching `{applicantId,eventId,eventHash,status:"INITIALIZED"}`
  receipts. The full hash includes sessionId as its final length-prefixed field.
- The owned adapter sends Credential its published seed-only envelope: original
  eventId/type/occurredAt/producer/version, with payload `{applicantId,seed}`.
  Credential returns its own initialization Status and sends CredentialsReady
  callbacks. A Status is never converted into a fabricated full hash receipt.

Routing configuration cannot replace these adapters. Compare the actual peer
implementation against these schemas and semantics, including missing-parent,
conflicting replay, hash normalization, callback causation and recovery behavior.
Publish coordinated contract/code changes if any receiver differs.

## Required Gateway and service configuration

Use the Gateway owner's operation-registry implementation, not the earlier
membership-only image. The unchanged candidate source used in the owned tests
was `0a6d49649e0dd3610e206e8afc4ffbf76b34ba87`. It must load the agreed candidate
catalog as runtime configuration; its older bundled catalog lacks the new routes.

Configure Gateway's `APPLICANT_SERVICE_URL`, `RECORD_SERVICE_URL`,
`CREDENTIAL_SERVICE_URL`, `SESSION_SERVICE_URL`, and other actual owner origins.
Keep backend ports private. Configure `GATEWAY_SERVICE_TOKENS_JSON` with distinct
caller identities and `GATEWAY_TARGET_TOKENS_JSON` with separate downstream
credentials. Each target's receiver token must match its Gateway target entry.
Never reuse Discovery credentials or player JWTs as service credentials.

Applicant needs `DB_URL`, `DB_USER`, `DB_PASSWORD`, `GATEWAY_URL`,
`GATEWAY_SERVICE_TOKEN`, `SERVICE_INTERNAL_TOKEN`, and `MANAGEMENT_TOKEN`.
Record needs its own `DB_URL`, `GATEWAY_URL`, `GATEWAY_SERVICE_TOKEN`,
`SERVICE_INTERNAL_TOKEN`, `MANAGEMENT_TOKEN`, and `SESSION_CLIENT=gateway`.
Use distinct 32-256 visible ASCII secrets; distribute them privately. Discovery
registration remains separate control-plane traffic. Apply the bundled migrations
to each service's own database, never a peer database.

Set Credential's published `BUSINESS_HTTP_BINDINGS_JSON` to:

```json
{
  "applicant.context": "/internal/v1/applicants/context",
  "record.facts": "/internal/v1/records/facts",
  "applicant.ready": "/internal/v1/applicants/events/credentials-ready",
  "record.ready": "/internal/v1/records/events/credentials-ready"
}
```

Verify Credential actually uses these published ports; configuration cannot fix
a different request/response or initialization implementation. The POST context
operation is Credential-only. The POST authoritative facts operation permits
Credential/Rules. Existing GET facts and Moderation-only answer-key reads retain
their separate permissions. Services never impersonate a junior to obtain facts.

| Operation | Method/path | Allowed caller |
| --- | --- | --- |
| credential.initialization.accept | `POST /internal/v1/credentials/initialize` | Applicant, Record |
| credential.initialization.recover | `POST /internal/v1/credentials/initializations/{eventId}/recover` | Applicant, Record |
| credential.initialization.status | `GET /internal/v1/credentials/initializations/{eventId}` | Applicant, Record, Session |
| applicant.credentialContext | `POST /internal/v1/applicants/context` | Credential |
| record.credentialFacts | `POST /internal/v1/records/facts` | Credential, Rules |
| applicant.credentialsReady | `POST /internal/v1/applicants/events/credentials-ready` | Credential |
| record.credentialsReady | `POST /internal/v1/records/events/credentials-ready` | Credential |

Use canonical service names from the catalog rather than the short labels here.
Both POST reads accept `{applicantId}`. The catalog defines their exact fields.
Record owns its persisted truth, including negative enrollment; Applicant's
claims and private deception must not be rewritten to match it.

## Initialization prerequisites and readiness proof

First call an owned `generate` operation (or Session's agreed Applicant warmup)
with nonzero requestId/applicantId/sessionId UUIDs, seed and difficulty. Preserve
that request for replay. Credential may initiate these full-context owned
operations too. A seed-only event cannot invent an unknown Session id or difficulty;
context reads never generate missing context. The initializer persists its own
data and pending delivery before network calls. Consumers do not fan out again.

The owned outbox persists INITIALIZE/RECOVER stages. After an acknowledged pending
Credential status it uses recover, with eight bounded automatic attempts and
explicit original-initializer resume. Recover 404 returns to INITIALIZE without
resetting that bound. Non-idempotent operations have no automatic in-request retry.

A CredentialsReady callback must contain immutable event metadata and payload
`{applicantId,causationId,credentialIds}`. CausationId must match the original
initialization eventId. Both receivers commit deduplication receipts before
returning `{eventId,accepted:true}`. Missing full parent is 503; changed content,
reused callback identity or wrong causation is 409. Identical semantic replay is 200.
Callbacks do not generate or republish initialization.

Readiness requires all of:

1. A matching full Applicant/Record peer receipt.
2. The owner's durable correlated CredentialsReady receipt.
3. Credential status matching both eventId and applicantId, with state READY and
   `pendingDeliveries=0`.

Until then, readiness and Session profile/claims return 202 with no ready applicant
data. A lost Credential status dependency makes the item pending again. Receipt
reads are local, so aggregate readiness does not recursively call itself.

## Joint acceptance with real peer implementations

Record exact source SHAs and running image digests for every participant. Use
fresh disposable stores and actual Gateway routing, caller allowlists and target
credentials. A contract double, health check, or container-to-container curl is
not sufficient evidence for these checks:

1. Start non-fixture, full-context generation through each supported owning entry
   point. Prove initialization completes in the real Applicant, Record and
   Credential stores. Session must not queue a partially initialized applicant.
2. Replay identical initialization, recovery and callbacks, including concurrent
   requests, restart and a second replica. Compare persisted counts and immutable
   identities to prove no duplicate applicants, records, credentials or delivery
   effects. Changed seed/content/event causation must conflict without overwrite.
3. Call `credential.listApplicantCredentials` and `credential.validateCredential`
   as their authorized Moderation caller, with real Session context. Prove
   Credential uses actual authoritative Record facts and preserves intentional
   truth/claim differences. Test invalid, unknown and forbidden cases too.
4. Call `rules.evaluate` as the authorized Moderation caller. Verify Rules obtains
   real permitted service responses, including agreed Session/shift context,
   instead of fixtures, cached demo values or log-only integrations.
5. Exercise missing credentials, wrong caller, forged player identity, unknown
   IDs, malformed replies, outages and deadlines. Authorization dependencies fail
   closed; no outage may become mock success. Recover after partial delivery
   without duplicate effects. Preserve X-Trace-Id across actual business hops.

The owned suite has passed 113 Gateway checks, 42 Applicant database tests, Record
race/coverage gates and 16 shared contract tests. Its Credential participant was
explicitly a test-only protocol peer; Session covered historical membership only.
Actual current Credential and Session sources are inaccessible to this account.
Real Credential validation and Rules evaluation are therefore still unverified.

After joint acceptance, update CPR submodule pointers, immutable image references
and evidence together. CPR retains its required approvals. Per Andrei's explicit
instruction, mandatory approvals are disabled only for Applicant/Record dev/main;
their CI and other protections remain. Message Broker approvals are unchanged.
