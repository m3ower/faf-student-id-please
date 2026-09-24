# Applicant and University Record — Lab 1 contract notes

This note covers only the two services owned by Bobeica Andrei. The published
Docker Hub `0.1.1` images provide the HTTP behavior below. Their source-level
Grade 9 in-process fake adapters are preparation for integration; they are not
live gRPC or RabbitMQ endpoints and are not exposed by these images.

## Current HTTP surface

Both services return JSON and run independently against separate PostgreSQL
databases. The shared Compose file maps Applicant to `localhost:8084` and
University Record to `localhost:8085`.

| Service | Methods and paths | Request and response data |
| --- | --- | --- |
| Applicant | `POST /api/v1/applicants` (`201`), `GET /api/v1/applicants` (`200`), `GET /api/v1/applicants/{id}` (`200`), `PUT /api/v1/applicants/{id}` (`200`), `DELETE /api/v1/applicants/{id}` (`204`) | Create/replace JSON requires `name`, `studentId`, `major`, `studyYear` (1–8), `universityStatus`, `role`, and `courses[]`. Responses include UUID `id`, those fields, `createdAt`, and `updatedAt`. |
| University Record | `POST /api/v1/university-records` (`201`), `GET /api/v1/university-records` (`200`), `GET /api/v1/university-records/{id}` (`200`), `PUT /api/v1/university-records/{id}` (`200`), `DELETE /api/v1/university-records/{id}` (`204`) | Create/replace JSON requires `studentId`, `name`, `major`, `enrolledSince` (`YYYY-MM-DD`), and `status`; `outlookGroups[]`, `courses[]`, and `fcimMessages[]` are string arrays. Responses include UUID `id`, those fields, `createdAt`, and `updatedAt`. |
| University Record | `GET /api/v1/records/enrollment?studentId=...` (`200`) | Requires `X-Session-Id` and `X-Player-Id`. Returns `{found,studentId,name,major,enrolledSince,status}`; `403` if its current Lab 1 verifier rejects the headers, `404` if the student is absent. |

`GET /q/health` (Applicant) and `GET /health` (University Record) report health.
Existing HTTP CRUD remains independent of other services. The enrollment
route's current HTTP verifier checks only for non-empty session/player headers;
it is **not real authorization** and is separate from the typed Grade 9 fake
described below. Do not expose management CRUD publicly without authentication.

The implemented HTTP errors include `400` invalid input, `404` missing record,
and `409` duplicate student ID where applicable. Their current error body is
`{ "error": { "code": "...", "message": "...", "service": "...", "details": {} } }`.
The CPR's planned general error envelope also includes `traceId`; that field
is not yet emitted by these two Lab 1 HTTP implementations.

## Agreed cross-service fixture slice

Session `55555555-5555-5555-5555-555555555555`, team
`66666666-6666-6666-6666-666666666666`, and ruleset version `1` are shared
fixture values. F1 is applicant `a0000000-0000-0000-0000-000000000001`, seed
`918273`, Vlad Cebotari, `FAF-221`, `vlad.cebotari@isa.utm.md`, deception
`NONE`. F2 is applicant `a0000000-0000-0000-0000-000000000002`, seed
`918274`, Ana Rusu, `FAF-222`, `ana.rusu@isa.utm.md`, deception
`FORGED_DOCUMENT`. In the owned mock code, major `FAF`, year `2`, enrollment
since `2024-09-01`, and active/enrolled status are local assumptions needed
to fill existing response types—not additional shared fixture requirements.

The CPR `ApplicantInitialized` payload remains
`{applicantId,seed,initiator,identity{name,studentId,year},deception{type,...}}`
inside the standard `{eventId,type,occurredAt,producer,version,payload}`
envelope. Email is a shared fixture value but is **not** added to the event's
documented `identity` fields. Each owned in-process adapter resolves it from
the agreed fixture ID. Applicant owns claims; University Record owns truth;
`FORGED_DOCUMENT` concerns Credential and does not alter F2's enrollment truth.

The in-process Applicant adapter can initiate or consume the typed event,
deduplicates repeated delivery, and exposes claim and Moderation-only deception
projections. Its fake `ShiftStarted` consumer pre-warms F1/F2 for the session.
The in-process Record adapter consumes or initiates the same event and calls a
typed fake `VerifyMembership(session_id,player_id) ->
{member,role,record_access[],channels[]}` client before returning record data.
It uses the CPR demo players: `22222222-2222-2222-2222-222222222222` for
`ENROLLMENT_LIST`, `33333333-3333-3333-3333-333333333333` for
`OUTLOOK_GROUPS`, and `44444444-4444-4444-4444-444444444444` for
`COURSE_CATALOG`. No CPR demo player has `FCIM_RECORD` access, so that fake
lookup fails closed. Unknown applicants/students are absent; unknown sessions
or unauthorized players do not receive record data. Repeated identical events
do not create duplicate mock records.

The planned gRPC and event contract remains in the CPR README. The in-process
adapters deliberately do not claim that live transport or cross-service
initialization is available in the published `0.1.1` images.
