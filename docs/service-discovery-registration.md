# Service Discovery startup registration

Additive PAD Lab 3 Grade 4 contract for Discovery and the initial Credential and
Rules callers. Teammates adopt this contract in their own repositories. It does
not change public business APIs, Gateway routes, shared Compose, image pins or
CPR gitlinks. Discovery runs in Python, the team's banned language.

## Internal API

All registry endpoints require `Authorization: Bearer <DISCOVERY_REGISTRATION_TOKEN>`.
Use one generated URL-safe machine secret (32-256 ASCII letters, digits, `_` or
`-`) supplied through ignored local configuration or deployment secrets, never
committed. This is not a Player JWT. These control-plane endpoints are private
and direct, not public REST client/business routes through Gateway. Do not add
them to Gateway's public route map. Use TLS outside a trusted private network.

### Register an instance

`POST /internal/v1/instances`:

```json
{
  "serviceName": "credential-service",
  "instanceId": "104bdb40-6a6d-49c6-adc0-76ac994fd588",
  "baseUrl": "http://credential-service:8080",
  "readinessPath": "/health/ready"
}
```

- `serviceName`: lowercase name, regex `^[a-z][a-z0-9-]{0,62}$`.
- `instanceId`: UUID generated once per process; retries reuse it. Each replica
  needs a different ID. `SERVICE_INSTANCE_ID` optionally supplies a UUID.
- `baseUrl`: reachable HTTP(S) origin, maximum 256 characters, no user info,
  non-root path, query or fragment. Trailing `/` is normalized away. Docker
  callers advertise a reachable container/network address, not `0.0.0.0` or
  `localhost` pointing to the wrong container.
- `readinessPath`: `/health/ready` (also the default when omitted).
- No extra fields. Maximum request body is 4096 bytes.

The response repeats the normalized registration and adds `registeredAt`
(ISO-8601 UTC). New `(serviceName, instanceId)` keys return `201`; the same key
returns `200` and updates its address/time. Success is registration, **not proof
of health**. Registry writes log service name and instance UUID, not the token.

### Inspect registrations

`GET /internal/v1/instances` returns `{"instances":[...]}`, sorted by service
name and UUID. Optional `?serviceName=rules-service` filters the list. It is an
internal control-plane endpoint. The scaled Gateway uses its service-name filter;
see [scaled integration](service-discovery-scaled.md).

### Remove an instance (additive Grade 5 change)

`DELETE /internal/v1/instances/{serviceName}/{instanceId}` requires the same
machine credential and identifier validation as registration. It removes exactly
that key and returns an empty `204`, including when already absent. Invalid
identifiers return `422 INVALID_REGISTRATION`; authorization/configuration errors
keep the existing 401/503 envelopes. It does not stop a container or remove other
instances. Logs include the service name, UUID and removed flag, never credentials.

The scaled deployment helper calls DELETE before stopping a selected replica,
then repeats it after stop to clean up a possible startup-registration race.
New Gateway lookups observe the removal. Existing requests/streams are not
migrated; a caller must reconnect if their selected instance stops. This is
controlled removal, not automatic crash eviction or health-based removal.

### Error responses

| HTTP | Code | Meaning |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | Missing, duplicate or invalid Authorization |
| 413 | `REGISTRATION_TOO_LARGE` | Request exceeds 4096 bytes |
| 422 | `INVALID_REGISTRATION` | Invalid JSON, missing/extra field or invalid value |
| 503 | `REGISTRY_NOT_CONFIGURED` | Discovery has no valid machine secret |
| 503 | `REGISTRY_CAPACITY_REACHED` | 1024 entries reached; existing-key updates still work |

Errors use `{"error":{"code":"...","message":"...","service":"service-discovery",
"traceId":"<uuid>","details":{}}}`. `X-Trace-Id` matches the error body. Raw
validation input, tokens and exceptions are not echoed or logged. Invalid server
secret disables registry operations, not the process-health probes.

## Startup clients and configuration

| Variable | Meaning |
| --- | --- |
| `DISCOVERY_URL` | Discovery origin; empty disables registration for backwards compatibility |
| `DISCOVERY_REGISTRATION_TOKEN` | Matching internal machine secret |
| `SERVICE_ADVERTISE_URL` | This instance's reachable HTTP origin |
| `SERVICE_INSTANCE_ID` | Optional UUID; otherwise generated once per process |

Credential registers asynchronously on Spring's application-ready event. Rules
registers asynchronously from Fiber's listener-started hook. Both validate
enabled configuration before serving, use two-second request timeouts, and make
at most three attempts with 1s and 2s backoffs for network failures/5xx. They do
not follow redirects or retry 4xx. A failed registration is explicitly logged
without taking down CRUD or changing health. Shutdown cancels pending work.
Environment examples are placeholders; native services do not automatically
load `.env`, and Compose must explicitly inject variables.

## Storage, release and next steps

Discovery uses one in-memory registry, one worker/replica, maximum 1024 entries.
Its restart clears state. Startup clients must restart to register again after
state loss. Entries do not expire. Controlled DELETE and fresh Gateway lookups
are described above; health polling, automatic crash eviction, periodic
re-registration, persistence and round-robin remain later work. A raw container
stop without DELETE leaves a stale entry. These limitations must not be confused
with the requirements for later grades.

Discovery's Docker image runs as non-root UID 10001 on port 8089 and includes a
readiness healthcheck. Intended public image:
`cmmarin/student-id-service-discovery:lab3-0.2.0`.
The main-release workflow requires passing tests/repository checks and a
`DOCKERHUB_TOKEN` Actions secret. Feature changes go to `dev`, then a reviewed
release PR from `dev` to `main` publishes the versioned image and `latest`.
Do not claim publication from a local build alone; verify the Docker Hub tag.
Adopt new published images and pushed gitlinks separately after reviewed merges.

The [scaled deployment](service-discovery-scaled.md) updates the shared
`docker-compose.yml` to wire two instances per backend. Its new source changes
need reviewed releases before final image pins. This contract
does not change teammates' implementations or claim their startup registration
is finished.
