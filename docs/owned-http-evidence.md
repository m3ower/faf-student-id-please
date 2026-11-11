# Owned Gateway communication evidence ? 2026-11-12

The requested pre-migration Gateway baseline is implemented in the owned candidates below.
This does not claim current Credential/Session full-game readiness or migrate to broker transport.

| Component | Source / exact peer scope |
| --- | --- |
| Applicant PR #23 | `9f58860452431ec9fba13864bd6de9498a880c52`; core Java suite 40 tests / 96.36% coverage |
| Record PR #25 | `576260f1f38d47b01eb3bf7d0a242b6929958c02`; fresh race suite passed, 80.0% instrumented-line / 79.3% statement coverage |
| Gateway peer | unchanged owner PR #52 at `0a6d49649e0dd3610e206e8afc4ffbf76b34ba87` |
| Session peer | existing historical membership image `sha256:f3ac52d0fb68368221dc120602b433e930785247575b11c5bc1751871222aa4e`; membership only, not current PR #26 gameplay |
| Current CPR definitions checked | dev `f4bd2d1931a9b8ff833bc7e3f18a213517049d1f`: 31 operations/examples; 15 contract/validator/vector tests passed at 94% coverage |

**53 real-network checks passed.** Applicant -> Gateway -> Record and Record -> Gateway ->
Applicant delivered actual generated initialization envelopes and matching cross-language
receipts. No peer response or READY prerequisite was seeded. Tests verify idempotent replay,
conflicting input rejection, claim/truth disagreement, NOT_ENROLLED truth, pending Session
responses, private deception caller/session checks and correlated traces at all three hops.

Record -> Gateway -> the real historical Session membership handlers verified persisted roles,
explicit access grants, denial of an unassigned junior spoofing another player's header,
moderator denial, dependency outage and recovery. Player JWTs were issued by an isolated test
signer; this is not a live Player login or current Session queue/shift acceptance claim.

The test also rejected a direct backend spoof before membership, restarted the actual owned
processes, and read the same committed receipts from second replicas. No credentials appeared
in candidate logs. The owned operations, allowlists, budgets and referenced schemas bundled in
the unchanged Gateway image match the current CPR, excluding broker-only transport metadata.
Only Gateway published a random loopback port; all backend ports stayed private. All disposable
containers, including profile-enabled replicas, and their volumes/networks were removed.

Reproduce using Applicant's `scripts/verify_gateway_integrations.py` and its
`docs/gateway-network-tests.md`. Exact local image IDs, results and traces are recorded in
ignored local evidence; private source and runtime credentials are not published in CPR.

## What the newest CPR does and does not provide

The current CPR provides the exact interfaces used here and receiver handoff documentation.
Credential and Session are still private gitlinks, pinned respectively to `d3386ffd992efe486f774f87875e7cf63cd07129`
and `055919cba0ee6838aca2f3b758148a855a9775a7`; the parent CPR does not contain their application source.
The current account cannot fetch those repositories. The old supplied Credential ZIP still
contains runtime CredentialMock/fixture source, not the newer private initialization implementation.

