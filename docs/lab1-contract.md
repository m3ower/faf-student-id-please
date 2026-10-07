# Lab 1 HTTP contract

The two Lab 1 services are independent HTTP/JSON CRUD services. Each owns its own PostgreSQL database; neither reads the other service's database.

## Applicant Service (shared Gateway, `http://localhost:8090`)

`POST /api/v1/applicants` and `PUT /api/v1/applicants/{id}` accept:

```json
{
  "name": "Ana Popescu",
  "studentId": "FAF-221",
  "major": "FAF",
  "studyYear": 2,
  "universityStatus": "ENROLLED",
  "role": "STUDENT",
  "courses": ["PAD", "OOP"]
}
```

`GET /api/v1/applicants`, `GET /api/v1/applicants/{id}`, and the mutation responses use the same object plus server-generated `id`, `createdAt`, and `updatedAt`. `DELETE /api/v1/applicants/{id}` returns `204`.

## University Record Service (shared Gateway, `http://localhost:8090`)

`POST /api/v1/university-records` and `PUT /api/v1/university-records/{id}` accept:

```json
{
  "studentId": "FAF-221",
  "name": "Ana Popescu",
  "major": "FAF",
  "enrolledSince": "2025-09-01",
  "status": "ENROLLED",
  "outlookGroups": ["FAF-221"],
  "courses": ["PAD"],
  "fcimMessages": ["Welcome to FAF"]
}
```

Get/list/mutation responses add UUID `id`, `createdAt`, and `updatedAt`. Delete returns `204`.

## Errors and integration boundary

Both services use this error shape: `{ "error": { "code", "message", "service", "details" } }`.

Common statuses: `400` invalid input, `404` missing resource, `409` duplicate `studentId`, `500` unexpected failure. Applicant and university records are intentionally separate claims/truth stores. Their eventual initialization and session-access interaction are covered by the team's gRPC/RabbitMQ contract, but have no required remote dependency in Lab 1; therefore no mock service is needed to keep either CRUD service operational.
