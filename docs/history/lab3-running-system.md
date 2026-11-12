# Historical reference — not current deployment instructions

Preserved from the earlier README. Current images, protocols and startup
requirements are in the CPR README and deployment/releases.json.

## Running the system

For Lab 3 Grade 5, use the [scaled startup guide](docs/service-discovery-scaled.md)
and `python scripts/scaled_stack.py up` with the updated `.env.example` settings.
The shared `docker-compose.yml` contains both replicas; the helper initializes
primary schemas before enabling the second instances. The Lab 2 release notes
below describe the earlier baseline, not the pending Lab 3 image pins.

Applicant and University Record submodules now track their merged Lab 3 fixes
on `dev`, both with source version `0.4.0`:

| Service | Source commit | Merged repair PR |
| --- | --- | --- |
| Applicant | `7b33b46a5900ecd35e791cd5e6b4f160f513fbfb` | [Applicant #21](https://github.com/Andreiisthebest/student-id-applicant-service/pull/21) |
| University Record | `aefdd93e198ee2824ca1c5c394cfe37aabf599de` | [University Record #20](https://github.com/Andreiisthebest/student-id-university-record-service/pull/20) |

Applicant adds HTTP/1.1 Discovery registration, measured `/status`, sanitized
create/update uniqueness conflicts and safe process/request logs. Record adds
measured `/status` and sanitized Fiber 404/405 handling while retaining 23505 ->
409 conflicts. Both retain the exact caller timeout x 3.5 failure window, exclude
ordinary 4xx/shutdown cancellation, and keep their in-process integration mocks
explicit. Record's `session.MockVerifier{}` is not live Session authorization.

Source verification passed 34 Applicant tests with 96.6% line coverage and the
race-enabled Record suite with 78.8% line / 78.7% statement coverage. Two source
replicas per service also passed registration, shared CRUD, 15 create and 15
update race pairs per service, restart, measured critical latency and database
failure/recovery. These results do not establish the full shared laboratory run.

The image table and Compose still select `lab3-0.3.0` for these two services.
Those images do not match the newer gitlinks; changing a submodule does not
rebuild a pulled image. Source version `0.4.0` is not a claim of Docker Hub
publication. Reviewed release, immutable tag/digest/source-revision verification
and a separate image-pin update remain required. No other owner's release is
changed by this source synchronization.

**Requirements:** Docker Engine 24+ with Compose v2, Python 3.12+, enough RAM
for 16 backend instances and their databases, and free host ports 8082, 8083,
8087, 8088, 8089, 8090 and 8091. Configure `.env` using `.env.example` and the
scaled startup guide; preserve existing credentials and update old image overrides.

```bash
git clone --recurse-submodules https://github.com/m3ower/faf-student-id-please.git
cd faf-student-id-please
cp .env.example .env      # replace every example password
docker compose pull gateway-service
docker compose up -d
docker compose ps
```

Data survives `docker compose down` because every database uses a named volume;
`docker compose down -v` wipes it.

Credentials exist only in `.env`, which is git-ignored. `.env.example` holds
placeholders so everyone knows which variables to set.

### Gateway deployment and authorization

Gateway uses the published image above. Update an existing ignored `.env`'s
`GATEWAY_IMAGE` to that tag, or remove the override to use the Compose default.
An older override takes precedence over an updated `docker-compose.yml`.

Set `GATEWAY_JWT_PUBLIC_KEY_B64` in local `.env` to the base64 encoding of the
matching issuer's PEM RSA **public** key (SubjectPublicKeyInfo, at least 2048 bits).
Gateway must never receive the private signing key. Do not commit JWTs, private
keys or local `.env` files; `.env.example` intentionally leaves this setting empty.

With an empty key setting, protected requests with a Bearer token fail closed
with `503 AUTH_NOT_CONFIGURED`; requests without a token return
`401 UNAUTHENTICATED`. A configured key verifies RS256 access JWTs with
`iss=student-id-player-service`, `aud=student-id-api`, UUID `sub`, numeric
`iat`/`exp` no more than 3600 seconds apart, and `token_use=access`.
Expired/invalid tokens return `401 UNAUTHENTICATED`. Gateway removes
`Authorization` before forwarding requests, including public requests.

Health endpoints, `OPTIONS`, and Player registration/login/refresh paths are
public. The pinned Lab 3 Player image predates real token issuance. The
[Player/Session baseline candidate](docs/player-session-http-baseline.md) implements
login/refresh and updates the owned collections to obtain real tokens; use a matching
reviewed Player/Gateway build and private key configuration. This documentation
does not silently upgrade the pinned deployment or establish full-stack readiness.

After updating local settings, adopt the release without clearing data:

```bash
docker compose pull gateway-service
docker compose up -d --no-deps gateway-service
```

Use the same project name and overrides as the existing stack. Local Gateway
health is `GET http://localhost:8090/health`. The membership/business baseline binds
Session's player identity to the verified JWT subject and adds backend target
credentials; do not supply a spoofed identity header. Direct published service ports
in the old lab deployment require a separate private-network deployment update.

### Moderation and Discord DMs: what they need

| Variable | Used by | Meaning |
| --- | --- | --- |
| `MODERATION_DB_PASSWORD` | `moderation-db`, `moderation-service` | PostgreSQL password; the same value in both |
| `DMS_REDIS_PASSWORD` | `dms-redis`, `discord-dms-service` | Redis password |
| `DOCKERHUB_USER` | both | `meow3r` |
| `MODERATION_VERSION`, `DMS_VERSION` | both | image tags, see the table above |

Health checks: `GET http://localhost:8087/q/health/ready` (Quarkus, reports the database
too) and `GET http://localhost:8088/health`. Both must report `UP` before the Postman
collections will pass.

Both services keep their data in named volumes, so a `docker compose restart` preserves
decisions and chat history; only `docker compose down -v` clears them.
**Player and Session run requirements:** set `PLAYER_DB_PASSWORD` and
`SESSION_DB_PASSWORD` to local values in the ignored `.env` file before
starting the shared Compose stack. Keep all keys from `.env.example` defined,
because Compose validates the whole shared file even when starting only two
services. The Session connection URL currently embeds its password, so use
URL-safe characters (letters, digits, `_`, `-`) for `SESSION_DB_PASSWORD`.
Run `docker compose up -d player-service session-service`
to pull the two published images and start their separate PostgreSQL 16
containers; ports `8082` (Player) and `8083` (Session) must be free.
`PLAYER_IMAGE` and `SESSION_IMAGE` select the published releases listed above.
If an existing ignored `.env` still sets these variables to older tags,
update those two values to match `.env.example`; local values take precedence.
Docker Compose supplies the database URLs, users, and named volumes, so
Java and Go are not needed on the host for this image-based run. To build or
test the current source instead, Player needs Java 21 (Maven Wrapper included),
Session needs Go 1.27, and running either outside Compose needs its PostgreSQL
database configured separately.

**Applicant and University Record run requirements:** keep all keys from
`.env.example` in the ignored `.env`, and replace `APPLICANT_DB_PASSWORD` and
`RECORD_DB_PASSWORD` with distinct local values. Use URL-safe characters for
`RECORD_DB_PASSWORD` because its value is embedded in the record service's
PostgreSQL URL. Their public REST entry point is Gateway on host port `8090`.
Use the published Gateway image and its authorization settings documented above. Run
`docker compose up -d applicant-service university-record-service gateway-service`
to start these services and their separate PostgreSQL 16 containers. Data persists in
the `applicant-pg-data` and `record-pg-data` named volumes. The image tags can
be overridden with `APPLICANT_IMAGE` and `RECORD_IMAGE`. Update these two values
in an existing ignored `.env` to match `.env.example`; older overrides take
precedence over the Compose defaults. To adopt the published images in an
already running stack, run these commands from the CPR directory:

```bash
docker compose pull applicant-service university-record-service
docker compose up -d --no-deps applicant-service university-record-service
```

Use the same Compose project name and overrides as the existing deployment.
This refreshes only these two services and preserves their database volumes.
Check
`http://localhost:8090/api/v1/health/applicant-service` and
`http://localhost:8090/api/v1/health/university-record-service`.
For this shared deployment, import the CPR's
[`Applicant collection`](postman/applicant-service.postman_collection.json),
[`University Record collection`](postman/university-record-service.postman_collection.json),
or [`combined collection`](postman/Student-ID-Please-Lab-1.postman_collection.json).
All three use `http://localhost:8090`. The older collection inside the Applicant
submodule defaults to standalone ports `8080` and `8081`; override both service
URL variables to `http://localhost:8090` if using that collection with Compose.
The current HTTP and in-process mock contract is documented in
[Applicant and University Record Lab 1 contract notes](docs/applicant-university-record-lab1.md).
Their dedicated networks and Gateway configuration are documented in
[Applicant and University Record Grade 6 integration](docs/applicant-record-lab2-grade6.md).

Run the owned collections in order. Each generates unique disposable student IDs,
checks create/update conflicts and rollback, and deletes only the records created
by that run. Record also checks enrollment lookup with local mock membership and
a missing-membership 403. `accessToken` stays empty in tracked collections; supply
a valid Gateway test token in a private environment. `sessionId`/`playerId` are
mock header inputs, not proof of live Session authorization. The combined
collection contains only these same two owned folders. These public collections
do not call internal `/status`, inject database failures or prove concurrent races,
image provenance, real membership authorization or full Grade 10 acceptance.

For Lab 4 Task 3, the two dedicated Applicant and University Record collections
also start with a **Gateway boundary** folder: the owned service's public health
relay, a missing-token `401`, and a malformed Bearer-header `401`, including the
Gateway error code and trace ID. Those checks override inherited authorization;
the existing business requests still inherit `Bearer {{accessToken}}`. Keep
`baseUrl` at Gateway (`http://localhost:8090`). The combined collection and other
owners' collections are unchanged; no request targets the repository-only broker.

Collection verification against local `0.4.0` builds of the exact owned gitlinks
passed 68 requests and 120 assertions across the two dedicated collections and
their combined run. This validates the business contracts directly against those
builds; Gateway authentication and the older pinned images were not part of that run.
