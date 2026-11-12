# Shared HTTP operation catalog (Lab 4: Gateway baseline, then message broker)

Tracked by [CPR issue #128](https://github.com/m3ower/faf-student-id-please/issues/128).
Builds on the membership candidate in [CPR #122](https://github.com/m3ower/faf-student-id-please/pull/122)
and [Gateway #48](https://github.com/Vasiok11/student-id-gateway-service/pull/48); it does not
replace them.

The machine-readable source of truth is
[`contracts/http/service-operations.json`](../contracts/http/service-operations.json). It lists
every business operation one service calls on another through the message broker, with its owner,
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
* **Through the message broker, never around it.** Callers send `<BROKER_URL><path>` with
  their own caller credential. The broker authenticates the caller, checks the operation's
  caller allowlist, chooses an instance by round robin among those whose circuit admits
  traffic, replaces the credential with the target's own credential, adds `X-Service-Name`,
  preserves `X-Trace-Id` and forwards the same path. A connection never established fails
  over once to another instance; nothing else is retried. Three failures of an instance
  within 3.5x the operation timeout trip its circuit and remove it from Discovery. No generic target URL, no shared universal token, no
  Discovery-token reuse, no player JWT on service routes. Discovery registration and
  polling stay direct control-plane traffic.
* **The target authenticates too.** Every handler checks the broker's target credential and
  the named caller itself, so a direct call to a private port or an ordinary player token
  grants nothing.
* **Budgets.** Target 500 ms, broker 750 ms, caller 1 s, each shortened by the caller's own
  remaining deadline. Callers never retry inside a request.
* **Idempotency.** Writes and callbacks carry a key fixed once by the caller
  (`scoreChangeId`, `eventId`). An identical repeat has no further effect; the same key with
  different content is a 409. Only idempotent operations are resent, and only by a durable
  outbox.
* **Events over HTTP are temporary.** `DecisionRecorded` and `ShiftStarted` keep the shared
  event envelope but travel as authenticated HTTP callbacks routed by the broker
  (request/reply). Queue and topic delivery are later work. Consumers never republish them.

## Operations and their status

| Operation | Owner | Callers | Status |
| --- | --- | --- | --- |
| `session.verifyMembership` `POST /internal/v1/session-memberships/verify` | Session | Record, DMs, **Moderation (requested addition)** | candidate (#122, Gateway #48) |
| `session.applyScoreChange` `POST /internal/v1/session-score-changes` | Session | Moderation | requested |
| `session.decisionRecorded` `POST /internal/v1/session-events/decision-recorded` | Session | Moderation | requested |
| `applicant.getDeception` `GET /internal/v1/applicants/{id}/deception?sessionId=` | Applicant | Moderation | requested |
| `credential.listApplicantCredentials` `GET /internal/v1/credentials?applicantId=&sessionId=` | Credential | Moderation | implemented, pending review (Credential #33) |
| `credential.validateCredential` `GET /internal/v1/credentials/{id}/validation` | Credential | Moderation | implemented, pending review (Credential #33) |
| `rules.evaluate` `POST /internal/v1/rules/evaluations` | Rules | Moderation | implemented, pending review (Rules #29) |
| `moderation.applicantDecisionFacts` `GET /internal/v1/moderation/applicants/{id}/decision-facts` | Moderation | Rules | implemented, pending review |
| `dms.shiftStarted` `POST /internal/v1/chat/shift-started` | DMs | Session | implemented, pending review |
| `dms.decisionRecorded` `POST /internal/v1/chat/decision-recorded` | DMs | Moderation | implemented, pending review |
| `record.enrollmentFacts` | University Record | Credential, Rules | owner to define |

`requested` means the caller's side is implemented against exactly this contract and the
owner has not accepted or implemented it. Until each one is implemented by its owner,
released, and routed by the broker, the corresponding end-to-end path is **not working**;
a stand-in used in a caller's unit tests does not change that.

## Routing in the message broker (Lab 4 Grade 5)

Service-to-service communication, round-robin load balancing and the circuit breaker moved
from the Gateway into the message broker
([broker #7](https://github.com/Andreiisthebest/student-id-message-broker/issues/7)).
The broker bundles a snapshot of [`contracts/http/service-operations.json`](../contracts/http/service-operations.json)
and routes every operation in it whose status is `candidate` or `implemented-pending-review`
(all 31 today), with that operation's owner as the target, its caller allowlist and its
`budgetsMs.broker` deadline. `requested` and `owner-to-define` entries are not routed. The
snapshot is updated together with this catalog; the broker never fetches routing policy at
runtime.

Callers' own secrets go in the broker's `BROKER_CALLER_TOKENS_JSON`; each target's
`<TARGET>_INTERNAL_TOKEN` is given to the broker and that target. (The Gateway also holds some
targets' credentials for public routes, see `publicBackendCredentials`; separating those is an
open review point.) Every caller migrates its own base URL and
credential (`BROKER_URL`, `BROKER_SERVICE_TOKEN`): Moderation and Discord DMs have. The
Gateway's service route (#48) and its public `/api/v1/internal/...` route to DMs are then
unused and should be removed by the Gateway owner
([Gateway #51](https://github.com/Vasiok11/student-id-gateway-service/issues/51)). The Gateway
keeps public routing, JWT verification, `X-Player-Id` binding and WebSocket negotiation.

## Identity for public requests

Moderation and DMs take the acting player only from `X-Player-Id`, which Gateway #48 sets
from the verified JWT subject and which the current Gateway `main` still passes through
from the client. Until #48 (or an equivalent) is released, identity binding through the
deployed Gateway is **not** in place, whatever the services do. Both services' business
ports must stay private; DMs can publish only its WebSocket listener (`PUBLIC_WS_PORT`),
where it verifies the Player access JWT itself.

## Applicant/Record caller migration

The [Applicant/Record broker migration candidate](applicant-record-broker-migration.md) switches both callers and Record membership to BROKER_URL/BROKER_SERVICE_TOKEN, without Gateway/direct fallback. It uses the unchanged current 39-operation catalog; Broker issue #12 owns bundling that snapshot. Public Gateway routes and direct Discovery registration stay in place. Matching images and actual current-peer acceptance remain deployment gates.
