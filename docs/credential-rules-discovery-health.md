# Credential, Rules and Discovery: Lab 3 health and logging contract

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

Merge and release the service changes before updating CPR image tags and
gitlinks. The owned `lab3-0.1.0` versions are pending releases; existing published
`lab2-0.3.0` images do not contain these new health endpoints. Professor access
and the rest of the team's Grade 3 work are tracked separately.
