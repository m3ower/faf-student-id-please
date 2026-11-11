# Lab 4 Gateway membership baseline (candidate)

Tracked by [CPR issue #121](https://github.com/m3ower/faf-student-id-please/issues/121),
[Gateway #47](https://github.com/Vasiok11/student-id-gateway-service/issues/47) and
[Record #21](https://github.com/Andreiisthebest/student-id-university-record-service/issues/21).

The verified scope is the actual enrollment authorization in University Record
and actual channel membership in Discord DMs. Both call Session through Gateway.
Applicant/credential/rules generation, Moderation decisions and Player progression
remain fixtures or planned contracts. This baseline does not implement those game
features or migrate any traffic to Message Broker.

## Public player identity

Gateway continues to verify RS256 access JWTs using the existing Player issuer,
audience and expiration contract. On protected REST requests it discards incoming
`X-Player-Id` values and sets one from the verified `sub`. It removes player JWTs
and untrusted service identity/credential headers before forwarding. Public
login/health/preflight requests carry no player identity. WebSocket negotiation
returns `403 PLAYER_ID_MISMATCH` when its `playerId` differs from the token subject.
Domain services remain responsible for permissions.

Player login/token issuance is not implemented in the supplied source. The
isolated verifier uses fresh test-signed tokens and configures only the matching
public key on Gateway. That verifies Gateway authentication, not Player login.

## Explicit Session access assignments

After assigning roles while the session is in `LOBBY`, its authenticated host can
call:

```http
PUT /api/v1/sessions/{sessionId}/access
Authorization: Bearer <host-access-token>
Content-Type: application/json

{"assignments":[{"playerId":"22222222-2222-2222-2222-222222222222","recordAccess":["ENROLLMENT_LIST"],"channels":["#enrollment-check","#general-mod-chat"]}]}
```

Success is `204`. Unknown sessions return `404 SESSION_NOT_FOUND`, a non-host
receives `403 SESSION_HOST_REQUIRED`, and an active/completed session returns
`409 SESSION_NOT_IN_LOBBY`. Invalid, duplicate, unknown-player or unsupported
assignments return `422 INVALID_ACCESS_ASSIGNMENTS`. Assignments replace the
permission arrays only for named players; omitted players retain their stored
permissions. An empty array explicitly revokes that category.

Supported record permissions are `ENROLLMENT_LIST`, `OUTLOOK_GROUPS`,
`COURSE_CATALOG`, `FCIM_RECORD`; channels are `#enrollment-check`, `#faculty-check`,
`#course-registration`, `#general-mod-chat`. Only Session owns assignments.
`MODERATOR` has no record assignments; `JUNIOR_MODERATOR` receives no implicit
record permission from its role. Existing sessions default to no assignments.

Session stores assignments in its own new `session_access_assignments` table,
with a foreign key to the existing session/player pair and cascade deletion.
Existing tables/data are retained. Validation and writes run in a transaction
with a session-row lock. Membership reads use one repeatable-read snapshot.
Memory stores exist only for existing unit/fixture tests; the acceptance run uses
PostgreSQL and verifies restart and another Session process.

## Service-only membership operation

```http
POST /internal/v1/session-memberships/verify
Authorization: Bearer <caller-service-secret>
X-Trace-Id: <trace-id>
Content-Type: application/json

{"sessionId":"55555555-5555-5555-5555-555555555555","playerId":"22222222-2222-2222-2222-222222222222"}
```

```json
{"member":true,"role":"JUNIOR_MODERATOR","recordAccess":["ENROLLMENT_LIST"],"channels":["#enrollment-check"]}
```

The caller sends that request to Gateway. Only dedicated credentials for
`university-record-service` and `discord-dms-service` are accepted. Player JWTs,
Discovery tokens and caller-controlled service headers grant no access. Unknown
internal paths return 404. No generic target URL is accepted.

Gateway's `GATEWAY_SERVICE_TOKENS_JSON` maps caller names to distinct secrets.
Gateway replaces the caller credential with `SESSION_INTERNAL_TOKEN` when
forwarding to Session and adds the authenticated `X-Service-Name`. Session alone
shares that target secret with Gateway; Record and DMs never receive it. All
three secrets must be distinct and contain 32-256 visible ASCII characters.
No credential examples or generated tokens belong in Git.

Absent/bad credentials return 401. Missing Gateway/Session service-auth
configuration returns 503; malformed partial Gateway configuration fails startup.
Session requires UUIDs (`400 INVALID_REQUEST`) and returns 200 with `member=false`,
empty role/arrays for unknown sessions, non-members, unassigned players and
completed sessions. Database failures are 503, not permission denials. Membership
success depends on persisted state, not demo fixture IDs.

Gateway keeps its existing Discovery, load-balancing and circuit-breaker logic.
The service operation has a separate bounded task pool to avoid exhausting the
public pool during nested calls; its capacity uses the existing Gateway task
setting. Session membership queries have a 500 ms deadline; Gateway's whole
membership operation has a 750 ms deadline, inside the callers' one-second
deadline and existing outer task limits. Saturation returns 429. These nested
budgets prevent an abandoned caller from holding Gateway service slots for the
general five-second task timeout during recovery.

## Caller behavior

Record uses `SESSION_CLIENT=gateway`, `GATEWAY_URL` and its own
`GATEWAY_SERVICE_TOKEN`. The default `disabled` setting fails closed; the old
fixture requires explicit `mock`. DMs selects its real client with
`SESSION_CLIENT=gateway` and the same two setting names, using its own credential.
Unknown DMs client modes fail startup instead of silently selecting fixtures.

Clients use HTTP/1.1, one-second request deadlines bounded by the original
context, no ambient proxy, no redirects and no retry. Responses are limited to
16 KiB and must contain valid membership fields. Non-200 or malformed responses
fail closed: Record returns `503 SESSION_SERVICE_UNAVAILABLE`; DMs returns
`503 SESSION_SERVICE_UNAVAILABLE`. A valid negative result denies access with
Record's existing `403 RECORD_ACCESS_FORBIDDEN` or DMs' `403 PLAYER_NOT_IN_SESSION`.
Record additionally requires `ENROLLMENT_LIST`; membership alone is insufficient.
All hops preserve one safe `X-Trace-Id` and omit credentials and raw payloads from logs.

## Reproduce privately

Use the private Session/DMs owner patches and the Gateway/Record feature
worktrees. Never copy the private snapshots into this public CPR. Run:

```powershell
python scripts/verify_gateway_membership_baseline.py --gateway-source <gateway-path> --record-source <record-path> --session-source <session-path> --dms-source <dms-path>
```

The verifier first builds its local Python test/signer tool from the supplied
Gateway dependencies, then builds only local candidate images and creates a random
`pad-membership-<id>` Docker project, fresh database containers, private service
networks, fresh credentials and a loopback-only random Gateway port. It reads
no existing `.env` or database volumes. Results and correlated traces are written
under ignored `docs-local/`; generated credential files stay there. Default
cleanup removes only that run's disposable project. `--keep-running` retains it
for inspection; the results record its exact project name and loopback address.

Review and apply owner patches in their private repositories using assigned
issues, feature branches and the existing PR templates. Two approvals and
required coverage/CI remain mandatory. Release changed services through their
existing reviewed main workflow, verify image provenance, then update shared
CPR gitlinks/image pins and client settings in a separate reviewed change.
This candidate does not claim those remote releases or shared deployment steps
have occurred. Architecture diagrams are left to their owner.

## Follow-up: shared catalog and DMs settings

This operation is now part of the shared
[HTTP operation catalog](http-operation-catalog.md), which keeps its path and schema
unchanged and requests `moderation-service` as a third caller. The Discord DMs feature
branch for [DMs #33](https://github.com/m3ower/student-id-discord-dms-service/issues/33)
removes the fixture modes this harness used: DMs refuses `STORE=memory` and
`SESSION_CLIENT=mock`, needs Redis, its own `DMS_INTERNAL_TOKEN`, and
`PLAYER_JWT_PUBLIC_KEY_B64` (the same public key as the Gateway) for WebSocket handshakes.
`scripts/verify_gateway_membership_baseline.py` was updated accordingly; that updated
harness has not been executed yet because Docker was unavailable on the machine that
changed it.

