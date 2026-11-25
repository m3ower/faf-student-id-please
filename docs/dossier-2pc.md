# Lab 5 Grade 8: dossier v1 protocol and owner handoff

Candidate 0.9.0. Credential, University Record and Applicant are participants;
Message Broker is the external transaction manager. Player, Session, Moderation,
DMs and Rules receive no transaction changes. Preserve this Grade 8 branch and its
evidence before implementing a separate Grade 9 saga.

## Enablement and control API

`BROKER_DOSSIER_ENABLED=false` by default. Enable only with a durable private
`BROKER_STATE_PATH`, the reviewed participant builds and matching CPR contract.
The sibling `*.dossier-v1.sqlite3` journal uses SQLite WAL, synchronous=FULL and
one exclusive process owner. Mount the data directory on durable storage;
independent writable coordinator replicas are unsupported.

Only configured Applicant, Record or Credential caller credentials may use:

* POST /internal/v1/dossiers/v1: accept the immutable start below, returning 202
  and current workflow state. Admission is not business completion.
* GET /internal/v1/dossiers/v1/{workflowId}: phase, decision, completion receipts
  and pending notifications, without authoritative snapshots or document bodies.

```json
{"version":1,"workflowId":"UUID","initializationId":"UUID","applicantId":"UUID",
 "deadlineAt":"RFC3339 UTC timestamp, within 30 seconds for a new workflow"}
```

The exact start, including deadline, is immutable. Replays return the same
workflow. Changed input or another workflow for the initialization/applicant
conflicts. The verified publisher message-broker is reserved to Broker code:
configuring an external caller credential for that name is rejected.

Participant commands use the unchanged MessageConsumer.Deliver proto and the
canonical operation.<prefix>.dossier.<command>.v1 bindings. Selection,
subscriptions, fresh gRPC health, target authentication, circuits and bounded
delivery threads are preserved. There is no REST delivery fallback.

## Durable state machine

1. Persist the workflow. Require full persisted Applicant/Record initialization
   context. Capture and persist authoritative snapshots/source versions first.
2. Bind Credential's exclusive generation path. Pass the agreed snapshots and
   persisted asOf time. Journal exact prepare input BEFORE dispatch. Credential
   prepares documents/provenance and returns replay-stable document references
   from its durable manifest, without querying another participant's prepared rows.
3. Record and Applicant prepare metadata only using real PostgreSQL PREPARE
   TRANSACTION, validating and retaining source-version locks. Immutable legacy
   callback receipts are never repurposed as transaction records.
4. After every valid PREPARED business receipt, fsync COMMIT before any commit
   instruction. Failure while undecided permits durable ABORT, resolved at ALL
   participants, including abort-before-prepare tombstones.
5. Obtain every commit acknowledgment, then every completion acknowledgment.
   Local ready remains false. Durably finalize success, then release completion
   notifications, with Applicant released last.
6. Retry lost notifications after finalized success; never change COMMIT to ABORT
   or compensate. Status can show finalized SUCCEEDED with notificationsPending
   and ready=false until releases finish. Independent reads need not change
   visibility simultaneously.

Receipts must match version, workflow, initialization, applicant, participant,
step, fingerprint, phase and acknowledgment booleans. A queue receipt or generic
2xx is insufficient. Request expiry after durable COMMIT never cancels recovery.
Contradictory receipts after COMMIT require recovery, not a new decision.
The indexed scan reads at most 64 pending IDs and advances one bounded command per
workflow per pass. History caps at 10,000 workflows without discarding deduplication
or decisions. Storage failure stops unjournaled decisions from being sent.

## Generation paths and Credential owner handoff

Applicant/Record default DOSSIER_NEW_INITIALIZATION_PATH to LEGACY. Opt-in
DOSSIER_V1 is stored atomically with NEW full initializations. Existing rows keep
LEGACY permanently. Dossier rows skip automatic Credential generation and reject
legacy completion callbacks; full-context peer initialization remains preparatory
work. No workflow takes over a legacy document set or changes academic truth.

