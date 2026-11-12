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

Release PRs and local images do not prove publication. Verify each tag's digest
and `org.opencontainers.image.revision` against its main merge commit. Do not
reuse the older published Broker `lab4-0.1.0-dev.84bd020c24e9`: it predates gRPC.
Discovery must also include the merged subscription/readiness implementation
(Discovery #39); the historical `lab3-0.7.0` image predates that change.

## Safe deployment preparation

The [opt-in overlay](../docker-compose.owned-broker.yml) supplies both owned
images, business bindings and private Broker configuration on both replicas.
Its defaults deliberately remain `BROKER_TRANSPORT=http`, `GRPC_ENABLED=false`.
The base Compose file and existing stack are unchanged.

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
2. In an isolated deployment, set `OWNED_CREDENTIAL_GRPC_ENABLED=true` and
   `OWNED_RULES_GRPC_ENABLED=true`. Verify standard gRPC health, including
   NOT_SERVING after an actual dependency failure. Preserve the default stack.
3. Set each owned `OWNED_*_BROKER_TRANSPORT=grpc` independently. Verify actual
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

No flip or callback removal is included in this preparation. Unit tests,
loopback gRPC/Broker doubles and a successful source release are not a claim
that deployed multi-owner Task 8 acceptance is complete.
