# Owned Task 5: move service-to-service HTTP to Broker

Issues: Credential #41, Rules #35, Broker #12, CPR #137.

Credential and Rules now require BROKER_URL/BROKER_SERVICE_TOKEN for all outbound
business operations, including Session authorization. No legacy Gateway or direct
service fallback exists. Public clients still enter Gateway; Discovery registration
is direct control-plane traffic. Receiver tokens and original caller identities,
payloads, deadlines, replay and error handling are unchanged.

Credential routes membership, Applicant context, Record facts and ready callbacks.
Rules routes membership, Session state, Applicant profile, Record facts, Credential
validation and Moderation history. Broker bundles the same merged39-operation
catalog as CPR/Gateway; this enables previously missing owned compatibility routes.
No routing selection/circuit code is changed: that Task5 subtask is owned elsewhere.

## Configuration and rollout

1. Use reviewed matching candidate service images and a Broker build with the
   39-operation catalog. Do not substitute old published Lab3 images as proof.
2. Privately register distinct credential-service/rules-service caller tokens in
   BROKER_CALLER_TOKENS_JSON. Set each service's BROKER_SERVICE_TOKEN accordingly.
3. Configure Broker's target credentials for each receiving service, plus its
   existing Discovery settings. Keep targets private. Never reuse Discovery,
   receiver or player credentials as caller secrets.
4. Set BROKER_URL=http://message-broker:8093 on the shared network (host-run example:
   http://localhost:8093). Private service Compose/examples now require these names.
   Shared stable Compose/pins/secret files are deliberately not promoted here.
5. Run actual private-peer acceptance and trace-correlated requests after deployment.
   A Broker outage must fail closed, not fall back to Gateway or fixture success.

The user explicitly accepted provisional source/contract compatibility for this
migration. Earlier network-peer/database tests are not retrospectively relabelled
as real-owner acceptance. That full-stack gate remains required for lab sign-off.

## Local verification

- Credential:73 tests, no failures/errors/skips;94.78% line coverage, disposable PostgreSQL.
- Rules:full PostgreSQL suite passed;84.1% total /89.4% rules-package statement coverage.
- Broker:43 tests,95.81% application coverage. The new relay test exercises14 owned
  request directions, credential replacement, caller/trace/body preservation and
  denial of Rules access to Credential-only context using explicit target peers.
- CPR:43 tests and39 operation/example pairs validate; Broker's bundled catalog
  is byte-identical to the merged CPR catalog.
- Missing Broker settings and Broker outages do not use otherwise valid legacy
  Gateway settings. No Gateway destination configuration remains in owned runtime
  client code. Public inbound Gateway authentication remains intentionally present.

These are local source tests, not a deployed-image or real private-peer acceptance
claim. Tests ran before PR publication. No image publication, shared deployment/pin
promotion or load-balancing/circuit-breaker change is included. Temporary test DB removed.

## Grade 6 ownership (from PAD_LAB_4_V1.pdf)

Grade6 is shared infrastructure **and** per-service work. Broker must implement
subscriber-based queues for Gateway-to-Service communication, where Gateway knows
the target, and topic-based queues for Service-to-Service communication, where
publishers do not know interested consumers. Discovery registration must include
the topics each service is interested in. Gateway/Broker/Discovery changes are
shared; each owner adapts their producers/consumers and registration. Agree topic
names, payloads and queue semantics together before individual implementation.
None of those Grade6 queues is implemented or claimed by this Task5 HTTP migration.
