# Credential Grade 8 integration handoff

Credential implements the eight operations in CPR #193 and Broker #45:
snapshot, prepare, commit, abort, status, acknowledge, release and pending.
The older five-command local proposal is superseded; there is no rollback or
activate operation in the shared dossier-v1 protocol. Rules stays read-only.

Candidate source: [Credential PR #71](https://github.com/CmMarin/student-id-credential-service/pull/71),
commit `9df277e`, branch `feature/credential-dossier-2pc`, candidate version `lab5-1.7.0`. It is not a
published-image claim. Enable `DOSSIER_2PC_ENABLED=true` only in a coordinated
deployment; PostgreSQL primary and standbys need `max_prepared_transactions=32`.
Existing receiver credentials, gRPC transport, trace/deadline checks and Broker
grants are preserved. No teammate private service source has been changed.

Credential reserves exclusive generation ownership on snapshot; generates actual
documents from the complete Applicant/Record snapshots using the persisted asOf;
stores a replay-stable manifest/full-request fingerprint before PostgreSQL
preparation; persists immutable decisions and abort-before-prepare tombstones;
and resolves pg_prepared_xacts through commit/abort. A committed marker recovers
lost commit replies. Completion acknowledgment is durable and keeps ready=false;
only release exposes READY. It never sends independent legacy CredentialsReady
callbacks for dossier rows. Ordinary CRUD cannot change an unreleased dossier.

## Verified joint acceptance on 2026-11-25

Verification passed against real Broker source
`b4782def5cd4386c5a0382f6e519f363b243b443`: the coordinator drove Credential's
production gRPC consumer and actual PostgreSQL document participant to
SUCCEEDED/COMMIT, including snapshot, prepare, commit, acknowledge and release.
Applicant, Record and Discovery were explicit contract peers in that check.
That earlier compatibility check is now supplemented by joint acceptance below.

The full Credential suite passed (101 passed, four Redis-dependent skips), then
the final 15 participant/transport checks passed with a non-superuser
`dossier_owner` role, including the real-Broker proof and non-enrolled applicants.
Measured line coverage is 91.1%. Detailed candidate evidence is in Credential's
`docs/dossier-v1-evidence.json`; no image or submodule pointer is advanced here.

The updated public tags were pulled, their source revisions verified, and their
actual applications used in joint acceptance:

| Image | OCI source revision | Finding |
|---|---|---|
| andreiisthebest/student-id-message-broker:lab4-0.9.0 | ca34c131990b86c4b95cf05448c4c366acee1f90 | Real coordinator; passed |
| andreiisthebest/student-id-university-record-service:lab3-1.8.0 | 8e31a7665b4cc8c5e7795dc947ba0e3c28f87fe4 | Real metadata participant; passed |
| andreiisthebest/student-id-applicant-service:lab3-1.8.0 | 3742a8be3e6340d42bb7a5c56514b532ee36445c | Real metadata participant; passed |

The private Applicant/Record repositories remain inaccessible to this account;
the published applications were tested directly. Credential ran its actual
packaged candidate application in Java 21, not a test implementation. Its jar
SHA-256 and the three immutable image digests are recorded in the
[joint summary](credential-dossier-joint-evidence.json).

## Joint result and limits

**61 acceptance checks passed**, using three separate PostgreSQL databases and
non-superuser participant roles. They verified actual document/reference
agreement, lost real prepare/commit replies, idempotent replay, source-version
conflict and rollback, invisible prepared writes and preservation of later edits.
All three databases and participants were restarted after durable COMMIT; Broker
remained stopped past the original deadline. Prepared resources survived without
heuristic rollback, applicants stayed unpresentable, and recovery committed once
with no remaining prepared transactions. The successful run needed no setup retries.

Discovery and transparent fault-injection proxies were the only test infrastructure;
none implemented participant business logic. Disposable resources were removed,
with logs retained locally. The earlier peer-based evidence in
docs/dossier-grade8-evidence.json is preserved separately.

This verifies Grade 8's joint 2PC functionality. It does not publish Credential's
candidate or prove physical-standby promotion. Review/release remains necessary;
before shared HA activation, verify prepared WAL survives the intended fenced
promotion. No shared image pins or submodule pointers are advanced by this handoff.
