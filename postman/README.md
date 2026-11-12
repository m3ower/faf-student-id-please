# Shared Postman collections

The eight `*-service.postman_collection.json` files are the editable service
collections. All were refreshed from shared `origin/dev` (`bdf7190`, fetched
2026-11-12), then checked and corrected locally. Import the individual files or
the generated `Student-ID-Please-Lab-1.postman_collection.json`. That historical
filename now contains all eight services and a whole-system log download.

Rebuild the combined file after editing a service collection:

```powershell
python scripts/build_shared_postman.py
python scripts/build_shared_postman.py --check
node tests/test_shared_postman.js
```

The shared file prefixes each service's variables, such as `applicant_accessToken`,
`university_record_managementToken`, `moderation_moderatorToken` and
`session_sessionId`. It also scopes variable access inside scripts, including
computed keys, without renaming business JSON fields. Only `baseUrl`,
`logDownloadUrl` and `logDownloadToken` are shared across services.

The historical two-service copy inside the initialized Applicant repository is
also refreshed. Use `--owned-copy` when generating/checking that copy together
with the shared collection. This edits the file in that service working tree;
service implementation and gitlink versions are not advanced by the generator.

Set secrets in a private Postman environment and never export populated tokens.
Player's login flow generates transient JWTs; Session's core flow creates real
accounts and session membership. Other service folders need their own actual
player/session/applicant prerequisites. Their input variables are deliberately
independent: copy values privately when testing the same live session across
folders. Historical fixed applicant and mock-membership IDs are not test setup.

Run folders independently. Optional shift, operations and Broker checks
need additional setup; running the entire combined file without that setup is
not a supported acceptance test. DMs event publication requires an actual
`shiftStartedEnvelope` for its `sessionId`; its duplicate check reuses that
business event with a new transport ID. Operations use the host exporter rather
than a public Gateway route. No durable-queue or dead-letter assertions are added
for APIs the Broker does not implement.

The HTTP collections cannot stand in for native gRPC publication checks. Import
the unchanged `messaging.proto` into a native gRPC request and follow
[Applicant/Record gRPC setup](README-owned.md). The same shared transport contract
applies to every service; its catalog is in `contracts/messaging/catalog.json`.
The current configuration and PDF compliance limits are recorded in
[the Lab 4 review](../docs/lab4-configuration-review.md).

The selected published Gateway returns 404 for unsupported method/path pairs.
Its current allowlist also omits Player logout. The Player collection names that
known 404 gap explicitly; it does not claim that logout/revocation succeeded.

Private source access was unavailable for Player, Session, Credential, Rules,
Moderation and DMs. Their collections match the latest shared exports plus the
local corrections; that is not proof they match unpublished private changes or
pass against a running deployment.

The obsolete Applicant/Record Task 5 adapters remain archived under `legacy/`
and are excluded from generated current collections.
