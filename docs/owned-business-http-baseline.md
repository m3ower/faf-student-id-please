# Owned business HTTP baseline — candidate, not integration-ready

Tracks [CPR #123](https://github.com/m3ower/faf-student-id-please/issues/123),
[Credential #31](https://github.com/CmMarin/student-id-credential-service/issues/31)
and [Rules #27](https://github.com/CmMarin/student-id-rules-service/issues/27).

This is an **incomplete first implementation slice**, not completion of the
production-baseline prompt. Candidate [CPR #122](https://github.com/m3ower/faf-student-id-please/pull/122)
and [Gateway #48](https://github.com/Vasiok11/student-id-gateway-service/pull/48)
are open, not merged. The latter currently permits only Record and DMs as
membership callers. Record #22 is inaccessible to this account. No private owner
package or canonical Applicant/context/Record-facts/Session-ruleset/history HTTP
catalog was supplied. Do not invent those operations or claim their acceptance.

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

Catalog: [operations.json](../contracts/business-http/operations.json).
OpenAPI: [openapi.json](../contracts/business-http/openapi.json).
These are the initial shared candidate catalog, not an alternative peer catalog.
Other receiving owners must extend/review it with their canonical operations.
Existing GET reads have no durable write effects and no retry; none of this
implements initialization idempotency or callbacks.

## Still missing before the full goal can be fulfilled

1. Credential's real persisted Generate/Get/Validate operations, generated-document
   provenance/authenticity and durable initialization/outbox/recovery. Removing
   the fixture does not implement those operations.
2. Receiver-owned Applicant context, internal Record facts, Session ruleset/shift
   context, moderation-history and initialization callback contracts, including
   method/path, schemas, credentials, allowlists, budgets and idempotency rules.
   Public junior Record access must not be impersonated for internal fact reads.
3. Authoritative Rules fact provider, session-bound persisted ruleset selection,
   rotation/evaluation operations and a finite dependency graph. The existing
   caller-facts `/evaluate` path remains a legacy/unverified-facts compatibility
   operation; it must not be described as authoritative or full baseline readiness.
4. Gateway registry/allowlist and target-credential changes, real peer services,
   then database-backed multi-service success/denial/spoofing/outage/recovery and
   second-replica/restart/duplicate initialization acceptance.

The catalog deliberately does not assign guessed peer paths. Keep reviewable
candidate PRs draft until these coordinated prerequisites are resolved. Do not
merge or publish a stable release, migrate broker transport, edit the architecture
diagram, or change Discovery merely to produce artificial business calls.
