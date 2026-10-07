# Applicant and University Record: Lab 2 Grade 7

This assessment continues Andrei's existing Lab 1 services and their Grade 6
Gateway integration. Its scope is Applicant and University Record.

## Requirement and decision

`PAD_LAB_2.pdf` asks to upgrade services **that require WebSocket or SSE**.
For WebSockets, Gateway must negotiate a direct service URL; the connection then
goes directly to the owning service.

Neither owned service requires a browser stream under the current communication
contract. Their existing REST traffic continues through Gateway on port `8090`.
Grade 7 therefore requires no transport implementation change in this slice.

| Service | Current communication | Reason to retain it |
| --- | --- | --- |
| Applicant | HTTP/JSON CRUD; planned unary gRPC for profiles and claims | Each operation returns a finite result. Session owns the active applicant and queue progression. |
| University Record | HTTP/JSON CRUD and enrollment lookup; planned unary gRPC for record queries | Each lookup returns a requested projection. The gameplay contract scopes access to the requesting player and session. |

The planned gRPC and RabbitMQ integrations remain separate future transports.
The Lab 1 typed adapters are in-process mocks; the published `0.1.1` runtime does
not expose live gRPC or RabbitMQ endpoints.

## Ownership of updates

Applicant stores claims. The browser's `APPLICANT_CHANGED` notification follows
a change to the current item in the Session-owned queue, rather than any edit
to an applicant's stored profile. In the planned game flow, Applicant supplies
the profile to Session through the agreed internal contract.

University Record stores the hidden ground truth. Its `fcimMessages` are stored
record evidence returned on lookup; they are not a live chat feed. A broadcast
of record mutations would require a new requirement and per-player access rules.

`ApplicantInitialized` coordinates Applicant, Credential and University Record
internally. Its deception information belongs in that internal contract.
Consuming or publishing it does not require a browser WebSocket or SSE endpoint.

The team's browser WebSocket contract belongs to Discord DMs. Its connection
negotiation and any other owner's streaming work are handled by those owners.
Completion of the team's Grade 7 depends on those implementations.

## Evidence

The decision follows the existing contracts and registered handlers:

- [CPR surface map](../README.md#surface-map),
  [WebSocket protocol](../README.md#websocket-protocol), and
  [asynchronous events](../README.md#asynchronous-events).
- [Applicant REST contract](../services/applicant-service/README.md) and
  [registered resource](../services/applicant-service/src/main/java/md/usm/faf/applicant/api/ApplicantResource.java).
- [University Record contract](../services/university-record-service/README.md),
  [registered routes](../services/university-record-service/cmd/server/main.go), and
  [lookup handlers](../services/university-record-service/internal/records/handler.go).

The latest fetched owner branches add only Lab 1 in-process integration mocks;
their existing HTTP handlers still use request/response communication.

Read-only verification through the existing focused Gateway deployment returned
`200` and JSON for both owned collection endpoints and both named health routes.
The Grade 7 changes consist only of this assessment and its CPR README link.
Service source, submodule pins, Compose configuration and API payloads are
unchanged from the Grade 6 branch.
