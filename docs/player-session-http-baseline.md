# Player/Session real HTTP baseline (review candidate)

Tracked by [CPR #125](https://github.com/m3ower/faf-student-id-please/issues/125),
[Player #20](https://github.com/Vasiok11/student-id-player-service/issues/20),
[Session #25](https://github.com/Vasiok11/student-id-session-service/issues/25) and
[Gateway #49](https://github.com/Vasiok11/student-id-gateway-service/issues/49).
This is source awaiting review; the shared Compose still pins previous published
Lab 3 images. No stable image, pointer or deployment upgrade is included here.

## Shared contract and boundaries

The executable source of truth remains
[`contracts/http/service-operations.json`](../contracts/http/service-operations.json),
with generated OpenAPI and synthetic examples. This extends the merged HTTP
catalog, preserving the existing membership path and receiving owners' published
Applicant/Record and DMs method/path/caller definitions. It does not make a caller's
requested Credential/Rules API routable. Receiver review is required before consumers
merge. Schema imports cite the owners' public CPR candidate commits; source or
image publication is not inferred from those proposals.

All business clients use Gateway. Direct Discovery registration/lookup remains
control-plane HTTP. No broker, gRPC, new architecture diagram or live RabbitMQ
transport is introduced. The Gateway bundles a reviewed snapshot of this catalog,
allows only its exact accepted operations, uses Discovery selection/Round-Robin/
circuit removal unchanged, and maintains separate bounded operation/public pools.

Player now issues real RS256 access tokens and rotating, hashed refresh tokens.
Gateway validates the existing issuer/audience/expiry contract, removes the user
Authorization and untrusted identity headers, then supplies a separate target
credential and verified X-Player-Id. Caller and target service secrets are all
distinct; Discovery's secret cannot be reused. Backend business ports must remain
private. Production startup requires valid business settings, with no runtime
fixture fallback. Generate secrets/keys privately; `.env` and private signing
material must never enter the public CPR or a source archive.

## Owned operations and state

Player owns real identity, refresh/revocation families, team membership and
progression. Session create/join call Player verification/team lookup. Session owns
shift membership, roles, explicit record/channel grants, ruleset version, queue IDs,
readiness, scores, decisions and delivery progress. It never owns applicant claims,
university truth, credential authenticity or deception.

| Receiver | Accepted operation | Trigger/caller |
| --- | --- | --- |
| Player | `players.verify`, `player-teams.lookup` | Session create/join/start validation |
| Session | `session.verifyMembership` | Record/DMs/Credential/Rules/Moderation authorization checks |
| Session | `session-state.get` | Moderation/Rules/Credential/Applicant; read-only, no recursive initialization |
| Session | `session.applyScoreChange` | Moderation; single score/penalty mutation |
| Session | `session.decisionRecorded` | Moderation; count/process once after score, no double delta |
| Player | `session-completions.record` | Session end via durable outbox |
| Session | `player-progressions.record` | Player's durable progression callback |

Canonical names/methods/paths, schemas, budgets and errors are in the catalog, not
an alternative API table. Public team routes, access assignment and shift control
are documented in the owners' private README guides and updated owned Postman
collections. Membership remains Session500ms/Gateway750ms/caller1000ms. Added
callers preserve independent receiver authorization; no service can impersonate
a player to obtain Record facts.

## Exact additive clarifications for review

* Score changes use `{scoreChangeId,sessionId,decisionId,applicantId,moderatorId,
  reason,delta,penalties}`. Reason DECISION/APPEAL_REFUND/DECISION_VOID; unique
  scoreChangeId and (sessionId,decisionId,reason); same-content replay harmless,
  conflicting replay409. Initial score targets current applicant and precedes its
  DecisionRecorded callback. Adjustments change totals only, not inferred correctness.
  New changes after completion are rejected; earlier identical replay is acknowledged.
* DecisionRecorded carries the actual moderatorId and scoreDelta, checked against
  the committed initial change. It increments processed/correct/incorrect once and
  clears current applicant; moderator explicitly advances the ready queue afterward.
* SessionCompleted.players is UUID[], accuracy is a fraction0..1, outcome PASSED/FAILED.
  Session's proposed explicit result policy is PASSED iff all queued applicants
  are processed, at least one was processed, counts match, accuracy>=0.8 and score>=0;
  otherwise FAILED. No placeholder result.
* Player's explicit policy: PASSED+100XP, FAILED+0, once per session/player;
  level=1+floor(totalXP/500), senior rank from level5. Accuracy averages completed
  shift accuracy, disciplinary actions accumulate penalties. XP means new total.
  Player owns future policy changes; this is not a team-wide duplicated XP formula.
* PlayerProgressed adds sessionId for correlation. Receipts use matching eventId
  and PROCESSED/DUPLICATE. Session records receipt/SSE notification without changing
  Player-owned XP. Existing terminal SSE closes at shift end; clients read Player's
  profile afterward rather than expecting late progression on a closed stream.
* GetSessionState reports rulesetVersion0 before selection. It never calls Rules or
  initializes applicants. Read operations cannot create recursive service cycles.
* Shift initialization persists original request/applicant/event IDs, seed and
  difficulty before remote work. Pending/blocked initialization exposes no applicant;
  lobby mutations are frozen. Host resume preserves the original identities.

## Latest receiving-owner reconciliation and remaining gates

CPR #126 at90fc1b9 now supplies exact Applicant/Record response schemas. The
catalog imports those receiver definitions and canonical operation names, including
202 readiness/profile responses; Session reads the exact {applicant:{...}} wrapper.
No unspecified profile/facts placeholder remains.

CPR #127 at28e3d8e now publishes Rules' immutable POST /internal/v1/rulesets/bind
and GET /internal/v1/rulesets/sessions/{sessionId}/shifts/{shiftId}. Session/Gateway
accept those receiver-owned paths and {eventId,sessionId,shiftId} request. One
Session already represents one shift, so Session supplies shiftId=sessionId,
persists binding intent before remote work and keeps the same eventId on recovery.
The worker finalizes the ShiftStarted payload only after the correlated version
is stored. WAITING_RULES exposes no applicant; no guessed path or hardcoded version.

The three canonical Credential list/validation and Rules evaluation operations
are receiver-implemented candidates now, so Gateway may route their exact allowlists.
The earlier owned aliases and incompatible Credential initialization endpoints
are not automatically promoted.

Credential's seed-only initialization/receipt protocol still differs from
Applicant/Record's full session-bound envelope, canonical hash and matching receipts.
Those owners must reconcile it before aggregate readiness can work. Their proposed
consumer context ports (including requestedChannel and applicantId inputs) also
need adaptation to Session's actual stored-state API or an agreed additive operation.
Session supplies shiftId in stored context, without inventing another owner's truth.
These are semantic gates, not problems a configurable forwarding path can solve.

DMs callback correctness, real initialization fan-out and Moderation's complete
decision/appeal delivery require real owner builds and coordinated acceptance.
No private peer code is changed or certified READY by this PR.

## Verification and deployment handoff

Owned unit/database suites and >=70% coverage gates apply. Real network acceptance
uses ephemeral keys, synthetic accounts and disposable PostgreSQL databases, with
one trace through actual Playerâ†’Gatewayâ†’Session and Sessionâ†’Gatewayâ†’Player calls.
No shared stack/production database is used. Exact results, source SHAs and sanitized
trace evidence accompany the private source handoff. Historical fixture tests alone
are never integration evidence.

The real network subset includes loginâ†’teamâ†’create/joinâ†’roles/access/membership,
denial/spoofing, duplicate scores/events, completionâ†’XPâ†’progression callback and
Session restart persistence. The completion phase explicitly seeds the external
applicant-ready prerequisite in the disposable Session database; it does **not**
verify real Rules/Applicant/DMs/Moderation initialization. Full coordinated gameplay
acceptance stays blocked until initialization/context semantics and real owner endpoints are reconciled.

The updated Player collection obtains real login tokens transiently and exercises
CRUD/teams/refresh/logout. Session's Core folder creates real accounts/team/session;
its Optional shift folder must be run manually with real external dependencies and
readiness/decision steps. Never export populated tokens or private environments.
Other owners' collections are unchanged by this feature.

After two approvals/code-owner review and green CI, merge features to dev, then
release devâ†’main under each repository's rules. Main CI publishes lab-versioned
images; verify revision labels and immutable digest before a separate CPR image/
pointer/private-network/credential deployment PR. Existing Compose and published
Lab3 images are not automatically updated by these source changes.
