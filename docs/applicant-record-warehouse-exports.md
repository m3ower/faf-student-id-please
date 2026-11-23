# Applicant and University Record Warehouse export contracts

This is the shared contract handoff for Andrei's two service-owned exports,
implementing the version-1 reporting exception proposed in [CPR #172](https://github.com/m3ower/faf-student-id-please/pull/172).
Its linked issue is #170; the earlier handoff called that issue a PR. The Lab 5 PDF
places Warehouse/ETL implementation under Grade 4. This document does not claim a
published or fully integrated deployment.

## Sources and review state

Both private implementation PRs have merged to `dev`; their exact tested feature
revisions and receiving contracts are:

| Source | Private implementation | Tested revision | Private endpoint | Proposed ETL schema |
| --- | --- | --- | --- | --- |
| Applicant | [PR #37](https://github.com/Andreiisthebest/student-id-applicant-service/pull/37), [issue #36](https://github.com/Andreiisthebest/student-id-applicant-service/issues/36) | `1f0e1557630f21c78bdb03ed6097cac64dd09d87` | `http://applicant-service:8080/internal/v1/analytics/snapshot` | [applicant-service.json](../contracts/analytics/applicant-service.json) |
| University Record | [PR #37](https://github.com/Andreiisthebest/student-id-university-record-service/pull/37), [issue #36](https://github.com/Andreiisthebest/student-id-university-record-service/issues/36) | `81b27de71c1e888e29abb7040395c98c4743dc66` | `http://university-record-service:8081/internal/v1/analytics/snapshot` | [university-record-service.json](../contracts/analytics/university-record-service.json) |

Candidate source version: **1.4.0** for both. No published export-capable image tag
or registry digest is selected by this contract. Private source, patches and
credentials are not included in CPR. These manifests are proposed entries for
ETL-owner review, not an alternative active `etl/sources.json`.

## Exact allowlists

Each dataset record uses its stored row UUID as the opaque `id`. All `data`
objects have exactly the following non-null fields:

| Source / dataset | Field | Wire type | Meaning / units |
| --- | --- | --- | --- |
| `applicant-service` / `applicants` | `year` | integer | Stored claimed study year, in years; not verified enrollment truth |
| `applicant-service` / `applicants` | `universityStatus` | string | Stored claimed university status |
| `applicant-service` / `applicants` | `role` | string | Stored claimed applicant role |
| `applicant-service` / `applicants` | `courseCount` | integer | Number of stored applicant-course entries |
| `university-record-service` / `university-records` | `status` | string | Stored authoritative university record status |
| `university-record-service` / `university-records` | `courseCount` | integer | Number of stored course array entries |
| `university-record-service` / `university-records` | `outlookGroupCount` | integer | Number of stored group array entries, without group names |
| `university-record-service` / `university-records` | `fcimMessageCount` | integer | Number of stored legacy FCIM array entries, without contents |

Record's legacy message count does not include separate normalized FCIM rows and
must not be interpreted as complete chat history. Applicant claims and Record
truth remain independent. Counts are observations of each owner's persisted
store, not new events or verified-document counts. Do not sum repeated snapshots
as if every observation represented a new business event.

No names, email/student IDs, majors, documents, tokens, deception, initialization
envelopes, message contents or authorization assignments are exported. Each owner
queries only its own database, selecting explicit fields/counts rather than
serializing domain entities. The ETL receives no source database credentials.

## HTTP, security and snapshot behavior

Use `GET` without query or body, `Authorization: Bearer <reporting-token>` and
`X-Service-Name: warehouse-etl`. This direct private HTTP route is an operational
reporting exception, not gameplay traffic. It is not a public Gateway route,
Broker operation/topic or protobuf change. Backend ports remain private.

The service variable is `WAREHOUSE_EXPORT_TOKEN`; ETL uses distinct
`APPLICANT_WAREHOUSE_EXPORT_TOKEN` and `RECORD_WAREHOUSE_EXPORT_TOKEN` values.
Tokens are 32..256 URL-safe ASCII characters, separate from that service's Broker,
receiver, management and Discovery credentials. Empty/malformed/reused reporting
configuration returns 503 `EXPORT_NOT_CONFIGURED` for export only, preserving
legacy startup and business reads. Wrong/missing credentials return 401, wrong
caller 403, queries 400 `INVALID_QUERY`, nonempty body 400 `INVALID_REQUEST`, source
failure 503 `EXPORT_UNAVAILABLE`, and overflow 413 `EXPORT_TOO_LARGE`. Existing
admission 429 and deadline 504 behavior still applies. Responses/errors are JSON,
use `Cache-Control: no-store`, and retain existing trace/error conventions.

Exports share actual HTTP/gRPC business admission and task deadlines. Work that
continues after a caller timeout remains counted until its handler stops. Existing
status/readiness probes, business auth, subscriptions and durable idempotency are
unchanged. Reporting does not create gameplay data.

Each response is a complete read-only PostgreSQL repeatable-read snapshot:
`schemaVersion: 1`, canonical `source`, UTC `capturedAt`, and exactly one named
dataset, including `records: []` when empty. IDs are stable opaque UUID strings;
integer measures are signed-64-compatible, strings are at most 128 characters,
and no field is nullable. At most 10,000 total records and 8 MiB of UTF-8 JSON are
returned. Both implementations query an extra row and buffer the whole response;
overflow fails before any partial snapshot is returned. Larger data requires a
coordinated versioned snapshot/cursor contract, not silent truncation.

Updates/deletions appear in the next successful complete snapshot. Empty datasets
explicitly remove all current records for the dataset when loaded by the shared
ETL. Per-service snapshot times differ; there is no globally simultaneous
multi-database snapshot, cross-database query or complete event audit claim.

## Evidence and coordinated integration

- Applicant: 62 tests pass, 94.21% application line coverage; private PR CI passes.
- Record: full race/database suite passes, 78.1% line and 81.8% statement coverage;
  private PR CI passes.
- Sixteen isolated real-container checks passed against the unchanged shared ETL
  candidate at `13f42b96f9e29b3f111c4e622d05d284e5fdf345`. Its strict validator
  accepted both manifests and loaded actual Java/Go HTTP snapshots. Checks cover
  replay, updates/deletion, empty snapshots, stopped-source atomic rollback and
  authorized business reads with reporting disabled.
- That acceptance overrides the ETL source list only inside its disposable test.
  Three databases use distinct credentials; ETL receives only its own Warehouse
  credential and the two reporting tokens. Synthetic rows, local test images and
  isolated networks do not establish published full-team acceptance.

The shared owner must first agree these allowlists and review the source/image
provenance, then append the two schemas, reporting views and explicit deployment
variables to the shared candidate. Preserve the Player/Session entries in #172
and the independently owned Credential/Rules additions in #173. Do not duplicate
or overwrite their pending implementation. This PR changes no active ETL source
list, SQL view, Compose file, image reference, submodule pointer or architecture
diagram. Publication and coordinated released-image acceptance follow separately.
