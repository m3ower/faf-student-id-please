# Historical reference — not current deployment instructions

Preserved from the earlier README. Current images, protocols and startup
requirements are in the CPR README and deployment/releases.json.

## Lab 1 deployment

The shared [`docker-compose.yml`](docker-compose.yml) also deploys the Credential
and Server Rules services owned by Clima Marin. They share one PostgreSQL
container while using separate databases, users, and the `postgres-data` Docker
volume; the Moderation and Discord DMs services retain their own database and
Redis volumes.

Published versioned Docker Hub images for these two services:

- [Credential Service — `cmmarin/student-id-credential-service:lab3-0.4.2`](https://hub.docker.com/r/cmmarin/student-id-credential-service)
- [Server Rules Service — `cmmarin/student-id-rules-service:lab3-0.4.1`](https://hub.docker.com/r/cmmarin/student-id-rules-service)

To run only these two services through the Gateway, you need Docker Engine with
Compose v2 and free host port 8090. Copy `.env.example` to the
git-ignored `.env` and replace at least `POSTGRES_PASSWORD`,
`CREDENTIAL_DB_PASSWORD`, and `RULES_DB_PASSWORD` with your own values. Complete
the other required settings from the current `.env.example`, including the
Discovery machine token and reviewed shared image selections; the earlier
Lab 1 three-password setup alone is no longer sufficient. Protected Gateway
requests also require its matching public key and a valid client access token.
Follow the [shared startup guide](docs/service-discovery-scaled.md) for the
team-wide configuration; this owned-service update changes neither shared
authentication nor other members' image selections. Do not commit `.env` or
real credentials. To start just these services and their dependencies:

```bash
docker compose up -d gateway-service postgres credential-service rules-service
docker compose ps
```

The Compose file references these published image tags, never the services'
local Dockerfiles. Both services use separate databases and users in the shared
PostgreSQL container, with data persisted in the `postgres-data` named volume.
The private service READMEs explain how to run each service from source.

These releases retain the internal `GET /status` introduced in `lab3-0.4.0`, with measured
database `checks[].latencyMs`, enabling Discovery's dependency-pressure alerts
without changing existing health or business responses. Rules also reads rules
and their version from one repeatable-read snapshot across concurrent replica
writes. See [the owned-service health guide](docs/credential-rules-discovery-health.md)
for the additive contract and the original Grade 3 health/logging notes.
Existing local `.env` image overrides take precedence: update only
`CREDENTIAL_IMAGE` and `RULES_IMAGE` to the tags above when adopting this release.

Credential `lab3-0.4.2` also sanitizes framework error responses and suppresses
raw JDBC failing-row detail while preserving safe application error events.
Both services exclude ordinary 4xx from their registration failure budgets and
expire failures exactly one window old. Their only live outbound service call
is Discovery registration; this release does not implement shared eviction fixes.
Exact released source commits, digests and PRs are listed in the
[owned-service health guide](docs/credential-rules-discovery-health.md).

Import `postman/credential-service.postman_collection.json` and
`postman/server-rules-service.postman_collection.json`. Select a private local
environment with a valid `accessToken` accepted by the Gateway and run each
collection in order. Both default to `http://localhost:8090`; keep stored tokens
empty. CRUD requests create disposable records and delete them at the end;
negative requests assert exact error statuses and sanitized responses. These
collections do not call internal `/status`, inject database faults, or establish
that the shared Discovery/Gateway acceptance tests pass.

The PostgreSQL initialization script runs only when the volume is first
created. To recreate development databases, intentionally remove the named
volume and start Compose again.

### Credential and Server Rules mock contract

For the newer Lab 4 Broker/gRPC-capable releases and the opt-in deployment,
see [Credential and Rules Task 8 rollout](docs/owned-grpc-rollout.md).
The opt-in overlay activates both owned gRPC publishers/receivers; deploy it only
with the matching Broker transport-catalog release described there.
The Lab 1 in-process examples below are historical, not the production Lab 4
service-to-service implementation. The base Lab 3 deployment is not promoted
by the opt-in overlay.

The following describes released Lab 3 behavior and test fixture expectations,
not the unreleased production-baseline implementation. In the candidate branches
the legacy fixture code is test-only, and protected reads use the real candidate
membership boundary; see [candidate status and missing work](docs/owned-business-http-baseline.md).

The Grade 9 code in these two private services prepares the existing internal
contract without changing their Lab 1 HTTP endpoints. Credential models
`ApplicantInitialized` plus `GenerateCredentials`, `GetCredentials`, and
`ValidateCredential` in process. An identical initialization event is safe to
replay; conflicting seed or event data is rejected. Validation reports
`structurally_valid`, `authentic`, and `issues` separately. The current
`X-Session-Id` HTTP check is only a session-presence mock, not per-player
authorization.

Rules models `GetCurrentRuleset(sessionId)` and
`Evaluate(sessionId, applicantId)` with a session-scoped fact provider. The
existing HTTP evaluation endpoint still takes applicant facts in its request;
the internal mock resolves those facts by IDs. Rules returns violations and an
advisory `recommendedAction`; Moderation owns the final admission decision, so
the forged-document fixture's `ACCEPT` recommendation is not its final verdict.

For session `55555555-5555-5555-5555-555555555555`, the agreed in-process
fixtures use ruleset version 1 and fixed `enrollmentYears=2`:

| Applicant ID | Seed and deception | Credential result | Rules result |
| --- | --- | --- | --- |
| `a0000000-0000-0000-0000-000000000001` | `918273`, `NONE` | Student ID structurally valid and authentic | No violations; `ACCEPT` recommendation |
| `a0000000-0000-0000-0000-000000000002` | `918274`, `FORGED_DOCUMENT` | Student ID structurally valid, not authentic; `SIGNATURE_MISMATCH` | No violations; `ACCEPT` recommendation |
| `a0000000-0000-0000-0000-000000000003` | `918275`, `PREVIOUSLY_BANNED` | Credentials valid; the ban does not invalidate a document | `NO_BANNED` (`CRITICAL`); `BAN` recommendation |

These are in-process mock fixtures, not live gRPC or RabbitMQ integrations.
The current Credential `lab3-0.4.2` and Rules `lab3-0.4.1` images include these
in-process mocks. Run `mvn test` in Credential and `go test ./...` in Rules to
exercise their fixture contracts; that is not proof of live gRPC/event transport.
