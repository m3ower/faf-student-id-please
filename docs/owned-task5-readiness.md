# Owned Task 5 preparation: current implementation handoff

Status: owned business workflows are implemented in local candidate source.
This is **not** a complete Task 5 / full-stack READY claim: peer schema agreement,
Gateway registration and real multi-service acceptance remain outstanding.
This supersedes the earlier membership-only handoff and its immutable ZIP snapshot.

**Publication update:** teammates have now merged CPR #129's canonical HTTP
catalog and published Applicant/Record draft #126. The shared list/validation/
evaluation receivers and history client have been reconciled. The initialization
protocol has a real mismatch, not just missing paths; follow
[the latest reconciliation](owned-contract-reconciliation.md) before integration.
All authoritative schemas now live in `contracts/http/service-operations.json`;
the earlier duplicate `contracts/business-http/` catalog has been removed.

## Credential: implemented

- Service-only initialization, persisted document retrieval, structural inspection,
  authoritative per-document and applicant-batch validation.
- Generation fetches Applicant seed/identity/deception context and privileged
  Record facts through Gateway; no fixture IDs, caller-supplied authenticity flag
  or cross-database reads.
- PostgreSQL stores initialization identity/fingerprint, generated documents,
  generation timestamps/revisions, per-document content hashes and ready outbox.
  Existing CRUD documents without provenance remain UNVERIFIED, not authentic.
- Fresh Record facts plus unchanged trusted provenance determine authenticity.
  Structural validity, authenticity and expiry are distinct results.
- Applicant, Record or Credential may initiate the same versioned workflow.
  Identical replay is effect-free; changed event/applicant/seed is 409.
  A failed dependency leaves PENDING; a failed callback leaves DELIVERY_PENDING.
- Explicit recover resumes after failure/restart without regeneration. Outbox
  row locks coordinate replicas. Delivery is at least once: receiver-side durable
  eventId/content deduplication is mandatory, including crash-after-remote-commit.
  READY requires both matching durable callback acknowledgements.
  Consumers do not rebroadcast ApplicantInitialized.

## Rules: implemented

- Moderation-only POST /internal/v1/rules/evaluations accepts sessionId/applicantId,
  not supplied facts. Session supplies readiness/shift/version/requested channel.
- Reads the persisted immutable shift ruleset; rejects version mismatches.
  Applicant, privileged Record and actual Credential validation are queried through
  Gateway, in parallel where independent. Prior-ban history is read-only and only
  requested when its rule is present. It never recursively submits a decision.
- Rejects missing, null, malformed, mismatched, unknown or failed authoritative
  facts; never substitutes fabricated ACCEPT. Records Applicant/Record revisions.
- Rule CRUD versions policy; persisted shift binding survives rotation/deletion
  and retries/restarts/another connection. Conflicting rebinding returns 409.
- Additional persisted types: AUTHENTIC_CREDENTIALS, CONSISTENT_CLAIMS,
  CURRENTLY_ENROLLED. Configure policy before starting/binding a shift.
- Public caller-facts evaluation deliberately returns 410 CALLER_FACTS_RETIRED.
  This is a **breaking candidate contract change**, requiring coordinated review
  and release versioning before rollout. Existing published images are unchanged.

## Discovery: verified, no change required

Current dev: 0f4c538f2b5d6eab6c128cd251c959b8e7872a39.
Current main/CPR pin: ee681e9b90af44989f85ffb4e042621a0f503e82.
Their application and requirements source are identical. Latest dev was checked
in an isolated worktree; the original stale checkout and CPR gitlink were preserved.

Registration, polling, bounded notifications and circuit-removal behavior remain
real control-plane responsibilities. No artificial domain calls or broker-topic
features were added. Broker migration is outside this baseline implementation.

## Contracts and required wiring

Canonical owned receivers and schemas:
[operation catalog](../contracts/http/service-operations.json),
[OpenAPI](../contracts/http/openapi.json).

catalog `ownedDrafts.consumerPorts` specifies exact consumer-required request/response
schemas. These are proposals requiring receiving-owner agreement, not claims that
a guessed peer URL exists. No default peer paths or arbitrary forwarding URLs exist.