The eight credential.dossier.* operations are explicitly candidate, not a claim
of implemented/deployed Credential behavior. Its owner must implement:

* snapshot: dossierIdentityV1 with stepId=credential.generate.v1; atomically select
  and persist exclusive generation ownership. Reject existing legacy generation,
  documents, workers or completion delivery. Return a reliable sourceVersion UUID.
* prepare: dossierCredentialPrepareV1, containing identity, sourceVersion,
  inputs with BOTH full owned snapshots, and persisted asOf. Validate complete
  authoritative inputs. Fingerprint the FULL request and persist stable document
  IDs/provenance intent before actual PostgreSQL preparation. PREPARED must be
  backed by pg_prepared_xacts; the receipt includes 1..32 distinct credentialIds,
  recoverable from durable control intent despite invisible document rows.
* commit/abort: retain immutable decisions and resolve its own prepared resource.
  Reconstruct outcomes from pg_prepared_xacts/committed markers after restart.
  Persist abort tombstones; never roll back an uncertain resource by elapsed age.
* acknowledge: durable completion receipt after local business commit, ready=false.
* release: require that receipt, release readiness and persisted notification
  outbox after coordinator finalization; repeat lost notifications safely.
* status/pending: recoverable business phases using the common receipt schema.

The new acknowledgment/release protocol replaces the legacy generation/callback
completion sequence for dossier rows. It must not independently send legacy
CredentialsReady into immutable Applicant/Record receipts. Receivers enforce
workflow identity, phase and protocol version. Legacy rows retain legacy behavior.

Applicant snapshots contain initialization, current stored profile and courses.
Record snapshots contain initialization, stored enrollment link, identity facts
and university record (null for non-enrollment). Real source writes change UUID
versions; event hashes alone are insufficient. Use the supplied asOf for
date-dependent derivation across retries. Exact schemas/examples are in CPR.

## Database requirements and evidence

Enable a tested nonzero max_prepared_transactions on each primary and at least
the same capacity on replicas; this requires server startup configuration.
Resolution uses the same database owner or a properly privileged operator.
Monitor prepared age and unresolved decisions; an age-based rollback janitor is
forbidden. Existing asynchronous HA is NOT proof that acknowledged PREPARE/COMMIT
WAL survives promotion. Test no-loss recovery/promotion before shared activation.
This change promotes no shared images, pins or existing HA configuration.

[PostgreSQL PREPARE TRANSACTION](https://www.postgresql.org/docs/16/sql-prepare-transaction.html),
[COMMIT PREPARED](https://www.postgresql.org/docs/16/sql-commit-prepared.html),
[prepared capacity](https://www.postgresql.org/docs/16/runtime-config-resource.html#GUC-MAX-PREPARED-TRANSACTIONS).

Run repository checks, then:

```text
python scripts/verify_dossier_2pc.py --applicant-root ../applicant-dossier-2pc --record-root ../record-dossier-2pc
```

The driver uses three separate PostgreSQL servers with non-superuser application
owners, actual Applicant/Record artifacts and the actual Broker image. Credential
and Discovery are explicit peers; synthetic documents/provenance use actual
PostgreSQL preparation, not the Credential owner's application. The peer is
excluded from the production image. Evidence covers lost actual-owner prepare/
commit replies, source-version abort, preserved academic truth/immutable receipts,
non-presentability and restart of BOTH actual participants and BOTH databases
after durable COMMIT. Broker stays stopped past the original deadline, then
recovers the same decision. Logs/summary stay under .local-ci. Joint acceptance
with Credential's actual owner build is still required.

## Owned source evidence

Applicant resource-manager implementation: Andreiisthebest/student-id-applicant-service
commit 0034123; Record resource manager: Andreiisthebest/student-id-university-record-service
commit 75fc11f. Broker implements durable coordination. Credential is candidate
owner work, not a fabricated participating service. No shared submodule or image
pin is advanced by this protocol proposal.
