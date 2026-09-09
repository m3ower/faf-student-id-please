# Student ID, please

A distributed, microservice-based multiplayer game about moderating a university
Discord server. A team of moderators receives applicants who want to join the
FAF community server. Applicants present credentials that may be expired, forged,
inconsistent or simply false. One player acts as the **Moderator** and speaks to
the applicant directly. The rest act as **Junior Moderators**, each holding a
different slice of the university's records, and must communicate their findings
before a decision is made.

Accept the right people, reject the wrong ones, uncover the impostors, and do not
traumatize Mr. Pumpkin with the emojis.

---

## Table of contents

1. [Team](#team)
2. [Service boundaries](#service-boundaries)
3. [Architecture diagram](#architecture-diagram)
4. [Technologies and communication patterns](#technologies-and-communication-patterns)
5. [Communication contract](#communication-contract)
   - [Surface map](#surface-map)
   - [Data management](#data-management)
   - [Applicant initialization](#applicant-initialization)
   - [REST endpoints](#rest-endpoints)
   - [gRPC services](#grpc-services)
   - [WebSocket protocol](#websocket-protocol)
   - [Asynchronous events](#asynchronous-events)
   - [Error envelope and status mapping](#error-envelope-and-status-mapping)
6. [Repository structure](#repository-structure)
7. [Contribution guide](#contribution-guide)
8. [Project board](#project-board)

---

## Team

| Member | Java service | Go service |
| --- | --- | --- |
| Pascari Vasile | Player Service | Moderation Session Service |
| Bobeica Andrei | Applicant Service | University Record Service |
| Clima Marin | Credential Service | Server Rules Service |
| Gurev Andreea | Moderation Service | Discord DMs Service |

Every member implements one service in **Java** and one in **Go**, so each of us
works in both languages of the project. Bobeica owns both the applicant's claims
and the university's ground truth deliberately: they are two halves of the same
seeded generation, and keeping them under one owner prevents them from drifting
apart accidentally.

---

## Service boundaries

Each microservice encapsulates one area of functionality and owns its data
exclusively. No service reads another service's database. The "does not own"
line for each service is the boundary that keeps the system modular.

### Player Service

Owns the identity and long-term progression of the **real players**.

- Registration, authentication, profiles
- Friends and online presence
- XP, levels, rank progression
- Formation of moderation teams

Progression is driven by completed shifts, decision accuracy and disciplinary
actions, all reported by the Moderation Session Service at the end of a shift.

**Does not own:** anything about the fictional applicants trying to enter the
server. A player and an applicant are unrelated concepts.

### Moderation Session Service

Owns one **active moderation shift**.

- Creating and joining sessions
- Assigning the Moderator and Junior Moderator roles
- Starting and ending shifts
- Tracking the current applicant in the queue
- Number of applications processed, session score, penalties

At the end of a shift it determines the overall session result and publishes it
so the Player Service can apply progression.

**Does not own:** the correctness of any individual decision, which belongs to
the Moderation Service, nor permanent player progression.

### Applicant Service

Owns the **people attempting to access the server**. It generates applicants with
a name, student ID, major, year, university status, courses and role.

Applicants may be FAF students, students from other majors, teaching assistants,
university staff, alumni or outsiders. Some intentionally provide false
information or attempt to impersonate another person.

**Does not own:** the truth. It owns only what the applicant *claims*. Whether
the claim matches reality is decided by comparison against the University Record
Service.

### Credential Service

Owns the **documents and credentials presented** by applicants: student ID,
university email, enrollment confirmation, course registration and similar.

Credentials can be expired, forged, inconsistent or incomplete. The service
validates the structure and authenticity of a credential.

**Does not own:** the admission decision. A perfectly valid document may still
belong to someone who is not allowed in.

### University Record Service

Owns the **hidden ground truth** of the university, used to verify applicants:
current enrollment list, Outlook group lists of emails, existing courses, current
academic year, semester schedule, FCIM server message record.

This information is deliberately partitioned among the junior moderator players.
One player may query the enrollment list while another can inspect the FCIM
server. Access is enforced per player and per session.

**Does not own:** applicant claims or credentials. It holds reality, not
assertions about it.

### Server Rules Service

Owns the **current rules for accessing the major's Discord server** and evaluates
applicants against them. Rules change between shifts and become progressively
more complicated. For example:

- Only FAF students may join
- First-year students may access `#general` but not `#dark-memes` or `#groupa`
- Students must be enrolled in FAF for at least 2 years
- Professors may access the teacher channels
- Previously banned students cannot enter regardless of their credentials

**Does not own:** the decision itself. It answers "which rules does this applicant
violate", not "let them in".

### Moderation Service

Owns the **admission decision** for each applicant. The Moderator may:

- **Accept** — allow the applicant into the Discord server
- **Reject** — deny access
- **Flag** — send the applicant for further investigation
- **Ban** — permanently prevent access

It gathers the relevant information, determines whether the decision was correct
according to the current server rules, and records the applicant, the decision,
the violated rules, the penalty and the outcome.

**Does not own:** applicant generation, credential validity or the rules
themselves. It consumes all three.

### Discord DMs Service

Owns the **real-time communication** between the moderator and the junior mods.
Players communicate through a Discord-like interface over WebSockets. Channels
are scoped to the current moderation session, for example `#enrollment-check`,
`#faculty-check`, `#course-registration`, `#general-mod-chat`.

Different players have access to different channels and different information.

**Does not own:** the correctness of anything said in a channel. The service
transports messages and does not determine whether the information is true.

---

## Architecture diagram

![Architecture diagram](https://github.com/m3ower/faf-student-id-please/blob/main/archdiagram.png "Architecture diagram")

**Legend**

- Solid arrow — synchronous request/response over REST or gRPC.
- Dotted arrow — asynchronous event published through the message broker.
- Colour groups services by ownership domain: player state, session state,
  decisions, applicant claims, ground truth, rules, transport.

The triangular `ApplicantInitialized` relationship between the Applicant,
Credential and University Record services is described in
[Applicant initialization](#applicant-initialization).

---

## Technologies and communication patterns

| Service | Language | Framework | Database | Surfaces exposed |
| --- | --- | --- | --- | --- |
| Player | Java 21 | Spring Boot | PostgreSQL | REST |
| Moderation Session | Go | Fiber | PostgreSQL + Redis | REST, gRPC |
| Applicant | Java 21 | Spring Boot | PostgreSQL | gRPC |
| Credential | Java 21 | Spring Boot | PostgreSQL | REST, gRPC |
| University Record | Go | Fiber | PostgreSQL | REST, gRPC |
| Server Rules | Go | Fiber | PostgreSQL | REST, gRPC |
| Moderation | Java 21 | Spring Boot | PostgreSQL | REST, gRPC |
| Discord DMs | Go | Gorilla WebSocket | Redis | WebSocket, REST |

Message broker: **RabbitMQ**. API gateway: **Traefik**. Everything runs under
`docker compose`.

### Why these choices

**Java for the services with the richest domain model.** Applicant, Credential
and Moderation carry almost all of the game's rules, and those rules grow every
time we add a new kind of lie, a new document type or a new interaction between
them. Credential validation is the clearest case: document kinds form a natural
type hierarchy, and modelling them as a sealed interface with one record per
credential type plus Bean Validation constraints means adding a forged-document
variant is a new subclass the compiler checks, not another branch in a
conditional that grows until nobody can read it. The Moderation Service benefits
from the same property, since a decision's correctness depends on combining
claims, credentials and rule violations, and an exhaustive `switch` over sealed
types fails to compile when we add a case we forgot to handle. Player Service is
Java for a narrower reason: Spring Security gives us registration, password
hashing, and JWT issue and refresh as configuration rather than code, and
authentication is the one part of this project we do not want to hand-roll.

The cost is real and we accept it. Four JVMs use noticeably more memory than four
Go processes, and Spring Boot's startup time makes a full `docker compose up`
slower than it would otherwise be. We considered Quarkus to reduce both and will
switch if local development becomes painful, but chose the more familiar stack
first because correctness of the domain logic matters more to this lab than
container startup speed.

**Go for the services dominated by connections and concurrency.** Discord DMs
holds one WebSocket per player for the length of a shift and fans every message
across four channels with per-player access filtering; goroutines and channels
make that a few dozen lines instead of a thread pool and a callback tangle. The
Session Service runs the live shift timer, the applicant queue and the session
state that every player polls, so it is the most read-heavy service in the
system. University Record serves many small partitioned lookups during a shift,
each one cheap and each one needing an access check. Server Rules is evaluated on
every single decision and benefits from a compiled, allocation-light path.

What we give up is expressiveness in the data layer. These four services have
simple schemas — records, rules, messages, session state — so the verbosity of
Go's error handling and the absence of an ORM costs us little here, which is
exactly why these four and not the other four.

**REST at the edge, gRPC between services.** The client is a browser game, so
everything it touches directly is REST over HTTP/JSON: readable in the network
tab, testable with curl, no proxy layer needed. Between services we use gRPC,
because those calls happen while a player is waiting and protobuf gives us both a
smaller wire format and generated stubs on both sides. The stubs matter more than
the latency: with a Java service calling a Go service, a single `.proto` file is
the only definition of the contract, and a field renamed on one side fails to
compile on the other instead of silently arriving as `null` at runtime.

We rejected gRPC everywhere because browsers cannot speak it without a gRPC-Web
proxy, which would add a component for no gain. We rejected REST everywhere
because the in-shift call chain — session to applicant, moderation to rules,
moderation to credential — would pay JSON serialisation three times per applicant
and, more importantly, would leave the Java/Go boundary defined only by prose in
this file.

**Events for anything not on the critical path.** Applicant initialization and
end-of-shift progression are asynchronous. Nobody is blocked waiting for XP to be
awarded, and coupling a shift's completion to the Player Service being up would
make a game fail for a cosmetic reason. We accept eventual consistency here: a
player may see their new level a second late, which does not affect play.

**Redis in two places.** As the session cache for live shift state, which is read
constantly and is rebuildable from PostgreSQL, and as the pub/sub backbone for
the Discord DMs Service so we can run more than one WebSocket instance without
players in the same session landing on different processes and losing each other.

---

## Communication contract

### Surface map

Every service exposes at most three kinds of surface. This table is the index;
each surface is specified in full below.

| Service | REST (via gateway) | gRPC (internal) | Events published |
| --- | --- | --- | --- |
| Player | auth, profiles, friends, teams | — | `PlayerProgressed` |
| Moderation Session | sessions, roles, shift control | `SessionService` | `ShiftStarted`, `SessionCompleted` |
| Applicant | — | `ApplicantService` | `ApplicantInitialized` |
| Credential | credential read for the moderator UI | `CredentialService` | `ApplicantInitialized` |
| University Record | partitioned record lookups | `RecordService` | `ApplicantInitialized` |
| Server Rules | current ruleset read | `RulesService` | `RulesUpdated` |
| Moderation | decision submission, history | `ModerationService` | `DecisionRecorded` |
| Discord DMs | channel list, history | — | — |

The Applicant Service has no REST surface. The client never queries applicants
directly; it receives the current applicant through the Session Service, which
keeps the queue and the "who is at the door right now" state in one place.

### Data management

Each service owns a **private database**. No shared tables, no cross-service
joins, no direct connections to another service's store. Data crosses a boundary
only through an endpoint or an event.

The critical consequence for this game: the **Applicant Service holds what the
applicant claims**, and the **University Record Service holds what is actually
true**. These are deliberately separate databases that can disagree. That
disagreement is the entire game. If they shared storage, an impostor would be
impossible to model.

Consistency is **eventual** between services and **strong** within a service. An
applicant is fully initialized across the three owning services before it is
offered to the session queue; the session polls for readiness rather than
assuming it.

Access control on the University Record Service is enforced per session and per
player. Every read is checked against the record assignment for that shift, so a
junior moderator cannot query records they were not given.

**Deployment note.** All eight databases run inside a single PostgreSQL container
in development, as eight separate databases with eight separate credentials. This
is a resource concession for local machines, not a relaxation of the boundary: no
service holds credentials for another's database and no query crosses a schema.
In any non-local deployment each service gets its own instance.

### Applicant initialization

Any of the three applicant-owning services may be contacted first for a new
applicant. Whichever one receives the request becomes the **initiator**:

1. The initiator generates its own part of the applicant and assigns the
   `applicantId`.
2. It publishes `ApplicantInitialized` containing the shared seed information.
3. The other two services consume the event and generate their own part,
   consistently with the seed.

If a service is contacted for an `applicantId` it has already received an event
for, it returns the stored data rather than generating anything. Generation is
therefore idempotent and the three parts of an applicant never contradict each
other by accident — only when the game intends them to.

```
Case A: Applicant Service first
  Applicant → ApplicantInitialized → Credential, University Record

Case B: Credential Service first
  Credential → ApplicantInitialized → Applicant, University Record

Case C: University Record Service first
  University Record → ApplicantInitialized → Applicant, Credential
```

The event carries a `deception` block describing the intended inconsistency, so
that the lying is coordinated rather than random:

```json
{
  "applicantId": "a3f1...",
  "seed": 918273,
  "initiator": "applicant-service",
  "identity": { "name": "Vlad Cebotari", "studentId": "FAF-221", "year": 2 },
  "deception": { "type": "IMPERSONATION", "impersonatedStudentId": "FAF-213" }
}
```

`deception.type` is one of `NONE`, `IMPERSONATION`, `FORGED_DOCUMENT`,
`EXPIRED_DOCUMENT`, `INCONSISTENT_CLAIM`, `NOT_ENROLLED`, `PREVIOUSLY_BANNED`.

---

### REST endpoints

All REST paths are prefixed `/api/v1`. Bodies are JSON. Authenticated endpoints
require `Authorization: Bearer <token>`.

#### Player Service

```
POST /api/v1/players/register
Request:  { "username": "string", "email": "string", "password": "string" }
Response: 201 { "playerId": "uuid", "username": "string", "level": 1, "xp": 0 }
Errors:   409 username or email taken | 422 validation failed
```

```
POST /api/v1/players/login
Request:  { "email": "string", "password": "string" }
Response: 200 { "accessToken": "jwt", "refreshToken": "jwt", "expiresIn": 3600 }
Errors:   401 invalid credentials
```

```
POST /api/v1/players/refresh
Request:  { "refreshToken": "jwt" }
Response: 200 { "accessToken": "jwt", "expiresIn": 3600 }
Errors:   401 expired or revoked refresh token
```

```
GET /api/v1/players/{playerId}
Response: 200 {
  "playerId": "uuid", "username": "string", "level": 7, "xp": 3420,
  "rank": "SENIOR_MODERATOR", "shiftsCompleted": 41, "accuracy": 0.86,
  "disciplinaryActions": 2, "online": true
}
Errors:   404 player not found
```

```
POST /api/v1/players/{playerId}/friends
Request:  { "targetPlayerId": "uuid" }
Response: 202 { "status": "PENDING" }
Errors:   404 player not found | 409 already friends or request pending
```

```
GET /api/v1/players/{playerId}/friends
Response: 200 { "friends": [ { "playerId": "uuid", "username": "string", "online": true } ] }
```

```
POST /api/v1/teams
Request:  { "name": "string", "ownerId": "uuid" }
Response: 201 { "teamId": "uuid", "name": "string", "members": ["uuid"] }
Errors:   409 team name taken
```

```
POST /api/v1/teams/{teamId}/members
Request:  { "playerId": "uuid" }
Response: 200 { "teamId": "uuid", "members": ["uuid"] }
Errors:   404 team not found | 409 already a member | 422 team full
```

#### Moderation Session Service

```
POST /api/v1/sessions
Request:  { "teamId": "uuid", "hostPlayerId": "uuid", "difficulty": "EASY|NORMAL|HARD" }
Response: 201 {
  "sessionId": "uuid", "state": "LOBBY", "hostPlayerId": "uuid",
  "players": [ { "playerId": "uuid", "role": "UNASSIGNED" } ]
}
Errors:   404 team not found | 409 team already in a session
```

```
POST /api/v1/sessions/{sessionId}/join
Request:  { "playerId": "uuid" }
Response: 200 { "sessionId": "uuid", "players": [ { "playerId": "uuid", "role": "UNASSIGNED" } ] }
Errors:   404 session not found | 409 session already started | 422 session full
```

```
POST /api/v1/sessions/{sessionId}/roles
Request:  { "assignments": [ { "playerId": "uuid", "role": "MODERATOR|JUNIOR_MODERATOR" } ] }
Response: 200 {
  "sessionId": "uuid",
  "players": [ { "playerId": "uuid", "role": "JUNIOR_MODERATOR",
                 "recordAccess": ["ENROLLMENT_LIST"], "channels": ["#enrollment-check"] } ]
}
Errors:   403 caller is not the host | 409 roles already assigned
          | 422 exactly one moderator required
```

```
POST /api/v1/sessions/{sessionId}/start
Response: 200 {
  "sessionId": "uuid", "state": "ACTIVE", "startedAt": "2026-09-08T18:00:00Z",
  "rulesetVersion": 12, "applicantsQueued": 10
}
Errors:   403 caller is not the host | 409 already started | 422 roles not assigned
```

```
GET /api/v1/sessions/{sessionId}
Response: 200 {
  "sessionId": "uuid", "state": "LOBBY|ACTIVE|COMPLETED",
  "currentApplicantId": "uuid", "applicationsProcessed": 4,
  "score": 340, "penalties": 1, "timeRemaining": 512
}
Errors:   404 session not found
```

```
GET /api/v1/sessions/{sessionId}/current-applicant
Response: 200 {
  "applicantId": "uuid", "position": 5, "remaining": 5,
  "profile": {
    "name": "Vlad Cebotari", "studentId": "FAF-221", "major": "FAF",
    "year": 2, "universityStatus": "ENROLLED", "role": "STUDENT",
    "courses": ["PAD", "SO", "AI"]
  }
}
Notes:    profile is relayed from the Applicant Service over gRPC
Errors:   404 session not found | 409 no applicant at the door
```

```
POST /api/v1/sessions/{sessionId}/next-applicant
Response: 200 { "applicantId": "uuid", "position": 5, "remaining": 5 }
Errors:   404 queue empty | 409 current applicant has no decision yet
```

```
POST /api/v1/sessions/{sessionId}/end
Response: 200 {
  "sessionId": "uuid", "state": "COMPLETED",
  "result": { "score": 780, "correct": 8, "incorrect": 2,
              "penalties": 1, "outcome": "PASSED" }
}
Errors:   409 session not active
```

#### Credential Service

```
GET /api/v1/credentials/applicant/{applicantId}
Headers:  X-Session-Id
Response: 200 {
  "applicantId": "uuid",
  "credentials": [
    { "credentialId": "uuid", "type": "STUDENT_ID", "issuedAt": "2024-09-01",
      "expiresAt": "2028-07-01",
      "fields": { "studentId": "FAF-221", "photoUrl": "string" } },
    { "credentialId": "uuid", "type": "UNIVERSITY_EMAIL",
      "fields": { "email": "vlad.cebotari@isa.utm.md" } }
  ]
}
Notes:    what the applicant handed over, exactly as presented, with no verdict
Errors:   403 caller is not in this session | 404 applicant not found
```

```
GET /api/v1/credentials/types
Response: 200 { "types": ["STUDENT_ID", "UNIVERSITY_EMAIL",
                          "ENROLLMENT_CONFIRMATION", "COURSE_REGISTRATION"] }
```

#### University Record Service

Every lookup requires `X-Session-Id` and `X-Player-Id`, and is rejected with 403
if that player was not assigned the corresponding record type for that shift.

```
GET /api/v1/records/enrollment?studentId=FAF-221
Headers:  X-Session-Id, X-Player-Id
Response: 200 {
  "found": true, "studentId": "FAF-221", "name": "Vlad Cebotari",
  "major": "FAF", "enrolledSince": "2024-09-01", "status": "ACTIVE"
}
Errors:   403 player not assigned to ENROLLMENT_LIST | 404 not enrolled
```

```
GET /api/v1/records/outlook-groups?email=vlad.cebotari@isa.utm.md
Headers:  X-Session-Id, X-Player-Id
Response: 200 { "found": true, "groups": ["FAF-221", "FCIM-STUDENTS"] }
Errors:   403 player not assigned to OUTLOOK_GROUPS
```

```
GET /api/v1/records/courses?semester=2026-1
Headers:  X-Session-Id, X-Player-Id
Response: 200 { "semester": "2026-1",
                "courses": [ { "code": "PAD", "name": "Distributed Systems", "year": 3 } ] }
Errors:   403 player not assigned to COURSE_CATALOG
```

```
GET /api/v1/records/fcim-messages?studentId=FAF-221
Headers:  X-Session-Id, X-Player-Id
Response: 200 { "messages": [ { "channel": "#general",
                                "sentAt": "2026-03-04T10:22:00Z", "excerpt": "string" } ] }
Errors:   403 player not assigned to FCIM_RECORD
```

```
GET /api/v1/records/academic-context
Response: 200 { "academicYear": "2026/2027", "semester": "2026-1", "weekOfSemester": 3 }
Notes:    unrestricted; every player may see the calendar
```

#### Server Rules Service

```
GET /api/v1/rules/current?sessionId={sessionId}
Response: 200 {
  "rulesetVersion": 12,
  "rules": [
    { "code": "FAF_ONLY", "description": "Only FAF students may join",
      "severity": "CRITICAL" },
    { "code": "MIN_2_YEARS",
      "description": "Must be enrolled in FAF for at least 2 years",
      "severity": "MAJOR" },
    { "code": "NO_BANNED",
      "description": "Previously banned students cannot enter",
      "severity": "CRITICAL" }
  ]
}
Errors:   404 session not found
```

#### Moderation Service

```
POST /api/v1/decisions
Request:  {
  "sessionId": "uuid", "applicantId": "uuid", "moderatorId": "uuid",
  "action": "ACCEPT|REJECT|FLAG|BAN", "reason": "string"
}
Response: 201 {
  "decisionId": "uuid", "correct": false,
  "expectedAction": "REJECT", "violatedRules": ["MIN_2_YEARS"],
  "penalty": 50, "scoreDelta": -50, "sessionScore": 290
}
Errors:   403 caller is not the moderator | 404 applicant not found
          | 409 decision already recorded for this applicant
```

```
GET /api/v1/decisions/{decisionId}
Response: 200 { "decisionId": "uuid", "sessionId": "uuid", "applicantId": "uuid",
                "action": "REJECT", "correct": true, "violatedRules": [],
                "decidedAt": "2026-09-08T18:12:44Z" }
Errors:   404 decision not found
```

```
GET /api/v1/decisions/session/{sessionId}
Response: 200 { "sessionId": "uuid", "decisions": [ ... ],
                "correct": 8, "incorrect": 2 }
```

```
POST /api/v1/decisions/{decisionId}/appeal
Request:  { "playerId": "uuid", "argument": "string" }
Response: 200 { "decisionId": "uuid", "upheld": true, "penaltyRefunded": 0 }
Errors:   404 decision not found | 409 appeal window closed
```

#### Discord DMs Service

```
GET /api/v1/channels?sessionId={sessionId}&playerId={playerId}
Response: 200 { "channels": [ { "name": "#enrollment-check", "canWrite": true } ] }
Errors:   403 player not in session
```

```
GET /api/v1/channels/{channel}/history?sessionId={sessionId}&limit=50
Response: 200 { "channel": "#enrollment-check", "messages": [ ... ] }
Errors:   403 player has no access to this channel
```

---

### gRPC services

Proto files live in [`contracts/proto/`](contracts/proto) at the root of the CPR
and are consumed by every service, so Java and Go generate their stubs from the
same source of truth. `syntax = "proto3"` throughout; `package studentid.v1`.

#### `common.proto`

```protobuf
message Applicant {
  string applicant_id = 1;
  string name = 2;
  string student_id = 3;
  string major = 4;
  int32  year = 5;
  UniversityStatus university_status = 6;
  ApplicantRole role = 7;
  repeated string courses = 8;
}

enum UniversityStatus { STATUS_UNSPECIFIED = 0; ENROLLED = 1; GRADUATED = 2;
                        EXPELLED = 3; NEVER_ENROLLED = 4; }
enum ApplicantRole    { ROLE_UNSPECIFIED = 0; STUDENT = 1; TEACHING_ASSISTANT = 2;
                        STAFF = 3; ALUMNI = 4; OUTSIDER = 5; }
enum DeceptionType    { DECEPTION_UNSPECIFIED = 0; NONE = 1; IMPERSONATION = 2;
                        FORGED_DOCUMENT = 3; EXPIRED_DOCUMENT = 4;
                        INCONSISTENT_CLAIM = 5; NOT_ENROLLED = 6;
                        PREVIOUSLY_BANNED = 7; }
enum Severity         { SEVERITY_UNSPECIFIED = 0; MINOR = 1; MAJOR = 2; CRITICAL = 3; }
enum Action           { ACTION_UNSPECIFIED = 0; ACCEPT = 1; REJECT = 2; FLAG = 3; BAN = 4; }
```

#### `applicant.proto` — Applicant Service

```protobuf
service ApplicantService {
  rpc CreateApplicant (CreateApplicantRequest) returns (ApplicantResponse);
  rpc GetApplicant    (GetApplicantRequest)    returns (ApplicantResponse);
  rpc GetClaims       (GetApplicantRequest)    returns (ClaimsResponse);
  rpc GetDeception    (GetApplicantRequest)    returns (DeceptionResponse);
}

message CreateApplicantRequest {
  string session_id = 1;
  string difficulty = 2;   // EASY | NORMAL | HARD
  int64  seed = 3;
}
message GetApplicantRequest { string applicant_id = 1; }
message ApplicantResponse   { Applicant applicant = 1; }

message Claim          { string field = 1; string value = 2; }
message ClaimsResponse { string applicant_id = 1; repeated Claim claims = 2; }

message DeceptionResponse {
  string applicant_id = 1;
  DeceptionType type = 2;
  string impersonated_student_id = 3;
  repeated string inconsistent_fields = 4;
}
```

`GetDeception` is called only by the Moderation Service when scoring a decision.
It is never routed through the gateway and never reaches a client.

#### `credential.proto` — Credential Service

```protobuf
service CredentialService {
  rpc GenerateCredentials (GenerateCredentialsRequest) returns (CredentialsResponse);
  rpc GetCredentials      (ApplicantRef)               returns (CredentialsResponse);
  rpc ValidateCredential  (ValidateCredentialRequest)  returns (ValidationResponse);
}

message ApplicantRef               { string applicant_id = 1; }
message GenerateCredentialsRequest { string applicant_id = 1; int64 seed = 2; }

message Credential {
  string credential_id = 1;
  CredentialType type = 2;
  string issued_at = 3;                 // ISO-8601 date
  string expires_at = 4;
  map<string, string> fields = 5;
}
enum CredentialType { CREDENTIAL_UNSPECIFIED = 0; STUDENT_ID = 1;
                      UNIVERSITY_EMAIL = 2; ENROLLMENT_CONFIRMATION = 3;
                      COURSE_REGISTRATION = 4; }

message CredentialsResponse { string applicant_id = 1; repeated Credential credentials = 2; }

message ValidateCredentialRequest { string credential_id = 1; }
message ValidationResponse {
  string credential_id = 1;
  bool structurally_valid = 2;
  bool authentic = 3;
  repeated string issues = 4;   // SIGNATURE_MISMATCH, EXPIRED, MISSING_FIELD, ...
}
```

#### `record.proto` — University Record Service

```protobuf
service RecordService {
  rpc InitializeRecords   (InitializeRecordsRequest) returns (InitializeRecordsResponse);
  rpc LookupEnrollment    (EnrollmentQuery)          returns (EnrollmentResponse);
  rpc LookupOutlookGroups (EmailQuery)               returns (OutlookGroupsResponse);
  rpc ListCourses         (SemesterQuery)            returns (CoursesResponse);
  rpc LookupFcimMessages  (EnrollmentQuery)          returns (FcimMessagesResponse);
  rpc GetAcademicContext  (Empty)                    returns (AcademicContextResponse);
}

message Empty {}
message InitializeRecordsRequest  { string applicant_id = 1; int64 seed = 2; }
message InitializeRecordsResponse { string applicant_id = 1; repeated string records_created = 2; }

message EnrollmentQuery { string student_id = 1; string session_id = 2; string player_id = 3; }
message EmailQuery      { string email = 1;      string session_id = 2; string player_id = 3; }
message SemesterQuery   { string semester = 1;   string session_id = 2; string player_id = 3; }

message EnrollmentResponse {
  bool found = 1; string student_id = 2; string name = 3;
  string major = 4; string enrolled_since = 5; string status = 6;
}
message OutlookGroupsResponse   { bool found = 1; repeated string groups = 2; }
message Course                  { string code = 1; string name = 2; int32 year = 3; }
message CoursesResponse         { string semester = 1; repeated Course courses = 2; }
message FcimMessage             { string channel = 1; string sent_at = 2; string excerpt = 3; }
message FcimMessagesResponse    { repeated FcimMessage messages = 1; }
message AcademicContextResponse { string academic_year = 1; string semester = 2; int32 week_of_semester = 3; }
```

`session_id` and `player_id` are carried in the message rather than in metadata,
so the access check is part of the contract and cannot be forgotten by a caller.
Violations return `PERMISSION_DENIED`.

#### `rules.proto` — Server Rules Service

```protobuf
service RulesService {
  rpc GetCurrentRuleset (SessionRef)      returns (RulesetResponse);
  rpc Evaluate          (EvaluateRequest) returns (EvaluationResponse);
  rpc RotateRuleset     (RotateRequest)   returns (RotateResponse);
}

message SessionRef      { string session_id = 1; }
message Rule            { string code = 1; string description = 2; Severity severity = 3; }
message RulesetResponse { int32 ruleset_version = 1; repeated Rule rules = 2; }

message EvaluateRequest { string session_id = 1; string applicant_id = 2; }
message Violation       { string code = 1; Severity severity = 2; }
message EvaluationResponse {
  string applicant_id = 1;
  int32 ruleset_version = 2;
  repeated Violation violations = 3;
  Action recommended_action = 4;
}

message RotateRequest  { string session_id = 1; string difficulty = 2; }
message RotateResponse { int32 ruleset_version = 1; repeated string added = 2;
                         repeated string removed = 3; }
```

#### `moderation.proto` — Moderation Service

```protobuf
service ModerationService {
  rpc SubmitDecision       (SubmitDecisionRequest) returns (DecisionResponse);
  rpc GetDecision          (DecisionRef)           returns (DecisionResponse);
  rpc ListSessionDecisions (SessionRef)            returns (SessionDecisionsResponse);
}

message SubmitDecisionRequest {
  string session_id = 1; string applicant_id = 2; string moderator_id = 3;
  Action action = 4; string reason = 5;
}
message DecisionRef { string decision_id = 1; }
message DecisionResponse {
  string decision_id = 1; bool correct = 2; Action expected_action = 3;
  repeated string violated_rules = 4; int32 penalty = 5;
  int32 score_delta = 6; int32 session_score = 7; string decided_at = 8;
}
message SessionDecisionsResponse {
  string session_id = 1; repeated DecisionResponse decisions = 2;
  int32 correct = 3; int32 incorrect = 4;
}
```

#### `session.proto` — Moderation Session Service

```protobuf
service SessionService {
  rpc GetSessionState  (SessionRef)        returns (SessionStateResponse);
  rpc VerifyMembership (MembershipRequest) returns (MembershipResponse);
  rpc ApplyScoreDelta  (ScoreDeltaRequest) returns (SessionStateResponse);
}

message SessionStateResponse {
  string session_id = 1; string state = 2; string current_applicant_id = 3;
  int32 applications_processed = 4; int32 score = 5; int32 penalties = 6;
  int32 ruleset_version = 7; int32 time_remaining = 8;
}
message MembershipRequest  { string session_id = 1; string player_id = 2; }
message MembershipResponse {
  bool member = 1; string role = 2;
  repeated string record_access = 3; repeated string channels = 4;
}
message ScoreDeltaRequest { string session_id = 1; int32 delta = 2; int32 penalty = 3; }
```

`VerifyMembership` is what the Discord DMs Service and the University Record
Service call to enforce per-player access, so the assignment of records and
channels is decided in exactly one place.

---

### WebSocket protocol

```
WS /ws/v1/sessions/{sessionId}?playerId={playerId}&token={jwt}
Handshake: 101 Switching Protocols
Errors:    401 invalid token | 403 player not in session | 404 session not found
```

Client to server:

```json
{ "type": "MESSAGE_SEND", "channel": "#enrollment-check",
  "content": "FAF-221 is not on the list" }
{ "type": "CHANNEL_JOIN", "channel": "#faculty-check" }
{ "type": "TYPING", "channel": "#general-mod-chat" }
```

Server to client:

```json
{ "type": "MESSAGE_RECEIVED", "messageId": "uuid", "channel": "#enrollment-check",
  "senderId": "uuid", "senderName": "string", "content": "string",
  "sentAt": "2026-09-08T18:07:02Z" }
{ "type": "APPLICANT_CHANGED", "applicantId": "uuid", "position": 5 }
{ "type": "SESSION_ENDED", "result": { "score": 780, "outcome": "PASSED" } }
{ "type": "ERROR", "code": "CHANNEL_FORBIDDEN", "message": "string" }
```

Channel membership is resolved at connection time through
`SessionService.VerifyMembership` and cached for the lifetime of the socket.

---

### Asynchronous events

All events are published to RabbitMQ on the topic exchange `studentid.events`.
Envelope:

```json
{
  "eventId": "uuid",
  "type": "ApplicantInitialized",
  "occurredAt": "2026-09-08T18:04:11Z",
  "producer": "applicant-service",
  "version": 1,
  "payload": { }
}
```

| Event | Producer | Consumers | Payload |
| --- | --- | --- | --- |
| `ApplicantInitialized` | Applicant, Credential or University Record | the other two | `applicantId`, `seed`, `initiator`, `identity`, `deception` |
| `RulesUpdated` | Server Rules | Moderation, Session | `sessionId`, `rulesetVersion`, `added`, `removed` |
| `DecisionRecorded` | Moderation | Session | `sessionId`, `applicantId`, `action`, `correct`, `scoreDelta` |
| `ShiftStarted` | Session | Discord DMs, Applicant | `sessionId`, `players`, `rulesetVersion` |
| `SessionCompleted` | Session | Player | `sessionId`, `players`, `score`, `outcome`, `accuracy`, `penalties` |
| `PlayerProgressed` | Player | Session | `playerId`, `level`, `xp`, `rank` |

Events are JSON rather than protobuf, because consumers are decoupled from
producers by design and a broker message should stay readable in the RabbitMQ
management UI while we are debugging. Consumers must be idempotent on `eventId`.
Failed handling is retried three times with exponential backoff before the
message is routed to `studentid.events.dlq`.

---

### Error envelope and status mapping

Every REST service returns the same shape on failure:

```json
{
  "error": {
    "code": "APPLICANT_NOT_FOUND",
    "message": "No applicant exists with the given id",
    "service": "applicant-service",
    "traceId": "uuid",
    "details": { "applicantId": "a3f1..." }
  }
}
```

gRPC calls return the equivalent condition as a status code, with the same `code`
and `traceId` attached as `google.rpc.ErrorInfo` in the status details. A
gateway-facing service translates an inbound gRPC failure into the HTTP status on
the same row.

| HTTP | gRPC status | Meaning |
| --- | --- | --- |
| 400 | `INVALID_ARGUMENT` | Malformed request |
| 401 | `UNAUTHENTICATED` | Missing or invalid token |
| 403 | `PERMISSION_DENIED` | Authenticated but not permitted, including record access violations |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `ABORTED` | Conflict with current state |
| 422 | `FAILED_PRECONDITION` | Semantically invalid input |
| 429 | `RESOURCE_EXHAUSTED` | Rate limit exceeded |
| 500 | `INTERNAL` | Unhandled server error |
| 503 | `UNAVAILABLE` | Downstream dependency unavailable |

---

## Repository structure

```
.
├── contracts/
│   └── proto/
│       ├── common.proto
│       ├── applicant.proto
│       ├── credential.proto
│       ├── record.proto
│       ├── rules.proto
│       ├── moderation.proto
│       └── session.proto
├── docs/
│   ├── architecture.mmd
│   └── architecture.png
├── services/
│   ├── player-service/              (submodule, private, Java)
│   ├── session-service/             (submodule, private, Go)
│   ├── applicant-service/           (submodule, private, Java)
│   ├── credential-service/          (submodule, private, Java)
│   ├── credential-service/          (submodule, private, Go)
│   ├── rules-service/               (submodule, private, Go)
│   ├── moderation-service/          (submodule, private, Java)
│   └── discord-dms-service/         (submodule, private, Go)
├── .github/
│   ├── pull_request_template.md
│   └── CODEOWNERS
├── .gitmodules
├── docker-compose.yml
└── README.md
```

Each microservice lives in its own **private** repository linked here as a git
submodule. Only the professor is invited to those repositories.

```bash
git clone --recurse-submodules https://github.com/<org>/<cpr>.git
# already cloned:
git submodule update --init --recursive
```

Submodule contents are not readable by anyone outside the team and the professor.
Visitors see the commit pointer but cannot fetch the objects, which is the
expected behaviour for a private submodule inside a public repository.

Each service repository carries its own README containing that service's slice of
this contract: the endpoints or RPCs it exposes, the events it publishes, the
events it consumes and the services that call it. Proto files are pulled from
`contracts/proto` rather than copied, so there is one definition of every message
in the system.

---

## Contribution guide

### Branches

| Branch | Purpose |
| --- | --- |
| `main` | Stable, protected. Only receives merges from `dev` via release PR. |
| `dev` | Integration branch. All feature work targets this. |
| `feature/<scope>-<short-description>` | New functionality |
| `fix/<scope>-<short-description>` | Bug fixes |
| `docs/<short-description>` | Documentation only |
| `chore/<short-description>` | Tooling, CI, dependencies |

`<scope>` is the service name, for example
`feature/credential-forged-document-detection`.

### Commits

Conventional Commits, imperative mood, lowercase subject, no trailing period:

```
feat(credential): detect signature mismatch on student ids
fix(session): prevent double role assignment on rejoin
docs(readme): add communication contract for rules service
```

### Pull requests

- Target `dev`. Only release PRs target `main`.
- **2 approvals required** before merge, and at least one must be from a member
  who does not own the service being changed.
- All CI checks must pass.
- Branch must be up to date with `dev`.
- **Squash merge** only, so `dev` history stays one commit per feature.
- The source branch is deleted on merge.
- Stale approvals are dismissed when new commits are pushed.
- Force pushes and deletions are blocked on `main` and `dev`.

Every PR must contain: a description of what changed and why, the linked issue, a
note on any contract change, and evidence of testing.

### Testing

- Minimum **70% line coverage** per service; CI fails below the threshold.
- Unit tests are mandatory for rule evaluation, credential validation and
  decision correctness, which are the three places a bug is invisible in play.
- Any change to a `.proto` file, a REST payload or an event payload requires an
  accompanying update to the [Communication contract](#communication-contract)
  in the same PR, and a PR against the affected service's own README.

### Versioning

Semantic versioning, tagged on `main`:

- **MAJOR** — a breaking change to an endpoint, RPC or event payload
- **MINOR** — a backwards-compatible addition
- **PATCH** — a fix with no contract change

Services version independently. The `/api/v1` prefix and the `studentid.v1` proto
package change only together, on a MAJOR release.

### Code review expectations

Reviewers check boundary violations first: a PR that makes one service read
another's database or duplicate its responsibility is rejected regardless of
whether it works.

---

## Project board

Work is tracked on the GitHub Project linked to this repository:

**[Student ID, please — project board](https://github.com/orgs/<org>/projects/<n>)**

Columns are **Backlog → In Progress → In Review → Done**. Every PR is linked to an
issue, and every issue is assigned to the owner of the affected service.
