# Shared HTTP operation catalog (Lab 4 Gateway baseline)

Tracked by [CPR issue #128](https://github.com/m3ower/faf-student-id-please/issues/128).
Builds on the membership candidate in [CPR #122](https://github.com/m3ower/faf-student-id-please/pull/122)
and [Gateway #48](https://github.com/Vasiok11/student-id-gateway-service/pull/48); it does not
replace them.

The machine-readable source of truth is
[`contracts/http/service-operations.json`](../contracts/http/service-operations.json). It lists
every business operation one service calls on another through the Gateway, with its owner,
method, path, request and response schemas, error codes, caller allowlist, idempotency rule
and deadline budget. [`openapi.json`](../contracts/http/openapi.json) is generated from it and
[`examples/`](../contracts/http/examples) holds one request/response pair per operation, with
placeholder credentials only.

```powershell
python scripts/validate_http_contracts.py                  # catalog, examples, OpenAPI in sync
python scripts/validate_http_contracts.py --write-openapi  # after editing the catalog
python scripts/validate_http_contracts.py --check dms.decisionRecorded response reply.json
```

CI (`.github/workflows/http-contracts.yml`) runs the same validation and the validator's own
tests with the 70% coverage gate.

## Rules

* **The receiving owner owns the operation.** Only that owner changes its method, path,
  schemas, errors, authorization or idempotency. A caller that needs an operation the owner
  has not published adds it with status `requested`, the exact dependency contract it will
  call, and asks the owner to accept or replace it.
* **Through the Gateway, never around it.** Callers send `<GATEWAY_URL><path>` with their own
  caller credential. The Gateway authenticates the caller, checks the operation's caller
  allowlist, replaces the credential with the target's own credential, adds
  `X-Service-Name`, preserves `X-Trace-Id` and forwards the same path to one
  Discovery-selected instance. No generic target URL, no shared universal token, no
  Discovery-token reuse, no player JWT on service routes. Discovery registration and
  polling stay direct control-plane traffic.
* **The target authenticates too.** Every handler checks the Gateway's target credential and
  the named caller itself, so a direct call to a private port or an ordinary player token
  grants nothing.
* **Budgets.** Target 500 ms, Gateway 750 ms, caller 1 s, each shortened by the caller's own
  remaining deadline. Callers never retry inside a request.
* **Idempotency.** Writes and callbacks carry a key fixed once by the caller
  (`scoreChangeId`, `eventId`). An identical repeat has no further effect; the same key with
  different content is a 409. Only idempotent operations are resent, and only by a durable
  outbox.
* **Events over HTTP are temporary.** `DecisionRecorded` and `ShiftStarted` keep the shared
  event envelope but travel as authenticated HTTP callbacks through the Gateway. This is not
  RabbitMQ or Message Broker delivery. Consumers never republish them.

## Operations and their status

| Operation | Owner | Callers | Status |
| --- | --- | --- | --- |
| `session.verifyMembership` `POST /internal/v1/session-memberships/verify` | Session | Record, DMs, **Moderation (requested addition)** | candidate (#122, Gateway #48) |
| `session.applyScoreChange` `POST /internal/v1/session-score-changes` | Session | Moderation | requested |
| `session.decisionRecorded` `POST /internal/v1/session-events/decision-recorded` | Session | Moderation | requested |
| `applicant.getDeception` `GET /internal/v1/applicants/{id}/deception?sessionId=` | Applicant | Moderation | implemented, pending review (CPR #126) |
| `credential.listApplicantCredentials` `GET /internal/v1/credentials?applicantId=&sessionId=` | Credential | Moderation | requested |
| `credential.validateCredential` `GET /internal/v1/credentials/{id}/validation` | Credential | Moderation | requested |
| `rules.evaluate` `POST /internal/v1/rules/evaluations` | Rules | Moderation | requested |
| `moderation.applicantDecisionFacts` `GET /internal/v1/moderation/applicants/{id}/decision-facts` | Moderation | Rules | implemented, pending review |
| `dms.shiftStarted` `POST /internal/v1/chat/shift-started` | DMs | Session | implemented, pending review |
| `dms.decisionRecorded` `POST /internal/v1/chat/decision-recorded` | DMs | Moderation | implemented, pending review |
| `record.enrollmentFacts` `GET /internal/v1/records/{id}/facts` | University Record | Credential, Rules | implemented, pending review (CPR #126) |

`requested` means the caller's side is implemented against exactly this contract and the
owner has not accepted or implemented it. Until each one is implemented by its owner,
released, and routed by the Gateway, the corresponding end-to-end path is **not working**;
a stand-in used in a caller's unit tests does not change that.

## Gateway operation registry request

Gateway #48 accepts one operation (`session.verifyMembership`) from two callers, with one
target credential (`SESSION_INTERNAL_TOKEN`). The catalog needs the Gateway owner to
generalise that into a registry keyed by method and path:

| Method and path | Target | Allowed callers | Target credential |
| --- | --- | --- | --- |
| `POST /internal/v1/session-memberships/verify` | session-service | university-record-service, discord-dms-service, moderation-service | `SESSION_INTERNAL_TOKEN` |
| `POST /internal/v1/session-score-changes` | session-service | moderation-service | `SESSION_INTERNAL_TOKEN` |
| `POST /internal/v1/session-events/decision-recorded` | session-service | moderation-service | `SESSION_INTERNAL_TOKEN` |
| `GET /internal/v1/applicants/{uuid}/deception` | applicant-service | moderation-service | `APPLICANT_INTERNAL_TOKEN` |
| `GET /internal/v1/credentials` | credential-service | moderation-service | `CREDENTIAL_INTERNAL_TOKEN` |
| `GET /internal/v1/credentials/{uuid}/validation` | credential-service | moderation-service | `CREDENTIAL_INTERNAL_TOKEN` |
| `POST /internal/v1/rules/evaluations` | rules-service | moderation-service | `RULES_INTERNAL_TOKEN` |
| `GET /internal/v1/moderation/applicants/{uuid}/decision-facts` | moderation-service | rules-service | `MODERATION_INTERNAL_TOKEN` |
| `POST /internal/v1/chat/shift-started` | discord-dms-service | session-service | `DMS_INTERNAL_TOKEN` |
| `POST /internal/v1/chat/decision-recorded` | discord-dms-service | moderation-service | `DMS_INTERNAL_TOKEN` |

`GATEWAY_SERVICE_TOKENS_JSON` then needs entries for `moderation-service`,
`session-service` and `rules-service` as callers. Gateway's public `/api/v1/internal/...`
route to DMs must be removed: DMs no longer serves it, and internal operations are reached
only through the service route above.

## Identity for public requests

Moderation and DMs take the acting player only from `X-Player-Id`, which Gateway #48 sets
from the verified JWT subject and which the current Gateway `main` still passes through
from the client. Until #48 (or an equivalent) is released, identity binding through the
deployed Gateway is **not** in place, whatever the services do. Both services' business
ports must stay private; DMs can publish only its WebSocket listener (`PUBLIC_WS_PORT`),
where it verifies the Player access JWT itself.


## Owned initialization and ready-data operations

[The owned HTTP guide](owned-real-integrations.md) specifies the additional Applicant/Record
receiving operations, including generate, initialize, local receipt, aggregate readiness and
resume, plus Applicant profile, claims and warmup. Their exact caller allowlists and all
schemas/examples live in this same executable catalog, with status implemented-pending-review.
Credential initialize/local-receipt are requested dependencies; only Credential's owner can
accept their implementation. No second OpenAPI catalog is maintained.

The immutable session-bound envelope is a new HTTP candidate; legacy unbound envelopes are
rejected. A consumer never republishes initialization or takes delivery ownership. Session
receives 202 without profile/claims while any owner receipt is missing. Internal targets cap
work at 500 ms with parallel receipt checks. Generation/warmup/resume return 202; these success
responses are represented in generated OpenAPI and validated in examples.

The operation registry request above must also include the new owned rows from the catalog;
Gateway #48 still routes membership only. These contracts and unit/DB/HTTP-peer tests do not
claim a live cross-owner deployment or authorize broker migration.
