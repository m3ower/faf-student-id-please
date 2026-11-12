# Credential and Rules: Task 8 release and activation

Scope: CmMarin's two private services only. Vasile's Gateway cleanup, other
owners' service implementations and their delivery modes are not changed here.
The [merged gRPC contract](messaging-grpc.md) remains authoritative; this is an
operational checklist, not another protocol.

## Release artifacts

- Credential: `cmmarin/student-id-credential-service:lab4-1.1.0`, released by
  [private PR #49](https://github.com/CmMarin/student-id-credential-service/pull/49).
- Rules: `cmmarin/student-id-rules-service:lab4-1.1.0`, release tracked by
  [private PR #43](https://github.com/CmMarin/student-id-rules-service/pull/43).
- Broker gRPC release:
  [PR #26](https://github.com/Andreiisthebest/student-id-message-broker/pull/26),
  requiring the release-history CI fix in
  [PR #28](https://github.com/Andreiisthebest/student-id-message-broker/pull/28).

Verified public artifacts (12 November 2026):

| Owned service | Main source / image revision label | Pulled registry digest |
| --- | --- | --- |
| Credential | `ec6016ed8dc3d0a9f936382fda7fcbbfdcfeafb2` | `sha256:cc0ef68a3632768ef69c7c2d0d7a4cd36957709f46dec06c08d5cc970fb141fc` |
| Rules | `8d1ed489bdb2f2e22cd9d72dc2db416dbd20c77f` | `sha256:e5efb983211ffdf74b75372af6a753368d07888108dc0a7397303ea7acfe53a1` |

Both main publication workflows succeeded and both pulled images report
`org.opencontainers.image.version=lab4-1.1.0` and their matching source revision.

Release PRs and local images do not prove publication. Verify each tag's digest
and `org.opencontainers.image.revision` against its main merge commit. Do not
reuse the older published Broker `lab4-0.1.0-dev.84bd020c24e9`: it predates gRPC.
Discovery must also include the merged subscription/readiness implementation
(Discovery #39); the historical `lab3-0.7.0` image predates that change.

## Activation candidate

The [opt-in overlay](../docker-compose.owned-broker.yml) supplies both owned
images, business bindings and private Broker configuration on both replicas.
The overlay selects `BROKER_TRANSPORT=grpc`, `GRPC_ENABLED=true` on both owned
replicas and gRPC delivery for their two groups in the shared transport catalog.
It requires the matching Broker `lab4-0.6.3` release and published Discovery
`lab4-0.8.0`. The base Compose file and existing running stack are unchanged.

Broker `lab4-0.6.0` is published, but its bundled catalog still selects HTTP for
these groups. Merge the coordinated Broker activation PR and publish `lab4-0.6.3`
before deploying this overlay. Do not substitute the older image.

Populate a private environment using [.env.owned-broker.example](../.env.owned-broker.example).
Map `credential-service` and `rules-service` to their separate
`CREDENTIAL_BROKER_SERVICE_TOKEN` and `RULES_BROKER_SERVICE_TOKEN` values in
`BROKER_CALLER_TOKENS_JSON`. Receiver credentials must match each service and
Broker. Never reuse caller, receiver, management or Discovery credentials.

First validate without starting anything:

```powershell
docker compose --env-file .env.private -f docker-compose.yml -f docker-compose.owned-broker.yml --profile replicas config --quiet
```

Owned gRPC ports are 9080 and 9081 (HTTP port +1000), never published to the
host. The Broker is `message-broker:9093`. Registration and HTTP readiness stay
unchanged; Broker additionally requires fresh standard gRPC health for
`studentid.messaging.v1.MessageConsumer` before selecting a gRPC replica.

## Acceptance and activation gates

1. Publish and verify compatible Broker, Discovery and owned images.
2. In an isolated deployment, use the overlay's enabled gRPC listeners. Verify
   standard gRPC health, including
   NOT_SERVING after an actual dependency failure. Preserve the default stack.
3. Both owned publishers use `BROKER_TRANSPORT=grpc`. Verify actual
   owner applications, not stand-ins: Credential context/facts from Applicant
   and Record, both CredentialsReady processing receipts, Rules dependencies,
   Session bind/read and Moderation evaluation. Correlate each full path with
   the same trace. No Gateway/direct-service or HTTP fallback after RPC failure.
4. Verify deadlines, authenticated publisher/target identity, business-error
   compatibility, persistent replay and outage behavior. A Broker admission or
   acknowledged flag alone must never clear Credential's persisted outbox.
5. Only after that evidence, submit a reviewed flip of **credential-service**
   and **rules-service** in `contracts/proto/transports.json`, together with
   the identical Broker bundled copy and deployment selection. Other owners'
   existing modes must be preserved. Run real Broker-to-owned gRPC deliveries.
6. Remove obsolete owned internal HTTP callbacks in a separate follow-up
   release after the successful flip. Keep public REST, health and readiness.

This candidate includes the two-group flip, not HTTP callback removal. Local
Broker tests passed (113 tests, 91% coverage), and the shared contract compiles
and matches both private services. Isolated checks exercised real owned gRPC
health, Rules binding/replay and Broker delivery, but the complete cross-owner
business flow and both CredentialsReady receipts have not passed verification.
Further local tests were stopped before PR publication. This is not a claim of
full deployed Task 8 acceptance. Callback removal remains a separate follow-up
after successful activation, as required by the shared rollout order.
