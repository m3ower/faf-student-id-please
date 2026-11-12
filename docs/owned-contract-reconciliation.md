# Owned HTTP integration: latest team reconciliation

Reconciled against CPR dev `e21cdd9` (merged #132, including the rewritten
#129 catalog and #134's reviewed teammate pins). #132 imports Applicant/Record
[CPR #126](https://github.com/m3ower/faf-student-id-please/pull/126) schemas at
`90fc1b9bb98de61b50903cd9819ddaced4974c1e` and our receiver definitions from #127.

## What teammates have published

- The merged **single canonical catalog** is
  [service-operations.json](../contracts/http/service-operations.json).
  [OpenAPI](../contracts/http/openapi.json) is generated with the team's validator.
- Moderation's receiving contract now defines read-only
  `GET /internal/v1/moderation/applicants/{applicantId}/decision-facts`.
  Rules now consumes that exact method/path and schema. It no longer requires
  invented studentId/revision fields or a POST history binding.
- Applicant/Record's exact profile/claims/facts schemas, session-bound envelopes,
  hashes, receipts and readiness are now imported into the canonical catalog.
  The owned Credential compatibility adapters are now implemented as review candidates; actual current private-peer acceptance remains outstanding.
- Session now publishes `session-state.get`, accepts Credential/Rules membership
  calls, and adopts Rules' immutable bind/read contract with shiftId=sessionId.
  This establishes the reviewed candidate contract, not a live integration result.
- Gateway registry and target-credential behavior must be checked against its
  latest reviewed candidate; the older #48 membership-only snapshot is insufficient.
- The private peer repositories return 404 for this account. These findings
  establish published contract status, not verified private source or live images.

## Owned receivers now match the merged catalog

| Operation | Canonical request | Caller |
| --- | --- | --- |
| credential.listApplicantCredentials | `GET /internal/v1/credentials?applicantId={id}&sessionId={id}` | Moderation |
| credential.validateCredential | `GET /internal/v1/credentials/{id}/validation` | Moderation |
| rules.evaluate | `POST /internal/v1/rules/evaluations` with sessionId/applicantId | Moderation |

The Credential list returns at most 32 documents or a failure, not silent truncation.
Validation uses stored provenance and fresh Record facts, and returns all required
catalog fields. These canonical handlers use the target's 500 ms budget, inside
Gateway's 750 ms and the caller's one second. Unknown/missing facts never grant
permission or fabricate successful evaluation.

Rules' `rules.shift.bind` and `rules.shift.read` now also have canonical candidate
entries and examples, imported by #132. Their owner-defined schemas are preserved.

Earlier owned internal paths remain candidate aliases/extensions, not an alternate
canonical catalog. Their definitions and schemas are retained under `ownedDrafts`
and the additional `owned*` schemas in the single catalog. The remaining legacy
entries are **not** Gateway registry entries or approved team contracts. The duplicate
`contracts/business-http/` catalog has been removed.

## Explicit Credential compatibility adapters

Applicant PR #23 and Record PR #25 now preserve their full session-bound envelopes
and matching hashes while explicitly speaking Credential's receiver-published
seed/status/callback protocol. The two protocols remain separate schemas; a
Status is never fabricated into an INITIALIZED receipt. New canonical operations
cover initialize/recover/status, Credential-only Applicant context and both
CredentialsReady receivers, plus the Credential/Rules authoritative Record projection.

The initializer projects only `{applicantId,seed}` with the original event metadata.
It persists INITIALIZE/RECOVER progress and resumes bounded delivery after restart.
Each receiving owner commits a correlated immutable CredentialsReady receipt before
acknowledging. Aggregate readiness requires the full peer hash receipt, a local
durable callback, and Credential status matching eventId/applicantId with READY
and pendingDeliveries=0. Outages fail closed.

Credential must use the exact `BUSINESS_HTTP_BINDINGS_JSON` mapping in the
[owned integration guide](owned-real-integrations.md#credential-compatibility-configuration).
This is deployment configuration; no Credential source was changed. The shared
Gateway registry must load the candidate operation catalog. A seed-only message
cannot supply unknown Session context: generate/warmup with sessionId/difficulty
first. Credential may initiate those owned operations; context reads never
create a guessed applicant.

The reproducible network suite uses actual owned services and unmodified Gateway
source, with a labeled test-only Credential protocol peer. It proves adapter
wire compatibility and durable callbacks, not current private Credential document
generation/validation. Current Credential/Session source/images and full-game
acceptance remain unverified. Rules' other consumer adapters remain its owner's scope.

The safe publication is reviewable PRs to dev containing the implemented owned work,
canonical receiver compatibility, tests and this handoff. No release, image
publication, protected-branch push or submodule/image-pin promotion is requested.
Do not merge independently until real cross-owner
acceptance and required reviews are complete. Service Discovery's latest dev remains verified and
needs no domain-call changes for this baseline.
