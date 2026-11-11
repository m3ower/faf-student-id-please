# Owned HTTP integration: latest team reconciliation

Checked against CPR dev `d206056` (merged #129), Gateway dev `7d5c120`
(merged #48), and Applicant/Record draft [CPR #126](https://github.com/m3ower/faf-student-id-please/pull/126)
at `83fe3cf8af9266ef437f4b54afe16fcb708473aa`.

## What teammates have published

- The merged **single canonical catalog** is
  [service-operations.json](../contracts/http/service-operations.json).
  [OpenAPI](../contracts/http/openapi.json) is generated with the team's validator.
- Moderation's receiving contract now defines read-only
  `GET /internal/v1/moderation/applicants/{applicantId}/decision-facts`.
  Rules now consumes that exact method/path and schema. It no longer requires
  invented studentId/revision fields or a POST history binding.
- Applicant/Record #126 publishes generation, full initialization envelopes,
  canonical hashes, receipts and aggregate readiness. It remains draft. Its
  profile/claims/facts operations do not yet specify response JSON schemas.
- Gateway #48 is merged but still routes only Record/DMs membership. General
  service-operation routing and owned public-read target credentials remain needed.
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

Earlier owned internal paths remain candidate aliases/extensions, not an alternate
canonical catalog. Their definitions and schemas are retained under `ownedDrafts`
and `owned*` schemas in the single catalog. They are **not** Gateway registry
entries and must not be treated as approved team contracts. The duplicate
`contracts/business-http/` catalog has been removed.

## Initialization is NOT compatible yet

The earlier owned implementation uses a seed-only initialization payload and
CredentialsReady acknowledgements. #126 instead requires the full
ApplicantInitialized identity/deception payload, length-prefixed canonical hashing,
matching `{applicantId,eventId,eventHash,status:INITIALIZED}` receipts, origin-only
fanout, bounded leased delivery and nonrecursive aggregate readiness.

Do not wire the earlier callbacks to #126: a path binding alone cannot reconcile
those different protocols. Credential must adopt the agreed envelope/receipt and
generation protocol, and the owners must provide exact Applicant/Record JSON
response schemas. Rules also needs Session's persisted shift/applicant context
and Session adoption of its existing ruleset binding. Pending work stays explicit
in the public coordination issue and the owned parent issues, not hidden behind
a READY claim.

The safe publication is draft PRs to dev containing the implemented owned work,
canonical receiver compatibility, tests and this handoff. No release, image
publication, protected-branch push or submodule/image-pin promotion is requested.
Do not merge independently until contract reconciliation and real cross-owner
acceptance are complete. Service Discovery's latest dev remains verified and
needs no domain-call changes for this baseline.
