# Lab 3 Grade 3: Applicant and University Record

This checkpoint implements only the owned-service part of Grade 3 in
`PAD_LAB_3.pdf`: health/status endpoints and explicit logs. Grades 2 and 4 are
already completed and are not repeated. Other owners must verify their own
private and shared services before claiming team-wide Grade 3 completion.

## Tracking and source scope

- [CPR issue #72](https://github.com/m3ower/faf-student-id-please/issues/72)
- [Applicant issue #13](https://github.com/Andreiisthebest/student-id-applicant-service/issues/13)
- [University Record issue #12](https://github.com/Andreiisthebest/student-id-university-record-service/issues/12)

The private feature branches are `feature/applicant-lab3-grade3` and
`feature/record-lab3-grade3`. This CPR change is documentation only: its image
tags and gitlinks still identify the published Lab 2 implementations. The
Grade 3 features described below require approval, private PR review/merge,
image publication and a subsequent owned-image/gitlink update before deployment.
They must not be inferred to exist in the current shared images.

## Health and HTTP metadata contract

| Service | Direct endpoint | Meaning |
| --- | --- | --- |
| Applicant | `GET /q/health` and `/q/health/ready` | Existing datasource-aware health; 200/UP when ready, 503/DOWN when unhealthy |
| Applicant | `GET /q/health/live` | Existing process liveness; does not assert database readiness |
| University Record | `GET /health` | Database readiness, with a one-second ping deadline: 200 `{"status":"UP"}` or 503 `{"status":"DOWN"}` |

Health checks stay outside the business-task concurrency limiter. Direct
endpoints are for internal/container health checks; the services keep their
existing private networks and host exposure. Existing Gateway health routes
are `/api/v1/health/applicant-service` and
`/api/v1/health/university-record-service`; Gateway code is not changed.

Both implementations add a generated UUID `X-Request-Id` response header.
Incoming IDs are replaced. This value is diagnostic metadata, not identity,
authorization, or a new Gateway forwarding contract. Existing business routes,
JSON payloads, error envelopes and task limits retain their behavior. Record's
health now distinguishes database failure using 503 instead of unconditional UP.

## Logging and verification

Completed HTTP requests log service name, generated request ID, method, bounded
route, final status, elapsed milliseconds and severity. Health, async failures,
overload and timeouts are included. Success logs at INFO, 4xx at WARN, and 5xx
at ERROR. Request bodies, authorization headers, query strings, raw resource IDs
and untrusted request IDs are omitted. Unknown paths use `/unmatched`.

Applicant uses the existing Quarkus/JBoss logger, including startup task-limit
and shutdown events. Record uses JSON `slog`, logs sanitized startup/database/
migration/listener stages and graceful shutdown, recovers panics, and suppresses
raw GORM/driver messages that could contain credentials or row values.

After the Grade 3 images are deployed, inspect only these services:

```bash
docker compose logs applicant-service university-record-service
```

Use the existing Compose project name. PostgreSQL test databases remain separate
from application data. Run `bash scripts/verify_ci.sh` in each private repository
with its isolated test database configured. Evidence at this checkpoint:

- Applicant: 18 tests passed; 95.1% line coverage. Tests include live health,
  asynchronous error logs, correlation and private-sentinel exclusion.
- Record: full Go race tests passed; 74.1% line and 72.8% statement coverage.
  New health/logging packages have 100% statement coverage. Tests include actual
  server wiring against PostgreSQL and health failure after its handle is closed.

These tests do not stop a running application database or change another owner's
service. Tests do not claim discovery registration, replicas, round-robin,
circuit breakers, health polling or notifications; those belong to later grades.
Grades 6, 8, 9 and 10 include common Gateway/Discovery responsibilities that
require coordination with their owners under the existing service-scope rule.
