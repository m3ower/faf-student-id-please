# Player and Session: published Lab 4 deployment

Use the existing `docker-compose.owned-broker.yml` together with
`docker-compose.yml`. The overlay selects the new releases on both replicas;
the base file retains the historical Lab 3 deployment.

## Published owned images

| Service | Image | Matching main revision |
| --- | --- | --- |
| Player | `vasiok11/student-id-player-service:lab4-1.3.0-build.31` | `343eac9d3dd117ba0b7c9286c6a18dcd94fbd835` |
| Session | `vasiok11/student-id-session-service:lab4-1.3.0-build.37` | `28d9a794e40cbd5db87cdef3556032a9ef4f9bef` |

Publication, matching source/version labels, and matching `latest` digests were
verified on 12 November 2026. CPR's two owned gitlinks select these revisions.

## Shared release prerequisites

Fill `OWNED_GATEWAY_IMAGE` and `OWNED_DISCOVERY_IMAGE` with
verified **published** compatible releases. Their blank example values are
deliberate: the overlay fails validation instead of selecting historical images.

- Broker is pinned to published `andreiisthebest/student-id-message-broker:lab4-0.6.0`.
  Its publication succeeded during this verification. The source label matches
  main `6e5c2327dae01e914c04d303bd76013eefa02da3`, version label is `0.6.0`, and
  its versioned/`latest` digest is
  `sha256:29c9bdef6f6af8ff45c0b97d40dcc8d9ab0384ba8b4c2e78f702a5d11e7f4c71`.
  It serves topics/queues and `MessageBroker` on private port 9093. Keep the
  reviewed `OWNED_BROKER_IMAGE` override when selecting a newer release.
- Gateway needs subscriber-queue forwarding from its Lab 4 dev source, including
  the existing authenticated `POST /api/v1/players/logout` route. The missing
  allowlist entry is tracked in [Gateway #61](https://github.com/Vasiok11/student-id-gateway-service/issues/61).
  Its release is deferred until the remaining shared work is ready.
- Discovery needs the merged subscription/readiness implementation from #39.
  Its published `lab3-0.7.0` image predates that implementation.

No delivery modes in `contracts/proto/transports.json` or Broker's bundled copy
are changed here. Incoming deliveries remain HTTP until each group's reviewed
flip; Player/Session publish to Broker over gRPC. Full cross-owner and multi-group
acceptance remains part of that coordinated rollout.

## Private environment

Keep existing local credentials. Add the relevant entries from
`.env.owned-broker.example` to the ignored `.env`; do not overwrite an existing
`.env` with the example or commit populated secrets.

- `PLAYER_JWT_PRIVATE_KEY_B64`: base64 of a PKCS#8 PEM RSA private key, 2048+ bits.
  `GATEWAY_JWT_PUBLIC_KEY_B64` must contain the corresponding public key. Both
  Player replicas share the signing key.
- `PLAYER_INTERNAL_TOKEN`, `SESSION_INTERNAL_TOKEN`: separate receiver secrets,
  matching the values supplied to Broker.
- `GATEWAY_BROKER_SERVICE_TOKEN`, `PLAYER_BROKER_SERVICE_TOKEN` and
  `SESSION_BROKER_SERVICE_TOKEN`: separate caller secrets. Map their exact values
  to `gateway-service`, `player-service`, `session-service` respectively in
  `BROKER_CALLER_TOKENS_JSON`, retaining every actual peer caller.
- All caller/receiver secrets are distinct 32–256 visible ASCII characters,
  separate from Discovery and other owners' management credentials. Generate real
  values locally; the examples contain no deployment secrets.

Gateway uses Broker's HTTP subscriber ingress at `http://message-broker:8093`.
Player/Session use `BROKER_GRPC_TARGET=message-broker:9093`. Consumer port 9080
stays private; public Postman requests continue through Gateway at port 8090.
Inherited database settings and each replica's unique advertised HTTP address
remain in place. The legacy Gateway target-token map is no longer required.

Validate without starting or changing a stack:

```powershell
docker compose --env-file .env -f docker-compose.yml -f docker-compose.owned-broker.yml --profile replicas config --quiet
```

For isolated verification, choose a new Compose project. Start shared components
and the two primary owned services, wait for registration and readiness, then
start `player-service-2` and `session-service-2`. This avoids racing cold-start
database initialization. Other owners keep their own startup/migration checks.

## Postman and verification

Import only `player-service.postman_collection.json` and
`session-service.postman_collection.json` for this owner's checks. Their requests,
real login token handling and default `http://localhost:8090` already match the
public API. Run Player in order; run Session's **Core CRUD and access** folder.
The optional shift folder requires the real external Rules/Applicant/DMs/
Moderation workflow and is not a standalone owned-service acceptance check.

The actual merged Compose model passed validation with disposable synthetic
configuration, including missing shared-image gates. All 12 primary/replica
configurations belonging to the other six services remain identical.
A temporary stack used the published Player, Session and Broker images and
unmodified local candidates for Gateway `59b1f8b` and Discovery `97369bb`,
with two replicas of each owned service:

- All four replicas registered and standard gRPC health reported `SERVING`.
- Session Core: 17 requests, 19 assertions, all passed through Gateway/Broker.
- Player: 13 requests, 22/23 assertions passed. The sole failure was the known
  Gateway logout omission: expected 204, received 404. The collection correctly
  retains that assertion; its public API has not changed.
- All 57 CPR contract tests passed. Test containers, volumes and ephemeral
  credentials were removed. Existing deployments were not restarted.

One earlier fresh-stack run timed out waiting for primary registration; a clean
rerun with the same configuration passed. The cause was not established before
that disposable stack was removed. Registration retries remain bounded, with no
heartbeat or automatic re-registration; the successful run does not prove
automatic recovery from a missed startup registration.

This is configuration/local verification evidence, not a claim that the missing
shared images are published or that the entire team's optional shift flow passed.
