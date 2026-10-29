# Applicant and University Record: Lab 2 Grade 6

This continues Andrei's two existing Lab 1 services in the original project.
Their images, CRUD payloads, databases, and in-process integration mocks retain
their current behavior. Their REST entry point is Gateway at `http://localhost:8090`.

| REST paths | Owner | Named health route |
| --- | --- | --- |
| `/api/v1/applicants` | Applicant | `/api/v1/health/applicant-service` |
| `/api/v1/university-records`, `/api/v1/records` | University Record | `/api/v1/health/university-record-service` |

Each owned service and its PostgreSQL container shares a dedicated internal
network with Gateway. Neither service publishes a host HTTP port. Gateway keeps
its existing default network and also joins the two owned networks. Its
`APPLICANT_SERVICE_URL` and `RECORD_SERVICE_URL` target the owned containers.
The owned services' `GATEWAY_URL`, `APPLICANT_SERVICE_URL`, and `RECORD_SERVICE_URL`
point to Gateway for any REST adapter; their existing mock calls remain in process.

The image for this integration is
`vasiok11/student-id-gateway-service:lab2-0.2.0`, as configured by its owner in
the shared deployment. Build it locally before running until its owner publishes
the tag. It uses the Gateway routing code already pinned by the CPR.

```bash
docker build -t vasiok11/student-id-gateway-service:lab2-0.2.0 services/gateway-service
# Set GATEWAY_IMAGE to the image above in your ignored .env.
docker compose up -d applicant-service university-record-service gateway-service
```

Populate the existing password variables in `.env`; keep the Record password
URL-safe because its database connection URL embeds it. All existing named
volumes retain their data. Teammates' service configuration and collections
follow their owners' deployment work.

Import the two owned Postman collections and run them in order. The preserved
combined Applicant/Record collection also uses Gateway. A Docker Newman runner
and a focused deployment verifier are available:

```bash
python scripts/verify_owned_grade6.py --project <compose-project> --base-url http://localhost:8090
python scripts/run_owned_postman.py --project <compose-project>
```

Reports are stored under ignored `docs-local/`. These checks cover the two owned
services; completion of the entire team's Grade 6 deployment depends on each owner.
