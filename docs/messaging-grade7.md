# Lab 4 Grade 7: thread-per-request Broker and topic listing

**Status:** candidate. This page records the team baseline and the Broker
implementation proposed in Andreiisthebest/student-id-message-broker#20, which is not
merged, released or pinned. Grade 7 changes only the Message Broker.

Unchanged: business schemas, the HTTP catalog, the messaging catalog and envelope,
results, error codes, budgets, caller grants, Discovery, the Gateway and every
service's handlers, all as in [messaging-queues.md](messaging-queues.md). No service
needs a code change.

## Thread-per-request

- **Request threads:** every admitted business request runs on a new, dedicated OS
  thread, created for that request and ended with it. That covers routing,
  authentication, the Discovery lookup, queue admission, forwarding and waiting for the
  result.
- **Delivery threads:** every accepted delivery to one consumer group also runs on its
  own new thread.
- **No reuse:** there is no thread pool and no thread reuse.
- **Event loop:** the ASGI event loop only accepts connections and relays bytes.
  `/health`, `/health/ready` and `/status` stay on it, so a saturated Broker can still be
  diagnosed.

| Setting | Default | Meaning |
| --- | --- | --- |
| `BROKER_MAX_REQUEST_THREADS` | 512 | Live request threads; over it `429 TASK_LIMIT_REACHED` |
| `BROKER_LANE_THREADS` | 8 (max 64) | Concurrent delivery threads per `(topic or queue, group)`; replaces `BROKER_GROUP_WORKERS` |
| `BROKER_MAX_DELIVERY_THREADS` | 256 | Live delivery threads; an accepted delivery over a limit waits in its bounded lane, never refused |
| `BROKER_DISCOVERY_CACHE_MS` | 250 (0 disables) | One Discovery listing shared by all threads; dropped when the Broker evicts an instance |

- **Deadlines:** the existing queue, Discovery and delivery deadlines hold. The task
  deadline cancels a request's work inside its thread unless its response has started
  (a live SSE stream has its own lifetime).
- **Not force-stopped:** a Python thread ends once its cancelled work unwinds, bounded
  by its HTTP timeouts.
- **Ordering:** deliveries of one lane may complete in any order. Consumers already
  deduplicate by business id, and DMs' early DecisionRecorded is its recoverable
  `409 SESSION_CHAT_NOT_INITIALIZED`.
- **Observability:** `/status.threads` reports `{model, requests, deliveries}` with
  live, peak, started and limit. Log lines written on a Broker thread carry its `thread`
  name.

## Topic listing

`GET /internal/v1/messaging/topics[?kind=request|event]` on `BROKER_URL`, with any
authenticated Broker caller credential. The schema and a validated example are in
[topics.schema.json](../contracts/messaging/topics.schema.json).

- **What it lists:** every topic of the bundled, reviewed messaging catalog, sorted.
  Registration never creates a topic, and Gateway queues are not listed.
- **Request topics:** `operation`, the one group, `publishers` (the operation's
  callers) and `budgetMs`.
- **Event topics:** `eventType`, the required groups and the one publisher.
- **`canPublish`:** whether the authenticated caller may publish there.
- **`subscribers`:** per group, `{registered, ready}` from Discovery. If Discovery does
  not answer, they are `null` and `discovery` is `UNAVAILABLE`; the listing still
  answers 200.
- **Errors:** `401` without a valid caller credential; `400 INVALID_QUERY` for any other
  query parameter or `kind` value.
- **No sensitive data:** no instance addresses, credentials or bodies.

`python scripts/validate_messaging_contracts.py` checks that the example is valid and
that every listed topic agrees with the generated bindings.

## Evidence and limits

The candidate's evidence is in the Broker PR:
- 94 unit tests and 94% coverage;
- a local live run with the real Discovery and Gateway `dev`, Moderation and DMs, and
  labelled stand-ins for the other owners (21/21 checks);
- a burst of 52 concurrent requests in which every request and delivery ran on its own
  thread.

On that Windows run, the threaded Broker's median end-to-end latency for a
40-publication burst was 375 ms, against 235 ms for the async Broker. That is the cost
of per-thread setup under the GIL. Against a slow receiver, its parallel lanes
completed bursts the single-worker lanes could not.

Not yet done:
- a reviewed merge and the `lab4-0.5.0` release;
- Compose and image pins;
- Linux timings;
- verification with the real Session, Applicant, Credential and Rules.
