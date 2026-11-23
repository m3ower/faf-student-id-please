# Warehouse ETL job

See [the versioned extraction contract and runbook](../docs/warehouse-extraction.md).
This is a one-shot batch job, not another live business microservice.

`run.py` extracts service-owned, authenticated snapshots, validates/normalizes
allowlisted records and atomically loads PostgreSQL reporting batches. `schema.sql`
contains storage and reporting views. `sources.json` configures all eight services
and nine datasets using the reviewed handoffs. See
[the full integration guide](../docs/warehouse-all-sources.md).

`verify_exports.py` checks the eight real endpoints using configured reporting
credentials, compares every loaded row and typed view, checks replay/rollback and
removes only its disposable Warehouse schema. Use a test Warehouse, not a source
database. It never starts/stops source services or seeds their private data.
`verify_live.py` remains a separate isolated Player/Session container scenario;
it does not claim full-team acceptance. Tests with populated HTTP contract peers
are distinguished from tests of actual released service images.

Secrets are environment-only. Source databases are never connected directly.
Docker Compose selects an explicit ETL image, and its database volume persists.
There is no publication workflow or automatically enabled scheduler in this change.
