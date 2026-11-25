# Task 9 dossier saga integration contract

The executable source is [saga-v1.json](../contracts/dossier/saga-v1.json).
It defines every request, receipt, state, fingerprint, error and recovery rule.
The HTTP operation catalog/OpenAPI and 18 request/response examples are generated
by `python scripts/build_dossier_saga_contract.py`; follow with
`python scripts/validate_http_contracts.py --write-openapi` and
`python scripts/validate_messaging_contracts.py --write`.

Credential, Record and Applicant implement `snapshot`, `apply`, `status`,
`compensate`, `acknowledge` and `release` under `<owner>.dossierSaga.<command>`.
They use the existing authenticated Broker MessageConsumer.Deliver transport,
reserved `message-broker` publisher and catalog grants. The protocol is additive;
all existing Grade 8 commands, releases and evidence remain available unchanged.

New initialization path `DOSSIER_SAGA_V1` is exclusive with `LEGACY` and
`DOSSIER_V1`. All participants must persist that ownership, validate reliable fact
versions, suppress independent legacy document generation/callbacks and retain
their normal peer initialization deliveries. CRUD-created profiles alone are
insufficient. Snapshot returns `facts.generationPath=DOSSIER_SAGA_V1` and stable
full facts; repeated snapshot returns its original persisted projection.

Broker snapshots all three participants before applying any step. It freezes the
complete Applicant/Record snapshots in `inputsJson` and its `asOf` timestamp.
Credential receives those exact agreed inputs; it must not refetch evolving facts
or independently declare READY. All six command bodies are described by catalog
schemas and examples. The identity and apply fingerprints use **four-byte
big-endian lengths**, separately from Grade 8's older fingerprint encoding.
`inputsJson` is an exact persisted JSON string: no cross-language canonical JSON
algorithm is required. Credential apply alone accepts empty `credentialIds`;
its receipt must return 1..32 actual stable generated IDs. Record and Applicant
receive that same reference set and attach only independent saga-owned metadata.

Every apply commits a normal local database transaction including its durable
receipt and outbox intent. No database preparation is involved. Metadata ownership
and effect versions must be checked before compensation. Terminal tombstones
reject delayed commands and cancel notification intent. Later edits to workflow
resources are preserved and reported as durable `CONFLICT`, requiring intervention.
Compensating an unexecuted step creates a tombstone, protecting against a delayed
apply. Replaying apply after compensation returns that current terminal outcome.

Broker persists requests/attempts before dispatch and outcomes before acknowledging
progress. An uncertain transport outcome is resolved using status/idempotent
replay. Recovery never infers business completion from transport admission and
never treats a timeout as proof of failure. It retains bounded exponential retry
information across restarts. Failed workflows compensate Applicant, Record, then
Credential. Compensation conflicts stop recovery in `INTERVENTION` with false
readiness. Retain terminal journals without automatic expiry.

After all three business commits, obtain completion acknowledgments while ready
remains false. Persist immutable global `SUCCEEDED` before releasing Credential,
Record, Applicant. Recover delivery failures by retry only after success; never
compensate finalized success. Session sees Applicant as unpresentable until that
last release. There is no promise of simultaneous visibility across HTTP reads.

The initial contract PR does not claim any participant implementation or Grade 9
joint acceptance. Marin owns Credential. Shared activation requires its real
candidate and final acceptance with all four actual applications. Rules, Player,
Session, Moderation and DMs require no saga participant changes.
