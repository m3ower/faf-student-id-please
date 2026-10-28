# Scaled deployment and instance routing

PAD Lab 3 Grade 5 updates the shared `docker-compose.yml` with two explicitly
named replicas of each of the eight backends, one Gateway and one Discovery.
It references images, never Dockerfiles. The original service name remains the
first instance; its second instance has a `-2` suffix. Existing database volume
keys, network boundaries, database settings and primary host ports are retained.

## Release prerequisites

New source changes must be reviewed through feature → dev → main and published
before filling their image variables. A source branch, a local image or a README
is not publication evidence. `.env.example` intentionally leaves these
unset instead of selecting incompatible older releases:

| Image variable | Needed behavior / source version |
| --- | --- |
| `DISCOVERY_IMAGE` | Authenticated idempotent DELETE; candidate `lab3-0.3.0` |
| `GATEWAY_IMAGE` | Authenticated fresh registry lookup and DMs origin mapping; candidate `lab3-0.4.0-build.<run>` |
| `SESSION_IMAGE` | PostgreSQL cross-instance SSE; candidate `lab3-0.5.0-build.<run>` |
| `MODERATION_VERSION` | Owner's reviewed registration-enabled release; reported `lab3-0.3.1` still needs main-release confirmation |
| `DMS_VERSION` | Owner's reviewed registration-enabled Redis release; reported `lab3-0.3.0` still needs main-release confirmation |

Other defaults come from the owners' published-image reports: Player
`vasiok11/student-id-player-service:lab3-0.4.0-build.10`, Credential and Rules
`cmmarin/student-id-{credential,rules}-service:lab3-0.2.0`, Applicant and Record
`andreiisthebest/student-id-{applicant,university-record}-service:lab3-0.3.0`.
These reports establish release prerequisites, not a successful two-replica run.
After publication, pin actual tags and pushed submodule revisions in a separate
reviewed CPR change. Do not point CPR gitlinks at unpushed candidate commits.

## Local configuration

Install Docker Compose v2 and Python 3.12 or later. Reserve enough Docker RAM for
16 backends, six PostgreSQL processes, Redis, Gateway and Discovery; starting
everything on a memory-constrained laptop can fail even when unit tests pass.

For a fresh setup, copy `.env.example` to ignored `.env`. For an existing setup,
add the new settings to its `.env` and update old image overrides; do not replace
working credentials or keys with placeholders. Fill the three required image
variables and two version variables with reviewed published releases. Moderation
and DMs keep their existing `DOCKERHUB_USER` namespace setting. Generate one local 32–256 character
URL-safe machine secret for `DISCOVERY_REGISTRATION_TOKEN`, and replace the
database/Redis placeholders. Session and Record currently embed passwords in
connection URIs: use URL-safe passwords for this deployment. These credentials
initialize new volumes only; changing an env value does not change a password
already stored in PostgreSQL/Redis data.

Set `GATEWAY_JWT_PUBLIC_KEY_B64` to the public key matching locally issued RS256
test access tokens, using Gateway's existing token contract. Do not commit a
private key or token. The registry token is a separate machine credential.
Protected Gateway requests still require bearer access tokens; discovery does
not implement Player login or change authorization. The scripts never print
resolved Compose environments or authentication values. Avoid sharing raw
`docker compose config` output because it includes resolved secrets.

Use the same optional `WS_TICKET_SECRET` for both DMs replicas when enabling
tickets. `SESSION_CLIENT=mock` preserves the owner's current membership fixture;
this is not live Session-to-DMs membership integration. `WS_ALLOWED_ORIGINS=*`
is for local testing only. Set explicit allowed browser origins outside the lab.

## Startup, add and remove

From CPR with the ignored environment file configured:

```powershell
py -3.12 scripts/scaled_stack.py up
py -3.12 scripts/scaled_stack.py status
py -3.12 scripts/scaled_stack.py remove session-service-2
py -3.12 scripts/scaled_stack.py add session-service-2
```

Optional `--env-file` and `--project-name` arguments select a different isolated
deployment. By default the helper uses `.env` and Compose's usual project name,
so existing volume names are preserved when the same project name is used. Use
an explicit new project name for isolated tests. `up` starts the infrastructure and the first replica of each backend,
waits for all eight registrations and `/health/ready` responses, then starts the
second replicas. This avoids racing cold-start Hibernate/Flyway/SQL initialization
within each service. The readiness helper runs inside Discovery's container so
Docker-advertised addresses are reachable. This one-time deployment wait is not
the later periodic health-monitoring task.

The second instances are in the `replicas` profile. Use the helper for initial
two-phase startup; plain `docker compose up -d` starts only the primary instances
and infrastructure. The helper enables the profile after primary readiness.
Discovery and Gateway attach to both existing internal Applicant/Record networks
so registration, readiness probes and forwarding can reach those replicas.

Each replica has its own advertised Compose origin and generates its own process
UUID; do not reuse `SERVICE_INSTANCE_ID` across replicas. Replicas share only
their service's database. Both DMs replicas share Redis with AOF enabled for
message history/PubSub. Database pools, task limits and stream limits are per
process; two replicas increase aggregate resource use.

