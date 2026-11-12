# Gateway â†’ Message Broker routing handoff

Candidate for review: [CPR #140](https://github.com/m3ower/faf-student-id-please/issues/140),
[Gateway #55](https://github.com/Vasiok11/student-id-gateway-service/issues/55),
[Broker #11](https://github.com/Andreiisthebest/student-id-message-broker/issues/11).
This document specifies the coordinated change; it does not claim deployment or
publication. Queues/topics, gRPC and durable Broker delivery are later tasks.

## Responsibilities and credentials

`Client â†’ Gateway â†’ Broker â†’ selected backend` handles public HTTP.
`Service â†’ Broker â†’ selected backend` handles business service calls.
Gateway validates Player JWTs, denies internal-only paths and binds `X-Player-Id`.
Broker owns Discovery lookup, round robin, backend circuits and removal for both
flows. Gateway keeps its task/stream limits; it has no backend selection or breaker
state and no direct/static backend fallback. Discovery control-plane traffic stays
direct from Broker and registered services.

Gateway requires `BROKER_URL` (credential-free reachable HTTP(S) origin) and
`BROKER_SERVICE_TOKEN`. Broker registers that value as `gateway-service` in
`BROKER_CALLER_TOKENS_JSON`. All caller/target credentials are distinct 32â€“256
visible ASCII characters, also distinct from Discovery's token. Secrets are runtime
configuration only. Gateway no longer needs `GATEWAY_SERVICE_TOKENS_JSON`,
`GATEWAY_TARGET_TOKENS_JSON`, service URL overrides or Discovery credentials.
Broker holds the existing target credentials named in the HTTP operation catalog.

## Public HTTP and identity

Gateway sends the same public method/path/raw query/body to Broker's `/api/v1/...`,
with its own caller bearer, validated `X-Trace-Id`, and verified `X-Player-Id` for
protected requests. The user's Authorization never reaches Broker or a backend.
Broker authenticates `gateway-service` before trusting identity. Other service
credentials and player JWTs grant no public-delivery permission. Protected delivery
requires exactly one nonzero UUID player identity. Anonymous register/login/refresh,
OPTIONS and named health relays omit player identity, while still authenticating
the Gateway hop. JWT validation remains exclusively at Gateway.

Broker independently enforces this fixed path ownership:

| Prefix after `/api/v1` | Canonical target |
| --- | --- |
| `players`, `teams` | `player-service` |
| `sessions` | `session-service` |
| `credentials` | `credential-service` |
| `rules` | `rules-service` |
| `applicants` | `applicant-service` |
| `records`, `university-records` | `university-record-service` |
| `decisions`, `penalty-policies` | `moderation-service` |
| `channels`, `messages` | `discord-dms-service` |

Broker replaces the Gateway bearer with the selected target's credential and sets
`X-Service-Name: gateway-service` and the trusted player identity. It strips spoofed
identity/credential and hop-by-hop headers. Existing receiver authorization and
business schemas are unchanged. No caller-supplied host, origin or target selector
is accepted. Unknown/private paths fail closed. Public `/api/v1/internal/...` is
not a callback transport. Gateway's old `/internal/v1/...` router is removed (404);
business callers use the Broker catalog and retain their own caller identities.

`GET /api/v1/health/{canonical-service}` is relayed through Broker to one selected
instance's `/health/ready`. Other methods/payloads/responses remain unchanged.
Public requests are bounded to 64 KiB; buffered replies to 1 MiB. Response status,
application headers, duplicate cookies, raw query encoding and HEAD semantics are
preserved. Redirects are relayed without following; redirects to a selected private
origin are rewritten to their public path. Shared error envelopes and trace
headers remain; target-owned errors are relayed unchanged.

## WebSocket and SSE

After JWT and playerId checks, Gateway sends
`GET /internal/v1/gateway/ws-target` to Broker with its caller bearer, trusted
`X-Player-Id` and trace. This dedicated operation allows only `gateway-service`;
Gateway's credential is excluded from every internal business-operation allowlist.
Broker chooses a registered DMs instance by its existing round-robin/circuit state:

```json
{"serviceName":"discord-dms-service","instanceId":"00000000-0000-0000-0000-000000000001","baseUrl":"http://discord-dms-service:8080"}
```

Gateway validates the reply and maps the exact private origin using its existing
`DMS_PUBLIC_WS_ORIGINS` setting. Every selected DMs replica needs an explicit
browser-reachable WS(S) origin. Missing/invalid mappings fail closed. Gateway then
constructs the existing direct DMs URL with sessionId, playerId and the original
JWT; Broker never receives that JWT. DMs validates its own direct handshake and
membership. Selection does not pretend a DMs HTTP/WebSocket call was made, and
existing sockets remain on their selected instance. A later reconnect negotiates
again; direct socket traffic does not pass through Broker.

Session SSE stays streaming over both HTTP hops. Handshakes use short request
deadlines; established streams use independent bounded capacity/lifetime. Both
relays close their selected upstream on disconnect/cancellation, including before
iteration. Mixed-case Content-Type works. Ordinary EOF, client cancellation and a
configured stream lifetime expiry do not count as backend faults; transport read
errors do. SSE reconnect gets the existing Session snapshot, not durable replay.

## Deadlines, admission and instance protection

Gateway defaults remain 5 s / 16 short tasks, 1800 s / 64 streams. Broker defaults
are 5 s outer tasks; 4 s public delivery (`BROKER_PUBLIC_TIMEOUT_SECONDS`), 750 ms
internal delivery (`BROKER_OPERATION_TIMEOUT_SECONDS`), and 1800 s / 64 streams
(`BROKER_STREAM_TIMEOUT_SECONDS`, `BROKER_MAX_STREAMS`). Keep public Broker delivery
below Gateway's task deadline and internal delivery below its caller's deadline.
Broker public requests, each catalog operation and target-selection requests have
independent bounded pools (`MAX_CONCURRENT_TASKS`, default 16 per pool/process),
so a parent cannot exhaust the pool needed by its own nested call. Local probes
remain independent of business saturation and task deadlines.

One shared circuit state per backend registration now aggregates all its public
and internal endpoints. **Clarification:** its rolling window is
`TASK_TIMEOUT_SECONDS * 3.5` (default 17.5 s), separate from shorter per-call
deadlines. Three 5xx, transport failures or timeouts trip it; successes retain
unexpired failures. One HTTP attempt contributes at most one failure. The current
request is not replayed after a reply/read timeout. Only failure to establish a
connection permits one alternate-instance attempt. Open circuits are skipped;
one half-open probe is admitted after cooldown. Caller cancellation releases a
probe reservation without creating a backend failure.

Removal stays Broker-owned, compares the failed registration with Discovery's
current UUID/address/timestamp, then DELETEs it. The existing unconditional
Discovery DELETE still has a check/delete race; atomic conditional deletion is
separate receiver work. No stronger guarantee is claimed by this handoff.

## Coordinated rollout

1. Review/release Broker with Gateway ingress and target credentials; preserve
   probe isolation from Broker #10.
2. Finish each service's `BROKER_URL`/caller-token migration. Preserve the 39-operation catalog and compatibility adapters merged by Gateway #54 and Broker #13; keep them in Broker rather than restoring Gateway routing.
3. Release Gateway with only the Broker caller credential, JWT public key and
   per-replica DMs public mappings. Retain a compatible previous image/config pair
   for rollback; never mix the new Gateway with a Broker lacking public ingress.
4. Update shared Compose, immutable images and gitlinks in a separate reviewed
   integration change. Keep all backend/Broker business ports private.
5. Verify real public CRUD, application-generated service calls, two replicas,
   mixed-endpoint breaker/eviction, direct WS selection and live SSE across hops.
   Fixture/double checks alone do not establish full-game readiness.
