# Warehouse: eight-source integration

Tracks CPR #177. Preserves the shared job (#172) and Credential/Rules additions
(#173), and activates the exact manifests supplied in Applicant/Record #175 and
Moderation/DMs #176. No private service code, business transport, submodule pointer
or base release pin is changed.

| Source | Dataset | Reporting view |
| --- | --- | --- |
| Player | players | player_progression |
| Session | sessions | session_results |
| Credential | credential-inventory | credential_inventory |
| Rules | rules | rule_policy |
| Applicant | applicants | applicant_claims |
| University Record | university-records | university_record_summary |
| Moderation | decisions | moderation_decisions |
| Discord DMs | channels | dms_channels |
| Discord DMs | channel-days | dms_channel_activity |

The four new entries must remain identical to their manifests in
`contracts/analytics/`. Each source requires its own reporting token. The ETL
joins `applicant-net` and `record-net` as well as the default and private Warehouse
networks: those two sources cannot be reached from the default network alone.
Warehouse itself remains isolated on `warehouse-net` without a host port.

The new views preserve source meaning. Applicant values remain **claims**;
Record counts remain ground-truth observations, with FCIM limited to the owner's
documented legacy count. Moderation's `decided_at_epoch_ms` remains integer UTC
epoch milliseconds. DMs' `utc_day` remains its wire-format `YYYY-MM-DD` string.
These columns deliberately preserve the declared primitives rather than silently
adding a new date/timestamp validation contract. Messages are history-window
counts, not complete lifetime totals. No chat text, applicant/student identity,
credential document or authorization assignment is added.

## Release prerequisites

The example environments now select the published releases verified on 2026-11-26.
Copy the selections into your private environment; existing `.env` overrides do
not change automatically. Keep all reporting credentials private. The exact image
pins, source revisions and populated acceptance scope are recorded in
[Lab 5 release pins](lab5-release-pins.md).

All eight tags were pulled successfully for the isolated acceptance below.
Recheck digests and source revisions with owners before a later deployment. The known lab3
prefixes are the owners' actual published naming, not an instruction to relabel
their images. Any `WAREHOUSE_ETL_IMAGE` override must include this eight-source
configuration and nine views; the pinned default already contains them.

All eight configured sources must succeed, even if they return empty datasets.
There is no silent skip for a missing image/token/service. A failed export leaves
the previous batch intact. The existing retention and per-source snapshot model
remain; no globally simultaneous snapshot is claimed.

## Verification

The complete `etl/tests` suite uses populated authenticated HTTP peers and real
disposable PostgreSQL to verify all nine views, exact schemas, two DMs datasets,
privacy rejection, replay, updates/deletions, retained history and failure of
each new source. Those peers are **contract doubles**, not the owners' binaries.
CI enforces 70% coverage across the job and all-source acceptance helper.

For actual released services, enable their reporting tokens privately and use a
disposable test Warehouse with standard `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`
settings. Optional `ETL_SOURCES_FILE` may override addresses/token variable names
for testing, but schemas and the eight canonical sources must remain unchanged.
Run from inside the ETL container's private networks:

```powershell
docker compose --env-file .env -f docker-compose.yml -f docker-compose.owned-broker.yml -f docker-compose.warehouse.yml run --rm warehouse-etl python verify_exports.py
```

Use the same Compose project and **test** environment that starts all sources;
do not run against unrelated classmates' databases. The helper reads every real
export, loads a disposable `verify_warehouse_<uuid>` schema in the test Warehouse,
compares complete normalized records and all typed views, tests replay and an
**injected** extraction failure, then drops its own schema. Only safe counts are
logged; no reporting credentials or rows are printed. It does not stop sources
or simulate a real outage. A zero count is accepted only from a successful valid
snapshot and is reported as zero, never fabricated for an unavailable source.

For presentation, create known source data through the normal business flows
before running this check. Compare expected analytical values with the views.
In a separate disposable deployment, also stop a real source and verify an ETL
failure preserves the previous successful batch. The two-source
`etl/verify_live.py` already automates that scenario for Player/Session; extending
gameplay-generated seeding to other owners requires their normal business setup.

Full released-image acceptance and real outage testing must be reported
separately from the passing populated-peer suite and Compose validation.

### Executed acceptance — 2026-11-23

- Twelve tests passed on Python 3.12 with disposable PostgreSQL, at **83%**
  combined coverage for `run.py` and `verify_exports.py`. Image build, Compose
  validation and the existing HTTP/messaging catalog validators also passed.
- A separate, uniquely named Compose project started the eight published images
  above and fresh backing stores, using generated test-only credentials and no
  host ports. Reporting credentials were distinct. Discovery registration was
  disabled; Broker/Gateway were not started. This verifies reporting extraction,
  not a gameplay or business-messaging end-to-end run.
- All eight authenticated real exports passed validation. Synthetic Player and
  Session rows produced two reporting rows; the other six services returned valid
  empty datasets. All nine views materialized and the records matched the exports.
  Populated data for every dataset is covered separately by the contract peers.
- Replaying the run ID performed no second load. Updating Player XP from 100 to
  200 and deleting the synthetic Session produced the expected next batch.
  Stopping the test DMs container caused `EXPORT_UNAVAILABLE` and preserved that
  batch. The acceptance helper separately passed its injected-failure check.
- All test containers, networks and volumes were removed. No existing stack or
  private service code was changed. The Windows checkout had a CRLF initialization
  script; only its disposable test-mounted copy was normalized to LF. The existing
  `.gitattributes` already requires LF for shell scripts; ensure the deployment
  checkout respects that rule.

Recorded image digests (the tags above) and OCI source revisions:

| Source | Image digest (`sha256:`) | Source revision |
| --- | --- | --- |
| Player | `e67679416c181f63d417cbdeac0b567381bb6b1846f0471bf573685394e99ca5` | `be153dd278d38e0efa5f4041a3be9260a6eb9edc` |
| Session | `06c84e4c44e1df0a831e2b6c4c49c7456078d8f026d1a515228dafe2dbad6c05` | `8901c25ee9ff1bec8d3197b732b4d0924c0c5961` |
| Credential | `c1dc965dccafd1aa17c26bb3d446aacf048c9e3b97baebc1ee87a5e15e931cb8` | `6f92036cb103ed085d82e9b4b0d104a2820c57a7` |
| Rules | `151c74906f96bb5249f1b2ae3f5cbe803e8f543ad1d8d7f3e3957a33d1b289bb` | `e6202af8284596fbb01e55238158ea084b6e2e51` |
| Applicant | `0eb7600e6452249d60ee627bab448ddea66c04c78758c77c673de5727b413c41` | `631b13b57581d0b17545698d56b21685e29f68cb` |
| University Record | `77201fb26466a956f5241e450228a8f2e999388a5337eb9481ebf2875ebe8c77` | `c7b3750e5f2bdaced061568cdf67279f36e9bb16` |
| Moderation | `5272a96d0df2782a5c85e0e34c94942d9154980383d478eb6f2e58e110160280` | `6a764d5b56dd481a647b1723e7d13999564f45f1` |
| Discord DMs | `86f4510c972bc9ebf87df716a3cbb256aa9f730a17b0d32cab638f93e0f03b66` | `6ae837ef31fb3662760627bc95dff20c497b383b` |

Revision labels record the publishers' source claims; this check did not audit
inaccessible private repositories. At that acceptance run the ETL build was local;
it has since been published as described below. Shared deployment still needs
private source-image/token configuration. Existing base release pins remain unchanged.

## Published ETL release

Published `vasiok11/student-id-warehouse-etl:lab5-0.1.0` from merged CPR commit
`90a6a2616788a33375140418e653994c6b76fbbd` (PR #178). Immutable image digest:
`sha256:77bc3b0bd4cd16d3f4d2fef2d25e005f10c81f9d5dba84fe7dc40a700812de37`.
The image contains all eight sources, nine datasets/views and `verify_exports.py`.
Its OCI labels record the source revision and Lab 5 version. The release smoke
check verified imports, source/dataset counts and the non-root user (UID 10001).

The Warehouse Compose overlay and `.env.warehouse.example` select this digest.
Existing non-empty private `WAREHOUSE_ETL_IMAGE` overrides still take precedence;
update those deliberately when deploying. Source-service image choices and all
credentials remain private configuration. Publishing/selecting this release does
not start a stack or run a reporting job.