Each service requires GATEWAY_URL, its distinct GATEWAY_SERVICE_TOKEN,
its receiver token CREDENTIAL_INTERNAL_TOKEN or RULES_INTERNAL_TOKEN, and complete
BUSINESS_HTTP_BINDINGS_JSON. Missing/malformed settings fail startup. The JSON maps
these logical ports to receiver-reviewed POST /internal/v1/... paths on Gateway:

| Service | Required consumer-port names |
| --- | --- |
| Credential | applicant.context, record.facts, applicant.ready, record.ready |
| Rules | session.context, applicant.context, record.facts |

Rules' Credential batch operation already has our canonical path:
POST /internal/v1/credentials/validate-applicant.

The Gateway owner must register the catalog's exact operation/caller allowlists,
accept separate caller credentials, replace them with receiver-specific target
credentials, preserve traces and stamp authenticated caller identity. Public
reads must bind player identity to verified JWT subject. No generic internal proxy.

Peer owners must implement/reconcile the port schemas, bind real paths, durably
acknowledge CredentialsReady, and make Session respect shift binding and complete
initialization readiness. Pending initialization recovery is explicit and bounded;
the coordinator must invoke it, not assume an automatic background loop exists.

## Verification: 2026-11-11

- Credential: full Maven verify, **69 tests, no failures/errors/skips**;
  real PostgreSQL included; **95.2% line coverage**, existing >=70% gate passed.
- Rules: Linux Go 1.23 full race suite with PostgreSQL and network contract peers,
  passed; **84.3% total coverage**, 89.3% for the rules package.
- Discovery: **180 tests**, **96.9% coverage** on current dev.
- Shared catalog: both existing consistency/budget tests passed.
- Earlier runs exposed a race in test-peer response mutation (fixed with its mutex)
  and bounded Credential recovery timeouts; their timing cause was not isolated. The recovery test now
  explicitly retries the same idempotent recovery action once after 504 and still
  requires real success and exactly one stored document set. No production
  deadlines were raised and no timeout is accepted as successful initialization.
- Tests include each allowed initialization producer, duplicate/conflicting events,
  concurrent initialization/replay, persisted recovery through a recreated workflow,
  actual DB changes affecting validation, provenance tampering, pinned versions,
  denied/spoofed callers, failed/malformed/missing dependencies and cancellation.

The fact-service/Gateway peers in the new workflow tests are explicitly test
doubles. Credential and Rules themselves use their actual database and HTTP/client
implementations. This is **not** a real-peer/Gateway full-stack acceptance run.
That final correlated-trace test remains necessary after shared wiring/review.

## Reproduce without touching the running team stack

After reconciliation with #129: Credential `mvn verify` passed all **70 tests**;
Rules' complete normal Go suite with disposable PostgreSQL passed with **83.2%**
total coverage (**88.7%** for its rules package). The race result above predates
this reconciliation; the updated Linux race check must pass in the private PR.
These checks use network test peers, not the other owners' private applications.

Use an explicitly disposable PostgreSQL database only. Never target the existing
Compose database/volumes.

```powershell
$env:CREDENTIAL_TEST_JDBC_URL = 'jdbc:postgresql://127.0.0.1:<test-port>/postgres'
$env:CREDENTIAL_TEST_DB_USER = 'postgres'
Push-Location services/credential-service
mvn -B verify '-Ddebug=false'
Pop-Location

$env:RULES_TEST_DSN = 'postgres://postgres@127.0.0.1:<test-port>/postgres?sslmode=disable'
Push-Location services/rules-service
go test -race ./... '-coverprofile=coverage.out'
Pop-Location
```

Disabling Spring debug in this command avoids a global DEBUG environment setting;
normal INFO request logging and sensitive-data assertions remain enabled.
Windows race builds require supported CGO tooling; the verified race run used Linux.

These are unreleased candidates published through the linked draft PRs, not
reviewed stable releases. No stable image or release pin is changed, and no
teammate private source or Gateway implementation is edited. Keep the PRs draft
until contract reconciliation and live integration are complete.
