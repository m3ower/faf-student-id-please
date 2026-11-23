# Credential and Rules reporting snapshots

Lab 5 Grade 4, following the shared Warehouse candidate's version-1 contract.
Tracks CPR #171, Credential #54 and Rules #50. These are additive source changes;
review and image publication are required before deployment. No business RPC or
Gateway route is added. Direct reporting HTTP is the documented operational exception.

Both services expose private `GET /internal/v1/analytics/snapshot` to caller
`X-Service-Name: warehouse-etl` with `Authorization: Bearer <reporting-token>`.
The service variable is `WAREHOUSE_EXPORT_TOKEN`; Compose and ETL use the distinct
`CREDENTIAL_WAREHOUSE_EXPORT_TOKEN` and `RULES_WAREHOUSE_EXPORT_TOKEN` values.
Tokens are 32-256 URL-safe characters, distinct from business/Discovery credentials.
Missing, malformed or reused configuration disables only export with 503
`EXPORT_NOT_CONFIGURED`. Missing/wrong authorization is 401, wrong caller is 403,
query parameters are 400 `INVALID_QUERY`, source failure is sanitized 503
`EXPORT_UNAVAILABLE`, and overflow is 413 `EXPORT_TOO_LARGE`. Bodies on GET are
rejected. Responses and errors use `Cache-Control: no-store` and existing trace
conventions. Reporting uses the existing business admission/deadline mechanism.

## Allowlisted datasets

| Source / dataset | Stable record ID | Exact data fields | Units |
| --- | --- | --- | --- |
| `credential-service` / `credential-inventory` | persisted credential type enum, such as `STUDENT_ID` | `credentialType`: string; `documentCount`: integer; `issuedDateCount`: integer; `expiryDateCount`: integer | counts of currently stored documents / non-null date columns |
| `rules-service` / `rules` | persisted nonzero rule UUID | `type`: string; `severity`: string; `active`: boolean | current persisted policy metadata |

Credential uses one grouped read query. It exports no credential ID, applicant ID,
document fields, email, student ID, name, hashes or token. Date counts indicate
presence only: they do not claim authenticity, validity, enrollment or expiry.
Rules exports no custom code/description, application facts, player/session IDs,
authorization assignments or minimum-year null placeholders. Nothing is fabricated
to satisfy the non-null version-1 schema. The stable credential type ID is an opaque
reporting key, not a person/document identity.

Every response includes all configured datasets, even when empty. Credential has
at most the four current credential-type groups; the 10,000 limit applies to
reporting records, not underlying operational documents. Rules reads at most
10,001 rows and rejects the entire export above 10,000. Both reject output over
8 MiB. Reads use read-only repeatable-read transactions; there are no ETL-triggered
business writes, cross-database SQL or global multi-source snapshot claims.

The canonical `etl/sources.json` retains the Player and Session entries and adds
these exact two schemas. Typed current-snapshot views are `credential_inventory`
and `rule_policy`. Updates/deletions appear in the next successful batch; historical
snapshots remain governed by the existing retention policy. Do not sum periodic
document counts across historical runs as if they were newly issued documents.

## Deployment and verification

Use the existing shared Warehouse overlay with reviewed export-capable images.
`WAREHOUSE_CREDENTIAL_IMAGE` and `WAREHOUSE_RULES_IMAGE` are intentionally required;
the candidate release target for each owned service is `lab5-1.3.0`, not a claim
that those tags already exist. Configure reporting tokens privately. Backend ports
stay private; no export is added to Gateway, Broker topics or the protobuf catalog.
The ETL receives the reporting credentials and its own Warehouse credential only.

```powershell
docker compose --project-name <existing-project> --env-file <private-env> `
  -f docker-compose.yml -f docker-compose.owned-broker.yml `
  -f docker-compose.warehouse.yml up -d warehouse credential-service rules-service
docker compose --project-name <existing-project> --env-file <private-env> `
  -f docker-compose.yml -f docker-compose.owned-broker.yml `
  -f docker-compose.warehouse.yml run --rm warehouse-etl
docker compose --project-name <existing-project> --env-file <private-env> `
  -f docker-compose.yml -f docker-compose.owned-broker.yml `
  -f docker-compose.warehouse.yml exec warehouse psql -U warehouse -d warehouse `
  -c "SELECT * FROM credential_inventory; SELECT * FROM rule_policy;"
```

All four configured sources must be available; a failed source preserves the
previous committed batch. Do not use `down -v` or give the job source DB credentials.
The shared `verify_live.py` remains explicitly scoped to Player/Session; it does
not prove the new owned sources. Owned service tests cover their actual database
handlers; ETL tests cover the strict schemas, atomic replacement and typed views.
Release-image multi-service acceptance remains a separate rollout check.
