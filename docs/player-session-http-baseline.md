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

## Remaining receiving-owner decisions

Rules must publish its service-only selection method/path for
`{sessionId,difficulty}` → `{sessionId,rulesetVersion>=1}` and guarantee the same
frozen selection on retries. It is owner-to-define and deliberately unrouted.
Session's optional configured internal selection path does not grant a routing
allowlist or imply that Rules implements it. Missing configuration fails503.

Applicant/Record's candidate specifies profile/facts paths, but some responses
remain unspecified objects in its OpenAPI. These are labelled unknown detailed
schemas, not executable proof of business compatibility. Applicant must confirm
the Session profile whitelist (name,studentId,major,year,universityStatus,role,courses)
and publish its exact response. No Session fallback invents those fields.

Credential/Rules validation/evaluation operations requested by Moderation remain
receiver-owned work. DMs callback correctness, Applicant's complete initialization
fan-out and Moderation's end-to-end decision/appeal delivery require their owners'
real builds. This PR does not modify those private services or claim them READY.

## Verification and deployment handoff

Owned unit/database suites and >=70% coverage gates apply. Real network acceptance
uses ephemeral keys, synthetic accounts and disposable PostgreSQL databases, with
one trace through actual Player→Gateway→Session and Session→Gateway→Player calls.
No shared stack/production database is used. Exact results, source SHAs and sanitized
trace evidence accompany the private source handoff. Historical fixture tests alone
are never integration evidence.

The real network subset includes login→team→create/join→roles/access/membership,
denial/spoofing, duplicate scores/events, completion→XP→progression callback and
Session restart persistence. The completion phase explicitly seeds the external
applicant-ready prerequisite in the disposable Session database; it does **not**
verify real Rules/Applicant/DMs/Moderation initialization. Full coordinated gameplay
acceptance stays blocked until those owners' contracts and real endpoints are ready.

The updated Player collection obtains real login tokens transiently and exercises
CRUD/teams/refresh/logout. Session's Core folder creates real accounts/team/session;
its Optional shift folder must be run manually with real external dependencies and
readiness/decision steps. Never export populated tokens or private environments.
Other owners' collections are unchanged by this feature.

After two approvals/code-owner review and green CI, merge features to dev, then
release dev→main under each repository's rules. Main CI publishes lab-versioned
images; verify revision labels and immutable digest before a separate CPR image/
pointer/private-network/credential deployment PR. Existing Compose and published
Lab3 images are not automatically updated by these source changes.
