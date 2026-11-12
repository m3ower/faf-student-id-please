# Lab 4 Grade 8 (Task 8): service-to-service messaging over gRPC

This page and [`contracts/proto/studentid/messaging/v1/messaging.proto`](../contracts/proto/studentid/messaging/v1/messaging.proto) are the **single** gRPC contract.
- Earlier draft interfaces are discarded.
- Nobody creates a service-specific variant, a per-service proto fork or an extra interface (such as a `ProcessingResult`).

**What does not change:** everything in the Task 6 contract except the transport.
- Topics, groups, caller grants and budgets.
- The envelope fields, result states and receipt rules.
- Error codes.
- The JSON business schemas: each binding's `bodySchema` in [catalog.json](../contracts/messaging/catalog.json).

## 1. Shared protobuf interface

Every language generates its stubs from the one `messaging.proto`:
- `MessageBroker.Publish`
- `MessageBroker.GetResult`
- `MessageBroker.ListTopics`
- `MessageConsumer.Deliver`

**Pinned revision:** [`contracts/proto/transports.json`](../contracts/proto/transports.json) pins the revision as `protoSha256`, the SHA-256 of the proto text with LF line endings.
- Every vendored copy (the Broker's and each service's) must hash to it.
- Check one with `python scripts/validate_grpc_contract.py --vendored <path>`, or the same hash in the service's own test.
- Field numbers, enums, topic names and consumer groups never change in this migration.

## 2. Transport and addresses

| Leg | Transport |
| --- | --- |
| Service → Broker publications, results, topic listing | gRPC `MessageBroker` at `message-broker:9093` |
| Broker → service deliveries, operation and event topics | gRPC `MessageConsumer.Deliver`, **after that group's reviewed flip** in `transports.json`; HTTP until then |
| Gateway public queues and their delivery, public REST, Discovery, health and readiness checks, SSE, WebSocket | **HTTP, unchanged** |

**Receiver port:** the receiver listens on its registered HTTP port + 1000 (`grpcPortOffset`). Examples:
- containers on `8080` → `9080`;
- Credential `9080`;
- Rules `9081`.

**Host:** the Broker takes the host from the existing Discovery registration. There is no new gRPC address field, and the Broker dials no other address.

**No silent fallback:** a `grpc` group that does not answer is a failed delivery, counted by the circuit breaker exactly as HTTP is. The Broker never falls back to REST.

**Network:** for this lab, gRPC is plaintext and only on the private Docker network. Consumer gRPC ports are never published to the host. TLS deployment is outside this migration.

## 3. Authentication and identity

Metadata names, exactly:

```text
authorization: Bearer <credential>
x-service-name: <authenticated publishing service>
x-trace-id: <trace ID>
```

- **Publishers → Broker:** a publisher authenticates with its own caller credential. The Broker derives the publisher's identity from that credential and never trusts a supplied service name. The Gateway's credential is refused on gRPC, because its user queue stays HTTP.
- **Broker → consumers:** the Broker authenticates with the target service's internal credential, and sets `x-service-name` to the verified original publisher.
- **Consumers check:**
  - `x-service-name == Delivery.publisher`;
  - their own `group`;
  - an operation they own, its topic binding (`operation.<name>.v1` as `REQUEST`, or the catalog event topic as `EVENT`) and its permitted publisher.
- **Trace:** `x-trace-id` must equal the envelope's or delivery's `trace_id`.
- **Not service authentication:** player JWTs, the Discovery token and any client-supplied identity never stand in for it.

## 4. Deadlines and capacity

Deadlines use the native gRPC deadline **and** the shared absolute `deadline_at`.
- **Effective deadline:** the earliest of the incoming RPC deadline, `deadline_at`, and the existing local operation budget.
- **One budget:** queue waiting, processing, nested calls and polling all spend that same remaining budget.
- **Shorter limits stay:** for example Applicant and Record's 400 ms business budget, the Broker's 750 ms operation cap and the public 4 s.
- **Expired work:** it is refused before any business logic runs, with `DEADLINE_EXCEEDED` / `DEADLINE_EXCEEDED`.
- **Bounds:** concurrency and message sizes are bounded.
- **Cancellation:** a cancellation does not prove that a mutation was rolled back.

## 5. Direct business handling

`Deliver` calls the existing application function directly. There is **no REST loopback**.

It preserves:
- business validation and authorization;
- the exact business status and JSON body;
- persistent deduplication, immutable ids and outboxes;
- the existing initialization adapters and receipts.

**Inputs:**
- GET path and query values arrive in `Delivery.arguments`.
- A POST body arrives in `payload_json`, with its URI arguments kept separately in `arguments`.

## 6. JSON and reply compatibility

- **Empty, `null` and `{}` are not interchangeable:**
  - empty `payload_json` / `body_json` means **no body**;
  - JSON `null` is an explicit null;
  - `{}` is an empty object.
