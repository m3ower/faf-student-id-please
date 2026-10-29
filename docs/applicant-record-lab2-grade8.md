# Applicant and University Record: Lab 2 Grade 8

This continues Andrei's existing services with task deadlines and concurrent
task limits. It covers Applicant CRUD and University Record CRUD/enrollment
lookup. Gateway and all other owners' service settings and code are unchanged
by this work. Their Grade 8 implementation remains with their owners.

## Configuration

Each service has one admission limit shared across all its business endpoints.
Excess tasks are rejected immediately; they are not queued. Health endpoints
remain available outside this limit.

| CPR variable | Service variable | Default |
| --- | --- | --- |
| `APPLICANT_TASK_TIMEOUT_MS` | Applicant `TASK_TIMEOUT_MS` | `2000` ms |
| `APPLICANT_MAX_CONCURRENT_TASKS` | Applicant `MAX_CONCURRENT_TASKS` | `16` |
| `RECORD_TASK_TIMEOUT_MS` | Record `TASK_TIMEOUT_MS` | `2000` ms |
| `RECORD_MAX_CONCURRENT_TASKS` | Record `MAX_CONCURRENT_TASKS` | `16` |

Configure the CPR variables in the ignored `.env`. Standalone service runs use
the service variables. Timeout values must be positive integers no greater
than `2147483647`; limits must be positive integers. Invalid settings fail at
startup. Keep service deadlines below Gateway's upstream timeout so the client
can receive the owning service's error.

## Error contract

| HTTP | Code | Meaning |
| --- | --- | --- |
| `429` | `CONCURRENT_TASK_LIMIT` | All task slots are occupied; response includes `Retry-After: 1`. |
| `504` | `TASK_TIMEOUT` | The task exceeded its configured deadline. |

Both use the existing `{error:{code,message,service,details}}` envelope and
identify the service that rejected or timed out the task. Existing CRUD paths,
payloads and other error statuses retain their behavior. Grade 6 REST routing
and database isolation remain in place.

Applicant returns a completion stage while executing ORM work in an isolated
worker transaction. A deadline ends the HTTP task and requests interruption;
a PostgreSQL statement timeout also bounds blocked SQL. The concurrency slot
is retained until the worker actually stops, including after caller cancellation.

University Record creates a Go context deadline and passes it to every GORM
operation. Handlers execute in the Fiber request goroutine, and database
operations honour context cancellation. Future blocking integrations must also
honour this context. A slot is released when its handler returns.

A timeout cannot guarantee that a write never committed just before the
deadline. Verify the resource state before retrying a timed-out mutation.

## Local images and verification

The Grade 8 source versions use these Lab 2 image tags:

```bash
docker build -t andreiisthebest/student-id-applicant-service:lab2-0.2.0 services/applicant-service
docker build -t andreiisthebest/student-id-university-record-service:lab2-0.2.0 services/university-record-service
```

These tags must be built locally until their publication is approved. Set
`APPLICANT_IMAGE` and `RECORD_IMAGE` to these tags in the ignored `.env` before
starting the owned services. Gateway uses its existing deployment configuration.
Use `docker compose up -d --no-deps applicant-service university-record-service`
when their databases are already healthy.

The private service READMEs describe their suites and isolated test databases.
Applicant's `mvn verify` includes a 70% line-coverage check. Record's
`go test -race -coverprofile=coverage.out ./...` measures coverage and checks
for races; provide its isolated `TEST_DB_URL` to include database tests.

The existing owned Postman runner verifies CRUD through Gateway. Live task-limit
verification uses temporary locks in the owned databases, checks `429` and `504`
through the unchanged Gateway, then verifies recovery and query cancellation.

For the live probe, use a focused test deployment with `1..4` concurrent slots
and a `100..3000` ms deadline in each owned service, such as `2` slots and
`1000` ms. The probe creates unique test requests and locks only the owned
tables temporarily. Restore the normal settings afterward.

```bash
python scripts/verify_owned_grade8.py --project <compose-project> --base-url http://127.0.0.1:8090
python scripts/run_owned_postman.py --project <compose-project>
```

Task-limit results are written to ignored `docs-local/owned-grade8-verification.json`.
