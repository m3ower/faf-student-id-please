# Applicant and University Record Postman checks

Updated on 2026-11-12. Only these service collections were refreshed:

- `applicant-service.postman_collection.json`
- `university-record-service.postman_collection.json`

Source: CPR `origin/dev` at `bdf7190`, fetched from GitHub. The API review used
Applicant `43b2a97` and University Record `3a2df99` (their merged dev source),
also included in their current main releases `92e7b9f` and `76e831c`.
The review PR preserves upstream release pointers; service implementation commits are unchanged.

## Public HTTP checks

Import both collections. In a private Postman environment, set `baseUrl` to the
running Gateway (default `http://localhost:8090`), `accessToken` to a valid player
JWT, and `managementToken` to the configured management credential. Keep exported
credentials empty. Run the Gateway boundary folder and the top-level CRUD
requests in order. Each CRUD sequence creates disposable rows and deletes them.

For Record enrollment reads, set `sessionId` to a live session where the JWT's
player has `ENROLLMENT_LIST` permission. If setting `playerId`, use that player's
actual UUID; Gateway derives trusted identity from the JWT. Removing client
identity headers does not change the JWT subject. The negative enrollment request
omits session context and expects a forbidden response.

The operational logs folder runs separately. Configure the log exporter for the
actual Compose project, set reachable `logDownloadUrl`, and supply its separate
`logDownloadToken`. Collection bearer authentication is not the exporter secret.

## Archived internal HTTP examples

Upstream archived the historical Task 5 examples under `postman/legacy` in
CPR `69b505a`. They are excluded from current public collections and the shared
collection. Do not use those HTTP adapters as Task 8 acceptance checks. The
current private transport is the shared native gRPC contract below.

## Native gRPC checks for these two services

Import the adjacent `messaging.proto` as the service definition in a Postman gRPC
request. It is an unchanged copy of CPR's shared
`contracts/proto/studentid/messaging/v1/messaging.proto`, not a new service API.
LF-normalized SHA-256:
`16f01b51c6d591eabcf3c5839b4d4e7135bf7022d88c5186fe4210d17f607288`.

Use `message-broker:9093` from the authorized private network. No consumer gRPC
port should be published to the host. Call `studentid.messaging.v1.MessageBroker/Publish`
with metadata `authorization: Bearer <publisher's Broker credential>` and
`x-trace-id` matching `traceId`. Do not supply a publisher identity header.

For example, inspect an existing Applicant initialization as the Session caller:

```json
{
  "messageId": "<fresh nonzero UUID>",
  "schemaVersion": 1,
  "kind": "REQUEST",
  "topic": "operation.applicant.getReadiness.v1",
  "traceId": "owned-postman-readiness",
  "correlationId": "<fresh nonzero UUID>",
  "deadlineAt": "<fresh UTC timestamp within the operation budget>",
  "arguments": {},
  "payloadJson": "<base64 of {\"applicantId\":\"<existing applicant UUID>\"}>"
}
```

GET bindings put path/query IDs in the JSON payload, not `arguments`. Protobuf
JSON represents bytes as base64. Prepare a fresh deadline immediately before send;
the catalog caps these operations at 750 ms and existing shorter service budgets
still apply. Expired timestamps must fail.

| Check | Topic | Publisher credential | Expected result group |
| --- | --- | --- | --- |
| Applicant readiness | `operation.applicant.getReadiness.v1` | Session | `applicant-service` |
| Applicant profile | `operation.applicant.getProfile.v1` | Session | `applicant-service` |
| Record readiness | `operation.record.getReadiness.v1` | Session | `university-record-service` |
| Record enrollment facts | `operation.record.enrollmentFacts.v1` | Credential | `university-record-service` |

All four use the same applicant-ID payload. A Session profile request may return
business 202 while initialization is pending. With `MessageBroker/GetResult`, use
the same publisher credential and `messageId` if Publish remains PENDING. Verify
message/correlation IDs, the exact expected group, terminal state, acknowledgment,
business status and decoded JSON body. A successful RPC or acknowledged group
alone does not establish a ready applicant. PENDING has no final business result;
NOT_FOUND after retention/restart means unknown delivery and does not justify
replaying an arbitrary mutation.

Broker-to-consumer delivery uses the same proto's `MessageConsumer/Deliver`.
Applicant listens privately on 9080; Record on 9081. Verify their standard gRPC
health for `studentid.messaging.v1.MessageConsumer` and actual Broker delivery
with matching reviewed transport choices and healthy dependencies. HTTP success
does not prove that delivery leg works over gRPC.

## Review evidence and limits

The refresh adds the latest Gateway authentication, management credentials,
operational logs and current Gateway boundary checks. Local corrections align
unsupported-method responses with the published Gateway allowlist and preserve
the upstream archive of obsolete internal adapters. Credentials remain empty in tracked exports.

Static validation checks JSON structure, JavaScript syntax, declared variables,
internal method/path/caller mappings against the fetched shared catalog, and the
unchanged proto hash. Live Postman/Newman and gRPC execution could not be performed:
the Docker Desktop Linux engine was unavailable during this review. Current
cross-service acceptance, deployment/image provenance and private credentials
remain runtime prerequisites. The existing `scripts/run_owned_postman.py` predates
the new optional folders and provides no private environment inputs; configure
Postman explicitly instead of treating that runner as a current acceptance gate.
