# Postman — public Lab 4 requests

Import the root `*.postman_collection.json` files. Every public business request
uses Gateway `http://localhost:8090`; do not point it at a backend or Broker.
Use a private local environment for access/refresh tokens and generated IDs.
Never commit an exported environment containing secrets.

1. Complete the deployment prerequisites in the CPR README. A published Lab 4
   queue-capable Gateway and matching Broker transport catalog are required.
   The latest published Lab 3 Gateway is not that release.
2. Run Player registration/login first. Use the real access token for the player
   whose role the target collection requires.
3. Run Session Core to create/join a real session. Set that session's UUID in the
   collections that read session-scoped data. Host, member, junior, outsider and
   policy-admin cases require the corresponding actual identities/permissions.
4. Run Credential/Rules CRUD collections in order; preserve their generated IDs
   until cleanup. Applicant/Record operations require real initialization/session
   state. Optional Moderation/DMs/full-shift scenarios require initialized data
   and delivered events, not fixed fixture UUIDs or spoofed identity headers.

Internal service operations are not public REST endpoints. For gRPC diagnostics,
import `contracts/proto/studentid/messaging/v1/messaging.proto` into an authorized
private-network client and use MessageBroker Publish/GetResult with that caller's
own credential. Broker/consumer gRPC ports are not exposed to the host by Compose.
No player JWT substitutes for an internal caller credential.

`legacy/` preserves obsolete internal HTTP examples from Task 5. Do not include
them in the current public Collection Runner run or treat them as Task 8 tests.
Operational log requests use the separate operations endpoint/token, not Gateway
business routing. Keep explicit status assertions: 401/403/503 must not become a
false green for a positive business case. A collection run alone does not prove
Broker receipt semantics, full gameplay or deployment/image provenance.
