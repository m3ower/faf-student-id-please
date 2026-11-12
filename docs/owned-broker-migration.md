# Applicant and University Record: Message Broker migration

Tracked by [CPR issue #138](https://github.com/m3ower/faf-student-id-please/issues/138).
Application changes: [Applicant PR #25](https://github.com/Andreiisthebest/student-id-applicant-service/pull/25)
and [Record PR #27](https://github.com/Andreiisthebest/student-id-university-record-service/pull/27).
This is the owned migration candidate, not a claim that every team service or the
shared running deployment has been migrated.

## Transport and unchanged business protocol

All owned business clients now send their exact existing operation paths to
`BROKER_URL` using the service's distinct `BROKER_SERVICE_TOKEN`. This includes
initialization, full peer receipts, Credential status/recover and Record's Session
membership check. Missing broker configuration fails startup. No Gateway or
direct-peer fallback exists. Record requires/defaults `SESSION_CLIENT=broker`;
`gateway`, `mock` and `disabled` fail validation. Public player REST and verified
player identity still use Gateway; Discovery registration stays direct.

The single 39-operation [HTTP catalog](../contracts/http/service-operations.json),
its OpenAPI, schemas and golden vectors are unchanged. Full Applicant/Record
initialization remains session-bound with matching canonical hashes/receipts.
Credential keeps its separately adapted seed/status/callback protocol. Callback
receipts must commit and match causation; READY status alone never grants readiness.
Existing durable delivery stages, backoff/attempt bounds, idempotency, body limits,
caller allowlists and cancellation/deadline behavior remain. Existing data/pending
work stays in owned databases; no database migration of ownership occurs.

Broker catalog synchronization remains the teammate's [Broker issue #12](https://github.com/Andreiisthebest/student-id-message-broker/issues/12).
Their pushed source 00567a662c88e1489e35761c0506f63e92b8dadc bundles exactly the
current CPR catalog. This migration tests that candidate without modifying their
broker code/catalog or its two-review protection. Use the matching accepted image;
the earlier 31-operation image cannot route the new Credential compatibility ports.
No new queues/topics, load-balancing implementation, circuit-breaker implementation,
Gateway route deletion, architecture diagram or peer application changes are included.

## Configuration and rollout

Each owned service requires BROKER_URL/BROKER_SERVICE_TOKEN and its existing
separate receiver/management/DB settings. In Broker's BROKER_CALLER_TOKENS_JSON,
`applicant-service` and `university-record-service` must map to their own exact
caller secrets. APPLICANT_INTERNAL_TOKEN and RECORD_INTERNAL_TOKEN match the
respective receiver's SERVICE_INTERNAL_TOKEN. Credential/Session and any enabled
other target credentials must match their actual receivers. Secrets are distinct,
32-256 visible ASCII characters, delivered only through private configuration.
Never reuse a Discovery token or player JWT as a service credential.

[.env.owned-broker.example](../.env.owned-broker.example) lists blank configuration
keys. Add those values to a private copy of the base .env configuration. The
[opt-in overlay](../docker-compose.owned-broker.yml) selects explicitly supplied
migration images and introduces the private broker on default/applicant-net/record-net.
Both owned replicas inherit the new transport settings while retaining their
owned DB and direct registration configuration. It blanks the obsolete legacy
Gateway/direct business URL settings. No backend or broker business port is published.

The base Compose file, release image references and gitlinks are unchanged.
This overlay is an explicit candidate deployment, not a default deployment upgrade:

```powershell
docker compose --env-file .env.private -f docker-compose.yml -f docker-compose.owned-broker.yml config --quiet
# Only after selecting verified images and configuring all actual peer receivers:
docker compose --env-file .env.private -f docker-compose.yml -f docker-compose.owned-broker.yml up -d
```

Initialize primary DB schemas before starting optional replicas. Existing
scripts/scaled_stack.py uses the base Compose file only; do not use it to launch
this overlay implicitly. Keep actual Credential/Session peer configuration and
reviewed images aligned. Public Gateway receiver credentials are configured via
GATEWAY_TARGET_TOKENS_JSON; that is separate from Broker caller identities.
Additional peer target secrets in the overlay are optional and fail closed when
absent; only enable them with their actual receiver configuration.

No new images were published by this change. Do not pass old release/latest tags
as migration images. Build candidates from the exact source revisions or complete
the normal release process, then record pullable immutable digests/source labels.
Do not promote CPR pins/releases as proof of full-system acceptance before the
actual cross-owner business scenarios pass.

## Verification and evidence (2026-11-12)

- Applicant Java/PostgreSQL: 43 tests passed, 96.41% line coverage; >=70% gate passed.
- Record PostgreSQL race suite: passed, 80.8% instrumented-line /80.1% statement
  coverage; >=70% gate passed. Legacy-only Gateway settings/modes are rejected.
- Both existing Dockerfiles built successfully.
- 132 network checks passed against actual owned services, actual Broker and
  published real Discovery. The bundled catalog equals current CPR, with no mounted
  replacement or registry test double.
- Both initialization directions, matching hashes/receipts, private caller/session
  authorization, independent negative/contradictory truth, exact returned schemas,
  callback replay/conflicts, pending/ready profiles, restart and second-replica
  persistence passed. Broker logs prove actual round robin selects both Record replicas.
- New generation/delivery succeeds with Gateway stopped. Record fails closed on
  Broker outage despite an available Gateway, proving no fallback. Real membership
  denial/spoof/outage recovery still passes. Owned initialization traces go through
  Broker and never Gateway. Log scans found no credentials.
- The opt-in Compose configuration validates both replicas, image requirements,
  caller credentials, private ports and DB/registration inheritance without starting
  the shared stack. All disposable network resources were removed.

Exact local test artifacts (these local image IDs are not registry release digests):

| Component | Runtime source revision | Local image ID |
| --- | --- | --- |
| applicant | `bdbf79610eeb4683206265e5e06e900ed503238c` | `sha256:76324bdc30d711f35ad5dfcd823c8a5864fa8155b7afa3ab4fdd5e6945104fec` |
| record | `1d4ef70000808028fb57a282f9eb002228ea03f7` | `sha256:07f7e83fc2384249f9ccc1258de91d4d63d1093e125b1add20efc28761a7ef03` |
| gateway | `0a6d49649e0dd3610e206e8afc4ffbf76b34ba87` | `sha256:c80be656273ffee565a1cd14e9daaa7a7a5ea9dd5cd64b62c0ec5d8346e0a133` |
| broker | `00567a662c88e1489e35761c0506f63e92b8dadc` | `sha256:fe9e6d2174151d589b2be04c74a9cd2f1cd3777904781ed494a32ea4886cbe10` |
| discovery | `4993dd23b91636288893579dbd94d886cba62585` | `sha256:ad19c760fd6761375da31244d9b0461712a54df5381ebf3ce46b013796887a7a` |
| session | `historical membership image` | `sha256:f3ac52d0fb68368221dc120602b433e930785247575b11c5bc1751871222aa4e` |

Applicant's later 0346bbb commit extends only the test driver/docs; the tested
application artifact remains bdbf796. Reproduce from Applicant's
`scripts/verify_broker_integrations.py` and `docs/broker-migration.md` using the
exact current catalog and broker candidate. Output contains disposable credentials
and must be Git-ignored. The test-only Credential peer re-registers explicitly
after restart because it has no production registration worker; actual owned
services and replicas self-register. Random test ports are loopback-only.

Credential in this suite is an explicitly labelled protocol TEST DOUBLE under
Applicant test resources. It obtains real owned context/facts and persists its
synthetic callback jobs, but it does not prove production Credential document
validation/generation or real Rules evaluation. Session is the historical actual
membership image only, not current gameplay. Player JWTs are test-signed. Reports
retain fullSystemReady=false. Full current-peer acceptance remains outstanding.

The two separate owned Postman collections now send their owned internal folder
to `brokerBaseUrl` with Broker caller credentials. Run those calls from an authorized
private network test runner. Public collection requests keep Gateway baseUrl/player
JWT handling. The combined collection and architecture are unchanged. Tracked
credential values remain empty.

Applicant/Record retain required CI and other protections; mandatory approvals
remain disabled only there by owner instruction. CPR and Message Broker review
requirements are unchanged. No PR was self-merged or stable image published.
