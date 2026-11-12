# Lab 4 Grade 8: service-to-service messaging over gRPC

**Goal:** service-to-service calls move from REST to gRPC, to reduce overhead. These are the legs that already go through the Message Broker:
- a service publishing to the Broker;
- the Broker delivering to the consumer group.

**Contract:** [`contracts/proto/studentid/messaging/v1/messaging.proto`](../contracts/proto/studentid/messaging/v1/messaging.proto). Java and Go generate their stubs from this one file; there are no hand copies.

**What does not change:** everything in the Task 6 contract except the transport.
- Topics, groups, caller grants and budgets.
- The envelope fields, result states and receipt rules.
- Error codes.
- The business JSON bodies: each binding's `bodySchema` in [catalog.json](../contracts/messaging/catalog.json).

## Scope

| Leg | Before | Grade 8 |
| --- | --- | --- |
| Service → Broker publication | `POST /internal/v1/messaging/publications` | `MessageBroker.Publish` |
| Service → Broker result | `GET /internal/v1/messaging/results/{id}` | `MessageBroker.GetResult` |
| Topic listing | `GET /internal/v1/messaging/topics` | `MessageBroker.ListTopics` |
| Broker → consumer, every operation and event topic | HTTP callback to the binding's `method` + `path` | `MessageConsumer.Deliver` |
| Gateway → Broker user queue, and its delivery to `/api/v1/...` | HTTP | **Unchanged.** It carries a user's HTTP request 1:1. The Gateway owner decides about the Gateway → Broker leg. |
| Service ↔ Discovery registration and readiness, Docker healthchecks | HTTP | **Unchanged.** Discovery observes `/health/ready` over HTTP. |

During migration the Broker serves REST and gRPC side by side, so no service has to switch on the same day as another.

## Addressing

- **Port:** a service's gRPC port is its registered `baseUrl` port + `grpcPortOffset` (1000), on the host it registered with Discovery. In containers that's `8080` → `9080`. The Broker's gRPC port is `9093`.
- **No Discovery change:** registrations stay as they are. The Broker dials only the registered host. No caller or registration supplies a gRPC address.
- **Delivery transport:** [`contracts/proto/transports.json`](../contracts/proto/transports.json) lists, per consumer group, whether the Broker delivers over `http` or `grpc`.
  - Every group starts on `http`.
  - Each owner flips their own group in a reviewed PR once their published image serves `Deliver`.
  - The Broker bundles a copy, checked by `--broker-root`.
- **No silent fallback:** a `grpc` group that does not answer is a failed delivery. It is counted by the circuit breaker and Discovery eviction exactly as HTTP is.

## Authentication

- Metadata `authorization: Bearer <token>` carries the same per-service credentials as the REST contract:
  - towards the Broker, the publisher's own Broker credential;
  - from the Broker, the receiving service's credential.
- There is no shared universal token, no Discovery-token reuse and no player JWT.
- A receiver that is called without its credential answers `UNAUTHENTICATED`. Plaintext gRPC (h2c) on the internal network matches the internal HTTP it replaces.

## Deadlines

- The Broker sets the gRPC deadline to the delivery's remaining budget: 750 ms at most per operation, with the public 4 s budget unchanged. Publishers set theirs to their own call deadline.
- `deadline_at` stays in `Envelope` and `Delivery` as the absolute UTC deadline, ending in `Z` or `+00:00`. Receivers check it exactly as they check `X-Deadline-At` today.
- A delivery whose `deadline_at` has already passed is refused with `DEADLINE_EXCEEDED` before any work starts.

## Errors and acknowledgments

**Business outcomes:** a handler's outcome, success or not, is a normal `Reply{status, body_json, content_type}`. It carries the same status and JSON body that the HTTP binding returns today (for example 404 `APPLICANT_NOT_FOUND`), so results look identical to publishers.

**Other failures:** authentication, authorization, a malformed message, an unknown operation, an expired deadline or capacity end the call with a gRPC status. The trailing metadata carries the existing error code as `error-code`, and `trace-id`. This uses the README's error table:

| HTTP | gRPC |
| --- | --- |
| 400 | `INVALID_ARGUMENT` |
| 401 | `UNAUTHENTICATED` |
| 403 | `PERMISSION_DENIED` |
| 404 | `NOT_FOUND` |
| 409 | `ABORTED` |
| 413, 429 | `RESOURCE_EXHAUSTED` |
| 500 | `INTERNAL` |
| 503 | `UNAVAILABLE` |
| 504 | `DEADLINE_EXCEEDED` |

**Broker refusals:** when the Broker refuses a `Publish` (for example `CALLER_NOT_ALLOWED`, `TOPIC_NOT_FOUND` or `MESSAGE_CAPACITY_REACHED`), the publisher sees that gRPC status and code.

**Failed deliveries:** when a consumer's `Deliver` ends with a gRPC status, the Broker records that group as `FAILED`. It uses the HTTP status from the table and an error body with the code, so the result schema is unchanged.

**Event receipts:** the rule is unchanged. The reply must have status 200 and the same `eventId`, with status `PROCESSED` or `DUPLICATE` (`accepted: true` for CredentialsReady). Anything else is a failed delivery.

## Receiver duties

Every service that receives topics:
1. Serves `MessageConsumer` on HTTP port + 1000.
2. Authenticates the metadata against its own Broker-facing credential.
3. Accepts only `group` = its own service name and an `operation` it owns in the catalog, and checks the topic matches that binding.
4. Calls the same handler as its HTTP binding, with the delivery's `arguments` and `payload_json`, and returns that handler's `Reply`. Deduplication, outboxes and idempotency stay where they are.
5. Logs `trace_id`, `message_id`, `correlation_id`, `causation_id` and `operation`, the same fields as today. It never logs tokens or bodies.
6. Keeps its HTTP callback routes until its group's flip is merged, then removes them.

## Publisher duties

1. Publishes with `MessageBroker.Publish` to `BROKER_GRPC_TARGET` (`message-broker:9093`), with the same envelope, ids, deadline and causation as today.
2. A request topic returns the terminal `Result`, or `PENDING` to be polled with `GetResult`. An event returns `PENDING`.
3. Keeps the existing receipt checks and outbox retries.

## Stubs

- **Python (Broker):** `python -m grpc_tools.protoc -I contracts/proto --python_out=... --grpc_python_out=...`.
- **Java (Quarkus):** `quarkus-grpc` generates from `src/main/proto/`. Copy the file unchanged.
- **Go:** `protoc --go_out --go-grpc_out` with `--go_opt=Mstudentid/messaging/v1/messaging.proto=<your package>` and the same for `--go-grpc_opt`.

`scripts/validate_grpc_contract.py` keeps the contract coherent:
- the proto compiles, when `grpcio-tools` is present, as it is in CI;
- it declares both services and their RPCs;
- `transports.json` covers exactly the catalog's consumer groups;
- with `--broker-root`, the Broker's bundled copies are identical.

## Out of scope

- TLS between services.
- gRPC for Discovery.
- Streaming RPCs.
- Typed per-operation protobuf messages.

The business bodies stay the reviewed JSON schemas. A later version can type them one operation at a time without changing this envelope.