Only declared backend replicas can be added/removed by the helper. `remove`
authenticates DELETE of the selected registration, stops that replica, then
repeats deletion for a possible startup race. It never deletes volumes or stops
Discovery/databases/Gateway. There is no request drain or automatic retry of
business writes: in-flight requests/streams can fail during stop, so reconnect
and re-read state before retrying ambiguous mutations. A raw container stop or
crash bypasses cleanup and leaves a stale entry. Registry restart loses its
in-memory state; restart the backends to register again.

`up` is for initial startup, not a rolling-upgrade coordinator. Before replacing
an already registered backend image, remove that replica with the helper, change
its local image setting, and add it again. Recreating a process directly leaves
its previous UUID entry behind; remove stale entries explicitly before use.

## Gateway and stream behavior

Gateway queries Discovery on every routed operation with the machine credential,
bounded to two seconds per registry request. Protected routes validate the
Player token before lookup. Gateway forwards neither machine credentials nor
incoming Authorization to a backend. It selects the lowest instance UUID for
this grade, without a cache or static fallback while Discovery is enabled.
Round-robin is the next grade. Missing instances return `503 NO_SERVICE_INSTANCES`;
registry errors return `503 DISCOVERY_UNAVAILABLE`. Health relays use the
selected registration's `/health/ready`.

Session SSE remains on the chosen replica for the connection lifetime. Mutations
on another replica arrive through PostgreSQL transactional LISTEN/NOTIFY. A
private database revision prevents stale or duplicate notifications after the
initial snapshot; it does not change public payloads. Listener loss closes SSE
streams and makes Session unready until reconnected. Reconnect gives a fresh
snapshot, not durable replay. Every process needs one extra database connection
for LISTEN. Grade 9 in-process applicant/progression fixtures remain local mocks.

DMs negotiation maps the selected exact internal origin to a browser-reachable
socket origin. The scaled file uses:

| Internal origin | Local public socket origin |
| --- | --- |
| `http://discord-dms-service:8080` | `ws://localhost:8088` |
| `http://discord-dms-service-2:8080` | `ws://localhost:8091` |

Gateway accepts this JSON map via `DMS_PUBLIC_WS_ORIGINS`. Compose builds it from the existing
`DMS_PUBLIC_WS_ORIGIN` and the new `DMS_SECOND_PUBLIC_WS_ORIGIN` settings.
An unmapped instance returns `503 WS_ORIGIN_NOT_CONFIGURED`, not an internal Docker URL. The socket
connects directly to the selected DMs replica; existing sockets are not moved by
registry updates. Shared Redis provides cross-instance fan-out; reconnect can
negotiate a different instance. Discovery uses host port 8089, Gateway 8090, so
the second DMs port deliberately avoids 8089. Existing primary host bindings are
retained. Replace public origins with reachable `wss://` addresses and restrict
published ports appropriately for remote deployments.

## Verification boundaries

Run controller tests with `python -m unittest discover -s tests`. Gateway,
Discovery and Session own their implementation/coverage tests in their private
repositories. The Session integration suite needs a disposable PostgreSQL via
`SESSION_TEST_DB_URL`; never point it at an existing deployment database.

A final live check must establish 16 distinct registered UUIDs/origins and ready
replicas, exercise REST through authenticated Gateway, observe a Session mutation
on the other replica's SSE stream, exercise DMs Redis fan-out/direct negotiation,
and remove/add a selected replica while observing fresh Gateway routing. Until
that run passes with reviewed published images, source/tests alone do not mean
the whole team's scaled deployment is complete.

No heartbeat, expiry, automatic crash recovery/eviction, round-robin, circuit
breaker, ongoing health polling or developer alerts are implemented here. The
owners' mock-state limitations and Applicant duplicate-write/Moderation score
idempotency concerns remain owner follow-ups; scaling does not fix them.

### Local candidate verification, 2026-10-28

- Gateway: 199 tests, 99.36% application coverage on Linux/Python 3.12.
- Discovery: 27 tests, 100% application coverage on Linux/Python 3.12; repository
  setup checks passed.
- Session: full PostgreSQL-backed suite and `go vet` passed with race detection,
  84.4% statement coverage. Includes cross-instance updates/deletion, notification
  rollback, revision filtering, concurrent membership snapshots and listener recovery.
- CPR controller: five tests passed. Resolved Compose has 16 backend definitions,
  16 distinct advertised origins, no shared explicit UUID, and image references only.
- Isolated real Gateway/Discovery/two-Session containers: RS256 authorization,
  registration/readiness, cross-instance SSE through Gateway after six seconds,
  idempotent removal/restart and registry-failure responses passed.
- Actual scaled Compose subset with two DMs containers using the owner's reported
  `lab3-0.3.0` branch image: direct sockets received a message across shared Redis,
  history was shared, and helper removal/addition changed Gateway's negotiated port.
  This uses current mock membership/ticket-disabled configuration; it does not
  establish production DMs authentication or reviewed main-release provenance.

Temporary test projects/containers and their new volumes were removed. Existing
deployments and data were not used. The complete 16-backend stack was not started
on this memory-constrained host, and new candidate images were not published.
Final reviewed image pins and the all-services concurrent run remain required.
The live subset checks above used the earlier separate-file layout. After
consolidation into the existing Compose file, configuration and controller checks
are rerun; the updated full deployment still requires its final live check.
