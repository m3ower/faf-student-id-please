# Lab 4 configuration architecture

This diagram describes the Lab 4 Compose overlay and the shared messaging
contract. Use `docker-compose.yml` with `docker-compose.owned-broker.yml`.
The base alone retains the base-only configuration.

```mermaid
flowchart LR
    Client[Browser / Postman] -->|Public REST / SSE, player JWT| Gateway
    Gateway -->|HTTP subscriber queues, Gateway caller credential| Broker[Python Message Broker]
    Services[Eight business services] -->|gRPC Publish / GetResult, operation and event topics| Broker
    Broker -->|gRPC Deliver, target credential and verified publisher| Services
    Broker -->|Discover ready replicas| Discovery[Service Discovery]
    Services -->|HTTP registration, subscriptions and readiness| Discovery
    Services --> DB[(Owned PostgreSQL / Redis stores)]
    Gateway -->|Negotiate direct WebSocket| DMs[Discord DMs replicas]
    Client -->|Authenticated WebSocket| DMs
    Operator[Local operations client] -->|Separate bearer credential| Exporter[Host log-download endpoint]
    Exporter -->|Bounded docker compose logs| Logs[Logs from the exact Compose project]
```

Broker owns instance selection, round robin, circuit breaking, subscriber queues
and topic routing. Gateway authenticates public users and does not route internal
business APIs. DMs WebSocket traffic remains direct after negotiation; SSE remains
HTTP streaming. All gRPC ports and backend REST ports stay private, except the
browser-facing DMs WebSocket listeners. Receiver authorization remains mandatory.

The shared catalog selects gRPC for all eight consumer groups. Runtime compliance
requires compatible published images and a Broker bundling identical transport
choices. The inspected Broker source still differs for Credential/Rules; see the
[configuration review](lab4-configuration-review.md). The diagram does not claim
that deployment gates, durable Broker queues, dead letters, load-aware routing or
a monitoring stack have been implemented or verified.
