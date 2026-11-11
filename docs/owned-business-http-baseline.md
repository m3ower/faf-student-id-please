# Owned business HTTP baseline — candidate, not integration-ready

Latest status: [team contract reconciliation](owned-contract-reconciliation.md).
CPR #129 is now merged and supplies the canonical list, validation, evaluation
and Moderation history contracts. Applicant/Record #126 remains draft; its full
initialization protocol is incompatible with the earlier owned workflow below.
Treat this page's earlier consumer proposals as historical candidates, not agreed
peer contracts or proof of Task 5 completion. Latest dev #132 now imports exact
Applicant/Record schemas and Session state/Rules binding contracts; the remaining
work is owned implementation alignment, not waiting for those schemas to exist.

Tracks [CPR #123](https://github.com/m3ower/faf-student-id-please/issues/123),
[Credential #31](https://github.com/CmMarin/student-id-credential-service/issues/31)
and [Rules #27](https://github.com/CmMarin/student-id-rules-service/issues/27).

This is an **incomplete implementation candidate**, not completion of the
production-baseline prompt. Candidate [CPR #122](https://github.com/m3ower/faf-student-id-please/pull/122)
and [Gateway #48](https://github.com/Vasiok11/student-id-gateway-service/pull/48)
have now merged (CPR dev `3fca798`). The latter permits only Record and DMs as
membership callers. Record #22 is inaccessible to this account. No private owner
package was supplied. Applicant/context/Record-facts/Session-ruleset response
schemas remain unresolved; Moderation history is now specified by merged #129.
Do not invent the unresolved operations or claim their acceptance.

## Implemented in the owned candidate sources

- Removed CredentialMock/CredentialContracts and Rules ContractFixtures from
  production artifacts. Legacy fixture tests keep test-only source; there is no
  fixture bean, runtime fixture selector or network fallback.
- Credential applicant-document reads and Rules current-rules reads now perform
  real `POST /internal/v1/session-memberships/verify` calls **through Gateway**,
  using the exact candidate membership schema from #122.
- A nonblank session string no longer grants access. Session/player identifiers
  must be UUIDs; a valid negative membership result denies before business data
  is read. Non-200, missing/malformed fields, unknown roles, transport failures,
  oversized replies and deadlines fail closed with 503, not fabricated success.
- Each caller has its own `GATEWAY_SERVICE_TOKEN`; it is distinct from that
  receiver's target token and from Discovery's credential. No ambient proxy,
  redirect or automatic retry is used. Replies are bounded to 16 KiB.
- UUID `X-Trace-Id` propagates into the membership request. The maximum caller
  budget is one second; Credential reserves 100 ms when its parent task has the
  minimum one-second timeout. Rules bounds its call by the parent context.

Production startup requires `GATEWAY_URL`, the service's private
`GATEWAY_SERVICE_TOKEN`, and `CREDENTIAL_INTERNAL_TOKEN` / `RULES_INTERNAL_TOKEN`.
Only origins are accepted, never a caller-supplied forwarding URL. Environment
files or secret values must not be committed. Direct Discovery traffic is unchanged.

## Receiver security extension requiring Gateway-owner review

The protected public-read backend handler requires:

```http
Authorization: Bearer <OWNED_RECEIVER_TARGET_SECRET>
X-Service-Name: gateway-service
X-Player-Id: <VERIFIED_USER_SUBJECT_UUID>
X-Session-Id: <SESSION_UUID>                         # Credential applicant read
X-Trace-Id: <UUID>
```

Rules takes `sessionId` from its existing query parameter instead of X-Session-Id.
Gateway must authenticate the public JWT, strip untrusted identity/service headers,
bind X-Player-Id to its subject and supply the receiver-specific target credential.
Clients never receive that target credential. An X-Player-Id header alone is not
trusted. Missing/bad target credentials return 401, a non-Gateway caller returns
403, invalid identifiers return 400, negative membership returns 403
SESSION_ACCESS_DENIED, and failed dependency authorization returns 503
SESSION_SERVICE_UNAVAILABLE. These are candidate access/behavior changes, not a
silent claim of compatibility with the released Gateway.

Gateway #48 does **not** yet implement these two target-token/public-route
extensions or allow Credential/Rules to invoke membership. Request explicit
owner changes and coordinated review before merging or deploying the callers.
The released stack/image pins are unchanged by this work. Do not deploy candidate
callers alone: they intentionally refuse unsecured reads, or fail startup without
required configuration.

Catalog: [service-operations.json](../contracts/http/service-operations.json).
OpenAPI: [openapi.json](../contracts/http/openapi.json).
This is the team's single canonical catalog. Earlier owned extensions remain
explicitly unapproved metadata under `ownedDrafts`, not Gateway routing entries.
Existing GET reads have no durable write effects and no retry; none of this
implements initialization idempotency or callbacks.

## Additional owned receiving operations (not yet Gateway-routed)

The same shared catalog/OpenAPI now specifies these exact backend operations;
the receiving owners are us. These are implemented, not guessed peer routes:

| Operation | Authenticated service callers | Behavior |
| --- | --- | --- |
| `GET /internal/v1/credentials/applicants/{applicantId}` | Applicant, Moderation, Rules | Reads actual stored documents; no generation on a miss. |
| `GET /internal/v1/credentials/{credentialId}/checks` | Moderation, Rules | Checks stored structure, expiry (UTC) and future issue date. Authenticity is explicitly `UNVERIFIED`, not fabricated true/false. |
| `POST /internal/v1/rulesets/bind` | Session only | Persists active full rules and version for a session/shift, correlated by eventId. |
| `GET /internal/v1/rulesets/sessions/{sessionId}/shifts/{shiftId}` | Session, Moderation | Reads that immutable binding, never silently uses newer rules. |

All four require Gateway's receiver-specific target Bearer credential plus its
authenticated service caller header. Gateway must explicitly register their
caller allowlists and replace credentials; a user JWT is not service authority.
Do not route `/internal/` with a generic prefix proxy or publish backend ports.

Binding writes lock the Rules version row before reading active rules; rule
CRUD takes that lock before mutation too. Identical eventId/sessionId/shiftId
replays the original stored result even after rule rotation/deletion. Reusing an
event for different identifiers or rebinding a shift with a different event is
409. The PostgreSQL table survives process restart and is shared by replicas.
It stores no applicant/Record truth and sends no remote callbacks.

Generation, authoritative validation consumers, initialization/outbox recovery
and ID-based evaluation are now implemented too; see
[the current handoff](owned-task5-readiness.md). Their real HTTP adapters use the
shared catalog `ownedDrafts.consumerPorts`. No peer path is guessed: deployment bindings
must map those ports to receiver-reviewed internal POST operations on Gateway.
Session must adopt bind/read and readiness, and peers must agree the port schemas.

## Still missing before the full goal can be fulfilled

1. Receiver-owned agreement on Applicant context, internal Record facts, Session ruleset/shift
   context, moderation-history and initialization callback contracts, including
   method/path, schemas, credentials, allowlists, budgets and idempotency rules.
   Public junior Record access must not be impersonated for internal fact reads.
2. Session adoption of persisted shift snapshots and coordinated readiness,
   including explicit recovery of pending initializations and durable callback
   deduplication. Rules' provider reads history only; it never submits decisions.
3. Gateway registry/allowlist and target-credential changes, real peer services,
   then database-backed multi-service success/denial/spoofing/outage/recovery and
   second-replica/restart/duplicate initialization acceptance.

The candidate intentionally retires public caller-facts evaluation with
`410 CALLER_FACTS_RETIRED`, replacing it with service-only ID-based evaluation.
This is a breaking contract change requiring coordinated review/versioning
before release, not an additive change to silently deploy on existing clients.

The catalog deliberately does not assign guessed peer paths. Keep reviewable
candidate PRs draft until these coordinated prerequisites are resolved. Do not
merge or publish a stable release, migrate broker transport, edit the architecture
diagram, or change Discovery merely to produce artificial business calls.
