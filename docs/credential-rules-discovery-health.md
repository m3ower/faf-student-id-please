# Credential, Rules and Discovery: Lab 3 health and logging contract

## Current Credential and Rules contract: lab3-0.4.0

This section updates only Marin's two services. The Discovery notes further
below describe the original Grade 3 scope, not the current Discovery release.
Gateway, Discovery and teammate implementations/pins are unchanged by this
owned-service release.

Both services add unauthenticated operational `GET /status` on their internal
service address. Discovery already probes this path; it need not change its
parser. These are not new public `/api/v1` Gateway routes. Existing `/health`
and `/health/ready` responses and all business payloads/status codes are unchanged.

```json
{
  "service": "credential-service",
  "status": "UP",
  "version": "lab3-0.4.0",
  "uptimeSeconds": 12.5,
  "startedAt": "2026-10-29T00:00:00Z",
  "traceId": "104bdb40-6a6d-49c6-adc0-76ac994fd588",
  "checks": [{"name": "database", "status": "UP", "latencyMs": 1.2}],
  "limits": {"maxConcurrentTasks": 32, "taskTimeoutSeconds": 5}
}
```

Rules uses `service="rules-service"`; both report actual configured limits,
elapsed uptime, release version and the same UUID as their `X-Trace-Id` header.
The database check measures elapsed connection acquisition/validation or ping,
not an invented constant and not CPU utilization. Discovery uses that reported
dependency latency for its configured critical-pressure threshold. The existing
bounded probes and capacity exemption apply. Responses are `Cache-Control:
no-store`, with 200/UP on success and 503/DOWN on database failure. Neither the
body nor application logs expose database errors, passwords or authentication.

Rules' `/api/v1/rules/current` and `/api/v1/rules/evaluate` now obtain rules and
their version in a single read-only repeatable-read PostgreSQL transaction.
Concurrent committed updates on another replica cannot produce a mixed-version
response; the next request sees the new consistent snapshot. No new database
schema, cross-service database access, event integration or affinity is added.

Implementation PRs: [Credential #20](https://github.com/CmMarin/student-id-credential-service/pull/20)
and [Rules #20](https://github.com/CmMarin/student-id-rules-service/pull/20).
Credential packages VERSION inside its jar; Rules includes VERSION in its image.
CPR adopts only verified published `cmmarin/student-id-credential-service:lab3-0.4.0`
and `cmmarin/student-id-rules-service:lab3-0.4.0`, with matching released gitlinks.
The owned Postman collections retain Gateway port 8090 and their existing APIs.
This is not proof of a complete team-stack run or a Grade 10 eviction change.

Owner-approved workflow exception for these two private repositories only:
zero mandatory approvals, but PRs and successful required CI remain enforced.
Feature PRs to `dev` use squash; releases from `dev` to `main` use merge commits
and pass the release-source guard, tests and image build. Force pushes/deletions
remain blocked. Shared repositories retain their existing review requirements.

## Original Grade 3 scope

This additive contract covers the Grade 3 source changes in Credential, Rules,
and the shared Service Discovery repository. Other services remain their owners'
responsibility. Source implementation and tests do not change the images
currently pinned by CPR; adopt new images and source revisions after the normal
review/release process.

## Endpoints

All three services implement unauthenticated operational GET endpoints:

| Endpoint | Meaning | Success | Failure |
| --- | --- | --- | --- |
| `/health` | HTTP process liveness; no database query | 200 UP | An unreachable process cannot answer |
| `/health/ready` | Service readiness | 200 UP | Credential/Rules return 503 DOWN when PostgreSQL is unavailable |

Each health body has `status`, `service`, and `checks`. Service names are
`credential-service`, `rules-service`, and `service-discovery`.

```json
{"status":"UP","service":"credential-service","checks":{}}
```

Credential and Rules readiness includes `checks.database`, using UP or DOWN
consistently with the overall status:

```json
{"status":"DOWN","service":"rules-service","checks":{"database":"DOWN"}}
```

Discovery currently has no registry or external dependency. Its two probes
therefore return 200 UP with empty checks; they do not demonstrate registration
or lookup functionality. Those endpoints are later-grade work.

Credential and Rules health handlers bypass their business concurrency limit.
Rules' database probe uses a one-second context deadline. Credential defaults
to a one-second pool-acquisition wait plus a one-second JDBC validation bound;
`DB_CONNECTION_TIMEOUT_MS` tunes the pool wait. Liveness remains UP after a
database failure; readiness returns DOWN rather than hiding dependency failure.

## Transport scope

These are service operational paths, not new public `/api/v1` routes. Call them
on the service's configured address (Credential defaults to 8080, Rules to 8081;
Discovery's documented local command uses loopback 8089).

The existing Gateway `/api/v1/health/credential-service` and
`/api/v1/health/rules-service` mappings still use CRUD probes. This change does
not edit Gateway or pretend those aliases use the new endpoints. The Gateway
owner can adopt the new readiness paths in a separate reviewed change.
Discovery is not added to Compose or Gateway by this Grade 3 implementation.

## Traces, errors and logs

- Each request returns `X-Trace-Id`. A single canonical UUID supplied by the
  caller is preserved; missing, invalid or duplicate values are replaced.
- Standard error envelopes reuse that ID. It is a correlation identifier, not
  an authentication credential or a distributed tracing backend.
- Application operational events record service, event, method, matched route
  template, final status, duration and trace ID, with error codes for failures.
- Credential waits for async completion before logging the final response.
- Go Rules and Python Discovery write JSON operational logs. Credential writes
  SLF4J events with explicit key/value fields.
- Lifecycle and readiness transitions are explicit. Request bodies, queries,
  Authorization, cookies, passwords and raw database/exception text are excluded
  from these application events. Run Discovery with `--no-access-log` to avoid
  Uvicorn's separate raw-URL access log.

Credential database operation failures now return generic
`503 DATABASE_UNAVAILABLE`. Existing Credential/Rules task limits retain
`503 CONCURRENT_TASK_LIMIT_REACHED` with `Retry-After: 1`, and deadlines retain
`504 TASK_TIMEOUT`. Rules preserves framework HTTP errors such as 404 rather
than converting them to generic 500s. Discovery uses standard 404, 405 and 500
error envelopes without private exception text. Successful CRUD payloads are
unchanged.

## Verification and adoption

Service PRs:
- [Credential #9](https://github.com/CmMarin/student-id-credential-service/pull/9)
- [Rules #9](https://github.com/CmMarin/student-id-rules-service/pull/9)
- [Discovery #4](https://github.com/CmMarin/student-id-service-discovery/pull/4)

Private suites exercise health responses, unavailable databases, capacity
bypass, trace propagation and secret redaction, with at least 70% coverage
required in CI. Rules also tests HTTP/database CRUD against a disposable
PostgreSQL instance. Live source-process checks confirmed all three UP responses
and Credential/Rules DOWN readiness after stopping the disposable database.

The original Grade 3 changes were subsequently released. Current Credential
and Rules adoption is described above; the older Lab 2 images lack these health
endpoints. Professor access and teammates' work remain separately tracked.