- **Valid JSON only:** it must be valid UTF-8 and one JSON document, with no duplicate keys and no non-finite numbers.
- **Size limits:** the Task 6 limits are enforced before processing.
  - Envelopes: 96 KiB.
  - Business bodies: 64 KiB.
  - Operation replies: 16 KiB.
- **Internal replies** carry status, JSON body and content type. Arbitrary HTTP headers are not part of this internal RPC. Public HTTP response-header behaviour is unchanged.

## 7. Business errors versus transport errors

**Business outcomes** are normal `Reply` messages, including business 4xx and 5xx.

**Transport failures** end the call with a gRPC status. These are authentication, malformed transport envelopes, unknown bindings, exhausted capacity and delivery failures. The trailers carry:

```text
error-code: <existing stable machine-readable code>
trace-id: <trace ID>
```

| HTTP-equivalent | gRPC |
| --- | --- |
| 400 | `INVALID_ARGUMENT` |
| 401 | `UNAUTHENTICATED` |
| 403 | `PERMISSION_DENIED` |
| 404 | `NOT_FOUND` |
| 409 | `ABORTED` |
| 413 / 429 | `RESOURCE_EXHAUSTED` |
| 500 | `INTERNAL` |
| 503 | `UNAVAILABLE` |
| 504 | `DEADLINE_EXCEEDED` |

**Failed deliveries:** the Broker turns a failed RPC delivery into the existing Task 6 failed-group status and error envelope. There is **no second result model and no `oneof`**. The transport `error-code` and the gRPC status are kept in sanitized error `details`.

**Circuit breaker:**
- Connection failures, timeouts and business 5xx keep the existing accounting.
- Ordinary business 4xx do not trip circuits.

## 8. Results and processing acknowledgments

**Overall states:**
- `PENDING`: at least one group is unfinished.
- `COMPLETED`: every required group is `SUCCEEDED` and acknowledged.
- `FAILED`: every group is terminal and at least one failed.

**Group results:**
- A pending group has no final status, body or headers.
- A terminal group carries its actual outcome.
- Readers reject unknown, missing or duplicate groups.

**Event receipts:** the Broker validates them independently. A receipt counts only with:
- HTTP-equivalent status 200;
- the matching business `eventId`;
- `PROCESSED` or `DUPLICATE`, or `accepted: true` for `CredentialsReady`.

**Publishers** keep their own receipt checks. Transport acceptance or `acknowledged = true` alone never clears an outbox.

**`GetResult`** is available only to the original authenticated publisher. A result missing after a restart or after retention means an **unknown delivery**, not a non-delivery.

## 9. Readiness

For a `grpc` group, HTTP readiness from Discovery is necessary but not sufficient.

**Broker:** before selecting a replica, it must hold a fresh successful standard gRPC health check (`grpc.health.v1.Health/Check`) for `studentid.messaging.v1.MessageConsumer` (`transports.json` `health`).
- Observations are bounded and cached for at most 5 s, and never beyond Discovery's readiness validity.
- Missing, failed or stale observations fail closed.
- Health checks never invoke business operations.

**Every consumer** serves that health service:
- `SERVING` only when its listener and required application dependencies are ready;
- `NOT_SERVING` during startup, after a dependency failure, and during shutdown.

## 10. Ownership

- **Shared contract (this PR):** these rules.
- **Broker owner:**
  - finish Task 7;
  - implement Andreiisthebest/student-id-message-broker#22 against this contract, including health selection, identity metadata, result validation and error mapping.
- **Each service owner:** generated clients, direct `Deliver` handlers and gRPC health, preserving existing business behaviour.
- **Marin:** Credential and Rules only.
- **Vasile:** the Gateway user-route allowlist cleanup.
- Nobody edits another owner's private service.

## 11. Rollout order

1. Merge Task 7.
2. Merge this finalized shared contract.
3. Merge and publish the Broker with HTTP and gRPC side by side.
4. Merge and publish each owner's compatible services.
5. Verify real cross-owner calls and event acknowledgments.
6. Flip each ready group independently in `transports.json`. Update the Broker's identical bundled copy and the deployment.
7. Remove that group's obsolete internal HTTP callbacks in a follow-up release.
8. Keep public REST, health and readiness, and the streaming endpoints.

**Task 8 is complete only when deployed gRPC communication actually works.** Proto generation, or tests with stand-ins, are not enough.

## Stubs and checks

- **Python (Broker):** `python -m grpc_tools.protoc -I contracts/proto --python_out=... --grpc_python_out=...`.
- **Java (Quarkus):** `quarkus-grpc` generates from `src/main/proto/`. Copy the file unchanged.
- **Go:** `protoc --go_out --go-grpc_out` with `--go_opt=Mmessaging.proto=<your package>`, and the same for `--go-grpc_opt`.

`scripts/validate_grpc_contract.py` checks:
- the proto compiles (in CI);
- it declares exactly these services and RPCs, with the agreed field names and numbers;
- the pin matches;
- `transports.json` covers exactly the catalog's consumer groups, with the agreed health settings;
- with `--broker-root` and `--vendored`, the copies match the pin.
