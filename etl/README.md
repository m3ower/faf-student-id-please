# Warehouse ETL job

See [the versioned extraction contract and runbook](../docs/warehouse-extraction.md).
This is a one-shot batch job, not another live business microservice.

`run.py` extracts service-owned, authenticated snapshots, validates/normalizes
allowlisted records and atomically loads PostgreSQL reporting batches. `schema.sql`
contains storage and reporting views. `sources.json` configures Player, Session,
Credential and Rules; the latter two export only approved document inventory counts
and policy metadata. See [their exact schemas](../docs/owned-warehouse-exports.md).
Other owners adopt the documented contract separately. The existing live-container
helper remains explicitly scoped to Player/Session and does not prove other sources.

Secrets are environment-only. Source databases are never connected directly.
Docker Compose selects an explicit ETL image, and its database volume persists.
There is no publication workflow or automatically enabled scheduler in this change.
