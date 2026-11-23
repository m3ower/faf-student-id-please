# Warehouse ETL job

See [the versioned extraction contract and runbook](../docs/warehouse-extraction.md).
This is a one-shot batch job, not another live business microservice.

`run.py` extracts service-owned, authenticated snapshots, validates/normalizes
allowlisted records and atomically loads PostgreSQL reporting batches. `schema.sql`
contains storage and reporting views. `sources.json` configures only Player and
Session initially; other owners adopt the documented contract separately.

Secrets are environment-only. Source databases are never connected directly.
Docker Compose selects an explicit ETL image, and its database volume persists.
There is no publication workflow or automatically enabled scheduler in this change.
