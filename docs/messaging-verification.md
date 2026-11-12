# Shared Task 6 candidate verification

Local source verification, 2026-11-12. These results describe feature candidates,
not released versions, published image tags or a fully adopted team deployment.

| Repository | Branch | Inspected remote dev base |
| --- | --- | --- |
| CPR | feature/contract-messaging-bindings | 38df07dce26df7112d1a4386f4154aec134c8895 |
| Gateway | feature/gateway-subscriber-queues | e6cc55efdc05bccef8cbe8618d0b8a321a43c072 |
| Broker | feature/broker-topic-queues | 6b44c6516d25ed9bf88288c623c995ddea65fabc |
| Discovery | feature/discovery-subscriptions | 0f4c538f2b5d6eab6c128cd251c959b8e7872a39 |

Remote dev refs were rechecked after implementation and had not advanced.

- Gateway: 210 tests, 96.66% application coverage; threshold 70% passed.
- Discovery: 195 tests, 96.99% application coverage; threshold 70% passed.
- Broker: 79 tests, about 92.6% application coverage; threshold 70% passed. The
  same 79 tests also passed inside the actual Python 3.12 runtime image using a
  read-only test mount; native coverage used Python 3.14.
- Broker's five repository-policy regression tests and Discovery's shell
  repository/PR-policy checks passed. Protections and rulesets are unchanged.
- CPR messaging validator: six tests and 79% coverage. It verifies 39 operation
  projections, five event bindings, eight queues, generated owner subscriptions
  and concrete examples against existing business schemas. Existing HTTP catalog
  and 39 examples validate; no business schemas or receiver caller grants changed.
- All three local Docker candidate images built and started as UID 10001 with
  read-only filesystems. Readiness/status/version checks passed. The Broker image
  includes both required catalogs and safely refuses unconfigured messaging.

## Real-network reproduction

Use the Gateway development Python with its pinned dependencies installed:

```powershell
python scripts/validate_messaging_contracts.py --broker-root /path/to/services/message-broker
python -m unittest tests.test_http_contracts tests.test_messaging_contracts -v
python scripts/verify_messaging_shared.py --services-root /path/to/services
```

The last command starts new loopback Discovery/Broker/Gateway processes and
explicit test receivers (two Session replicas, two DMs replicas, one Player).
It creates no database, shared stack, production data or external deployment.
Secrets/private signing material exist only in memory; temporary process logs
are deleted. Processes/servers are stopped in finally blocks. Output is assertion
results and sanitized receiver trace/operation metadata in docs-local.

All 20 real-network assertions passed: authenticated registrations and independent
fresh readiness, public queue delivery, nested Session-to-Player topic reply,
two competing replicas, trusted trace/message/deadline metadata, event 202 followed
by two matching group acknowledgments, one delivery per group, transport replay
deduplication/conflicts, private result ownership, partial DMs 409 with successful
Session acknowledgment, mixed-case SSE after six seconds, unready subscriber
rejection, result loss on Broker restart and successful new requests afterward.

These receivers are deliberately test fixtures. This proves shared transport,
not actual owners' new topic clients, durable business dedup/outbox behavior,
full-shift progression, direct browser WebSocket authorization, multi-owner
schema compatibility or full-stack acceptance. Those remain individual adoption
and later deployment checks. Compose, image pins, existing Player/Session work
and other teammates' private source are untouched.