The merged [reconciliation](owned-contract-reconciliation.md#initialization-is-not-compatible-yet)
explicitly requires Credential to adopt the full immutable session-bound envelope, digest and
matching receipt protocol. Its older seed-only initialization and CredentialsReady callbacks
are not interchangeable with Applicant/Record initialization. They remain unapproved aliases
under ownedDrafts, not approved Gateway registry routes. This owned change does not silently
reinterpret them or fabricate successful credential initialization.

Remaining: compatible actual Credential initialization; actual current Session queue/gameplay
acceptance; required reviews and green CI for the latest PR heads; reviewed releases/pins.
The merged broker transport documentation is preserved, but broker migration is outside this
explicitly requested Gateway-phase implementation. Teammate application source was not changed.

---

# Owned HTTP baseline evidence — 2026-11-11

This report covers Applicant and University Record source candidates. It does not certify
the shared system, actual Gateway operation registry, Credential implementation or broker migration.

## Source and workflow

| Service | Implementation PR / issue | Tested source |
| --- | --- | --- |
| Applicant | [PR #23](https://github.com/Andreiisthebest/student-id-applicant-service/pull/23), [issue #22](https://github.com/Andreiisthebest/student-id-applicant-service/issues/22) | `55bed1d9b0921ddf2062049a8348344b62db57b9` |
| University Record | [PR #25](https://github.com/Andreiisthebest/student-id-university-record-service/pull/25), [issue #24](https://github.com/Andreiisthebest/student-id-university-record-service/issues/24) | `d8bec9e2e0c6336eb260399952e66d9d7c5bd042` |

Both PRs target dev, are assigned, contain the four required sections and have actual GitHub
closing-issue associations verified through the API. Review requests go to the two other
write-access collaborators. Both repositories now enforce two approvals, code-owner review,
last-push approval, strict `verify` CI, resolved review threads and no bypass/force-push/deletion
on dev/main. Dev requires squash and linear history; main uses release merge commits.
No service PR has been merged or stable image published by this work. Source candidate
1.0.0 records the new required authentication/configuration contract.

## Completed local checks

| Check | Result |
| --- | --- |
| Applicant Java 21/Maven `clean verify`, isolated PostgreSQL | 40 tests; 0 failures/errors/skips; 96.36% line coverage; >=70% gate passed |
| Record fresh `go test -count=1 -p 1 -race`, isolated PostgreSQL | passed; 80.0% instrumented-line / 79.3% statement coverage; >=70% gate passed |
| Both original Dockerfiles | local candidate image builds passed; Record image compiles with Go 1.23 |
| Single canonical HTTP catalog/OpenAPI/examples | 26 operations and 26 examples validated |
| Catalog validator tests | 9 passed; 93% coverage; >=70% gate passed |
| Actual owned images with fresh DBs, over HTTP | 32 receiver-contract checks passed, including actual process restart and second replicas |

The receiver checks exercised authenticated initialization in both actual images, denied missing
credentials/wrong callers, identical replay, conflicting initialization, no consumer ownership
takeover, pending readiness, cross-session answer-key denial, private deception allowlist,
independently persisted claims/truth disagreement, and matching cross-language receipt hashes.
Restarted containers and second replicas returned the same committed receipts and Record truth.
The HTTP client in this test supplied the receiving Gateway credentials directly on a private
test network. This validates the receivers; it is not a real Gateway routing test.

Unit/database tests additionally exercised concurrent generation, immutable claims, durable
outbox progress, stale-lease fencing/recovery, matching receipt acknowledgement, malformed,
oversized, denied and slow HTTP contract peers, bounded parallel readiness and cancellation.
These peer servers were test doubles and are not evidence of a live Credential implementation.

## Remaining integration gates

1. Gateway owner registers the exact new Applicant/Record operations and callers/target
   credentials from the catalog. [Gateway issue #51](https://github.com/Vasiok11/student-id-gateway-service/issues/51)
   still tracks the broader registry; membership alone is insufficient.
2. Credential owner accepts/implements `credential.initialize` and `credential.getInitialization`
   using the immutable session-bound envelope and matching receipt/deduplication semantics.
   Existing envelopes without sessionId are not accepted by these new HTTP receivers.
3. Session owner accepts the warmup/generate/poll-ready protocol. Only fully ready data may
   enter the queue; no unagreed shift callback is described as implemented here.
4. Complete the two reviews, code-owner review and remote CI on these PRs, followed by reviewed
   releases with immutable image provenance and a deliberate update of shared deployment pins.
5. Verify actual calls through the deployed Gateway and peers, correlated business traces,
   cross-owner initialization/recovery and game acceptance. The shared deployment still selects
   older images and was not changed by these owned feature PRs.

Architecture, the combined Postman collection, other owners' source and broker transport remain
outside this change. Only the affected README sections and separate owned collections are updated.
Local test logs, runtime credentials and private source stay outside the public CPR. Local image
IDs are recorded privately; no registry digest for a reviewed release is claimed.
