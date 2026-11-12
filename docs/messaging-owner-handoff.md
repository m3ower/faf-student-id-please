# Individual service adoption after shared Task 6

Shared candidate: CPR #145 / Discovery #38 / Broker #15 / Gateway #57. Do not
claim release/full integration until those PRs and your service PRs are merged,
published and tested together. Start from current remote dev on a feature branch;
follow your issue/PR/test rules and preserve unrelated local work.

Implement only your own services. Read `docs/messaging-queues.md`, the reviewed
HTTP business catalog, messaging schemas/examples and the exact arrays in
`contracts/messaging/subscriptions.json` before coding.

1. Register your generated operation and event subscriptions at listener startup.
   Preserve stable per-process UUIDs, distinct replica origins, direct authenticated
   Discovery registration, disabled mode, bounded retries and shutdown cancellation.
   Registration is not topic authorization; do not invent target/group names.
2. Replace outbound business HTTP-to-Broker paths with authenticated
   `POST /internal/v1/messaging/publications` at the same BROKER_URL. Use operation
   topics for request/reply; GET URI fields become payload, POST URI fields become
   arguments and POST JSON stays unchanged. No target URL or Gateway fallback.
   Unwrap the group's exact business status/body before existing validation.
3. Publish true events using their fixed event topics, preserving the complete
   business envelope, immutable hashes/IDs and owner-managed outboxes. Retain
   separate full vs seed initialization operation adapters. Never publish an
   initialization loop or treat Broker 202 as a processing receipt.
4. Poll authenticated results, checking correlationId/messageId and every required
   group's persisted acknowledgment. Keep your existing strict receipts; partial
   fan-out must not clear the overall outbox. Transport results are volatile:
   404/timeout/restart is ambiguous. Reconcile/retry with the same business IDs,
   new transport IDs/deadlines after known failure/expiry, and persistent consumer
   deduplication. No blanket replay of ambiguous writes. Preserve DMs' recoverable
   409 SESSION_CHAT_NOT_INITIALIZED and Credential's readiness handshake.
5. Honor trusted Broker X-Deadline-At and propagate remaining time into nested
   envelopes; retain shorter existing 400ms/1s budgets. Do not let queue waits or
   result polling reset deadlines. Preserve traceId; log IDs/status without
   credentials/bodies. Keep target bearer + X-Service-Name authorization unchanged.
6. Tests: permitted/forbidden callers, unknown topic, required subscription missing,
   stale/not-ready instance, two replicas competing in a group, multi-group fan-out,
   exact ACK and mismatch/202 rejection, partial failure, duplicate/conflicting
   business IDs, saturation, queued deadline, cancellation, Broker restart/result
   loss and a real nested call. Use isolated data/containers. Show durable outbox
   recovery where your service already owns it. Health checks alone are not proof.
7. Send back PR links, exact release image/digest/source revision, emitted topics,
   registered subscriptions, preserved budgets and sanitized end-to-end trace
   evidence. Full team acceptance and Compose/image pin promotion follow separately.

| Owner | Generated receiving operations + event groups |
| --- | --- |
| Vasile: Player / Session | Player: 3 operations + SessionCompleted; Session: 5 operations + DecisionRecorded + PlayerProgressed |
| Andrei: Applicant / Record | Applicant: 11 operations + CredentialsReady; Record: 8 operations + CredentialsReady |
| Marin: Credential / Rules | Credential: 6 operations; Rules: 3 operations |
| Andreea: Moderation / DMs | Moderation: 1 operation; DMs: 2 operations + ShiftStarted + DecisionRecorded |

Event topics are not the same as operation topics that deliver an event-shaped
body. Keep both receiving subscriptions during the transition, but producers
must not send the same business action down both paths as separate effects.
Existing public HTTP endpoints, SSE and direct DMs WebSocket frames stay intact.
No live gRPC, broker persistence or new production business API is required by
this shared task.
