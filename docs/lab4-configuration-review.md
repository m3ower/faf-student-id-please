# Lab 4 Compose and Postman review

Reviewed against `PAD_LAB_4_V1.pdf` on 2026-11-12. The PDF's tasks are assessment
criteria, not authorization to publish images, change accounts, merge PRs or
deploy. This change updates local shared configuration, collections and checks.

## Sources and changes

Shared source was fetched from GitHub: CPR `origin/dev` at `bdf7190`, integrated onto current `origin/dev` `69b505a` before PR submission.
Applicant source `43b2a97`, Record source `3a2df99`, current Gateway dev and
Discovery dev were readable. Broker dev was inspected at `0ef19d2`, version
`0.6.3`. GitHub returned repository-not-found for the six other private service
repositories; their review uses the latest public shared contracts/exports.

The base Compose file alone is not a complete Lab 4 deployment. The refreshed Lab 4
overlay now configures Gateway subscriber-queue delivery, all eight services'
Broker clients, Player signing, receiver credentials, Broker health dependencies
and primary/replica registration. Player, Session and Moderation no longer publish
backend ports in the overlay. DMs ports remain for the negotiated browser socket;
Broker and consumer gRPC ports stay private. `!reset` requires modern Docker
Compose (validated with v2.40.0).

The shared example now pins ten published service/Gateway/Discovery images by
tag and immutable digest, verified using Registry manifest/config metadata and
source revision labels. The evidence is recorded in
[`deployment/releases.json`](../deployment/releases.json). Never reuse the base's
old Lab 3 images for the Lab 4 roles. Broker remains explicitly unset because no
compatible newer release was published at review time. Private `.env` was not
read or overwritten. New private
`.env.lab4` is Git-ignored.

All eight Postman exports incorporate current shared source, including its newly archived legacy adapters. Corrections add
missing Gateway/log checks, remove historical applicant fixture IDs, fix DMs
polling scripts, require real ShiftStarted replay evidence, and declare transient
variables. Applicant/Record obsolete internal adapters remain archived as in the new upstream dev update. The combined
collection is generated from all eight with isolated variable names and an extra
whole-system log download. See [Postman instructions](../postman/README.md).
The initialized Applicant repository's old two-service collection is refreshed
as well; its source working tree now contains that Postman-only change.

The exact published Gateway revision `dd994ed` was fetched and its allowlist
checked against collection requests. Unsupported method/path checks now expect
Gateway `404 ROUTE_NOT_FOUND`, rather than a backend 405 or backend-owned error.
Credential's missing-token checks target an allowed GET path, ensuring they test
authentication rather than route rejection. The published Gateway omits
`POST /api/v1/players/logout`: the Player collection now explicitly asserts that
known 404 gap and does **not** claim refresh-family logout succeeded. Restoring
the positive logout check requires a Gateway implementation/release change.

The existing canonical HTTP/messaging/protobuf files, validators, host log exporter
and tests are retained from the current dev branch. The review introduces no
REST, event or protobuf contract changes.

## Start with private configuration

Copy the base example and add the entries from `.env.owned-broker.example` to a
private `.env.lab4`. Replace placeholders, select compatible published images,
generate distinct caller/receiver/management/Discovery credentials, and configure
matching Player RSA signing and Gateway verification keys. The Broker caller map
must contain `gateway-service` and all eight service identities with the same
values as their corresponding `*_BROKER_SERVICE_TOKEN` entries. Do not commit
private keys, JWTs or populated environments.

Validate and start using the same files and explicit project name:

```powershell
docker compose --project-name pad-lab4 --env-file .env.lab4 -f docker-compose.yml -f docker-compose.owned-broker.yml config --quiet
# Initialize primary schemas before adding the replicas profile.
docker compose --project-name pad-lab4 --env-file .env.lab4 -f docker-compose.yml -f docker-compose.owned-broker.yml up -d
# Wait for all eight primaries to register healthy and finish schema initialization
# before executing the next command; `up -d` alone does not establish readiness.
docker compose --project-name pad-lab4 --env-file .env.lab4 -f docker-compose.yml -f docker-compose.owned-broker.yml --profile replicas up -d
```

Deployment was not run during review. Before starting, resolve the transport-image
mismatch below. Keep private configuration local; `config` without `--quiet`
prints resolved credentials.

Start the host operational endpoint with the exact same project and files:

```powershell
$env:LOG_DOWNLOAD_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python scripts/log_download.py --project-name pad-lab4 --env-file .env.lab4 --compose-file docker-compose.yml --compose-file docker-compose.owned-broker.yml
```

Supply that generated token privately as Postman's `logDownloadToken`. The
exporter binds to localhost:8092; `GET /internal/v1/logs` without a `service`
filter downloads a bounded snapshot of the whole selected system.

## PDF assessment

| Grade | Configuration/source evidence | Remaining requirement |
| --- | --- | --- |
| 2 | Python Broker repository, Dockerfile and workflow exist. | Live GitHub repository protections were not audited. |
| 3 | All eight collections and shared collection refreshed; README and current architecture diagram updated. | Live collection execution and inaccessible private-source comparisons remain unverified. |
| 4 | Host log-download endpoint and system-wide Postman request included; 25 endpoint tests pass. | Run with the actual project to verify real container log downloads. |
| 5 | Broker routing, round robin and circuit breaking exist in inspected source; Compose clients now point at Broker. | Verify compatible published images and actual cross-owner calls. |
| 6 | Shared catalog contains 39 operations, 5 event topics and 8 subscriber queues; Gateway uses Broker. | Verify actual subscriptions, producers and multi-group processing in a running stack. |
| 7 | Broker source implements thread-per-request and authenticated topic listing; existing collections include topic checks. | Verify runtime behavior under concurrent requests. |
| 8 | Shared proto and overlay configure gRPC clients for all eight groups; internal Gateway routes are absent in current Gateway source. | Resolve Broker transport mismatch, verify receiver health and current real-peer calls; private service source access is incomplete. |
| 9 | Inspected Broker explicitly documents volatile queues/results. | Durable Broker queues, dead-letter storage and a dead-letter listing endpoint are not implemented in inspected source. A Compose volume cannot add these semantics. |
| 10 | Replicas and connection-establishment failover are configured. | Required rerouting after circuit trip, routing by service load and Grafana/Prometheus or ELK monitoring are not established by this configuration. No monitoring stack is present. |

### Blocking transport mismatch

`contracts/proto/transports.json` selects `grpc` for all eight groups. The inspected
Broker dev source's bundled `contracts/transports.json` still selects `http` for
Credential and Rules. The proto hash matches; the delivery selections do not.
The Registry currently publishes `lab4-0.6.0` at source `6e5c232`, rather than
`lab4-0.6.3`. The old suggested `lab4-0.6.3` image does not exist in the returned
release tags and is not selected. The exact published Broker source was also
fetched: its bundled delivery choices are `http` for **all eight** groups.
Select
and verify a published Broker bundling the reviewed shared choices, alongside
healthy gRPC-capable receivers, before deploying this full-gRPC overlay. This
review does not rewrite another repository's Broker implementation or silently
restore HTTP delivery.

The PDF is **not fully satisfied** by the available implementation. Grades 9/10
need backend work and runtime evidence beyond updating Compose and collections.

## Validation

Docker Compose renders the merged configuration offline for both primary and
replica profiles (18 and 26 services). Checks verify private backend/gRPC ports,
Broker targets/dependencies and distinct primary/replica advertise URLs.
HTTP, messaging and protobuf validators pass. The shared collection is checked
against its generator; exports are validated against Postman's official v2.1
schema and JavaScript syntax. Log-download and contract unit suites pass; proto
compilation is skipped because `grpcio-tools` is not installed.

The shared collection contains 220 requests; all nine shared exports pass the
official Postman schema and 469 scripts compile. A script execution check also
verifies variable isolation, unchanged business payloads, environment overrides
and bounded DMs polling. The log/contract suites ran 52 tests successfully,
including one skipped proto compilation check.

Docker Desktop's Linux engine is stopped, so no live Newman, image pull,
database, gRPC or full-game acceptance result is claimed. No image publication,
deployment or Git push was performed.
