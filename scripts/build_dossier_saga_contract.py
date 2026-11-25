"""Build the additive, executable dossier-saga-v1 schemas and transport examples."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'dossier-saga-v1'
COMMANDS = ['snapshot', 'apply', 'status', 'compensate', 'acknowledge', 'release']
PARTICIPANTS = {'credential-service': ('credential', 'credential.create.saga.v1', 'credentials'),
                'university-record-service': ('record', 'record.attach.saga.v1', 'records'),
                'applicant-service': ('applicant', 'applicant.attach.saga.v1', 'applicants')}


def fields(*values):
    return hashlib.sha256(b''.join(len(v.encode()).to_bytes(4, 'big') + v.encode() for v in values)).hexdigest()


def obj(properties, required=None):
    return {'type': 'object', 'additionalProperties': False,
            'required': list(properties) if required is None else required, 'properties': properties}


def main():
    uuid = {'type': 'string', 'format': 'uuid'}
    digest = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
    text = {'type': 'string'}
    identity = obj({'protocol': {'const': PROTOCOL}, 'version': {'const': 1},
                    'workflowId': uuid, 'initializationId': uuid, 'applicantId': uuid,
                    'stepId': {'enum': [v[1] for v in PARTICIPANTS.values()]}, 'fingerprint': digest})
    refs = {'type': 'array', 'items': uuid, 'maxItems': 32, 'uniqueItems': True}
    apply = obj({'identity': {'$ref': 'dossierSagaIdentityV1'}, 'sourceVersion': uuid,
                 'asOf': {'type': 'string', 'format': 'date-time'}, 'inputsJson': {'type': 'string', 'maxLength': 48000},
                 'credentialIds': refs, 'inputFingerprint': digest})
    receipt = obj({**identity['properties'], 'participant': {'enum': list(PARTICIPANTS)},
                   'state': {'enum': ['NEW', 'SNAPSHOTTED', 'COMMITTED', 'ACKNOWLEDGED', 'RELEASED', 'COMPENSATED', 'CONFLICT']},
                   'inputFingerprint': text, 'effectVersion': text, 'credentialIds': refs,
                   'completionAcknowledged': {'type': 'boolean'}, 'ready': {'type': 'boolean'}, 'errorCode': text})
    snapshot = obj({**identity['properties'], 'participant': {'enum': list(PARTICIPANTS)},
                    'sourceVersion': uuid, 'facts': {'type': 'object'}})
    start = obj({'protocol': {'const': PROTOCOL}, 'version': {'const': 1}, 'workflowId': uuid,
                 'initializationId': uuid, 'applicantId': uuid, 'deadlineAt': {'type': 'string', 'format': 'date-time'}})
    schemas = {'dossierSagaIdentityV1': identity, 'dossierSagaApplyV1': apply,
               'dossierSagaReceiptV1': receipt, 'dossierSagaSnapshotV1': snapshot, 'dossierSagaStartV1': start}
    protocol = {'protocol': PROTOCOL, 'version': 1, 'grade': 9, 'coordinator': 'message-broker',
        'participants': {k: {'stepId': v[1]} for k, v in PARTICIPANTS.items()}, 'commands': COMMANDS,
        'generationPath': 'DOSSIER_SAGA_V1', 'applyOrder': list(PARTICIPANTS),
        'compensationOrder': list(reversed(PARTICIPANTS)), 'releaseOrder': list(PARTICIPANTS),
        'workflowStates': ['RUNNING', 'COMPENSATING', 'INTERVENTION', 'SUCCEEDED', 'COMPENSATED'],
        'schemas': schemas,
        'identityFingerprint': 'SHA256 of 4-byte unsigned big-endian length-prefixed UTF8 fields: protocol, workflowId, initializationId, applicantId. UUIDs lowercase canonical, nonzero.',
        'inputFingerprint': 'Same encoding: protocol, workflowId, initializationId, applicantId, stepId, fingerprint, sourceVersion, asOf, inputsJson, followed by lexicographically sorted credentialIds. Excludes inputFingerprint itself.',
        'inputsJson': 'Broker serializes the full agreed Applicant/Record snapshots once as a JSON object keyed by canonical service name; persists and reuses the exact UTF8 string, never regenerates it on retry. Credential validates snapshots, generation paths, identities and reliable source revisions; other participants preserve the string fingerprint without interpreting document inputs.',
        'credentialApply': 'credentialIds=[] in request; generates 1..32 stable references from inputsJson/asOf and persists documents, provenance, receipt, generation ownership and outbox in one ordinary local transaction. Do not publish legacy callbacks or global READY.',
        'metadataApply': 'credentialIds must be the exact nonempty Credential receipt references. Validate bound initialization/sourceVersion; insert only separate workflow-owned metadata, receipt and outbox in one ordinary transaction. Academic truth and existing immutable receipts remain unchanged.',
        'snapshot': 'Requires existing full persisted initialization; atomically binds exclusive DOSSIER_SAGA_V1 generation ownership and workflow. Persist exact snapshot for retry. facts.generationPath=DOSSIER_SAGA_V1 is mandatory for every participant. No document creation at snapshot.',
        'receiptRules': '200 is business outcome only after local commit. Echo all identity fields exactly. inputFingerprint/effectVersion empty until apply, credentialIds empty until documents/references committed. COMMITTED/ACKNOWLEDGED/RELEASED have nonzero UUID effectVersion and 1..32 references. ready iff RELEASED; completionAcknowledged iff ACKNOWLEDGED or RELEASED. errorCode empty except CONFLICT. Reject malformed/mismatched receipts as ambiguous, never as completion.',
        'idempotency': 'Serialize commands per workflow. Persist immutable identity and first successful apply input. Same input returns current persisted outcome including terminal tombstones; different identity/input returns 409 SAGA_CONFLICT. Snapshot retry returns original snapshot, not changed facts. status for unseen identity creates NEW journal only. compensate for unseen/snapshotted work creates durable COMPENSATED tombstone; late snapshot/apply/acknowledge/release cannot revive it. A late identical apply returns COMPENSATED/CONFLICT, never COMMITTED.',
        'compensation': 'Reverse order, including any dispatched step with ambiguous outcome: resolve by status/idempotent replay first. Atomically check ownership, stored effectVersion and exact owned metadata/document versions, remove only workflow-owned data and cancel its outbox, persist COMPENSATED tombstone/receipt. Preserve pre-existing resources and later edits. If owned data changed or disappeared unexpectedly, cancel completion outbox and persist CONFLICT with COMPENSATION_CONFLICT; respond 409; status returns that durable state. Broker persists INTERVENTION and never claims successful rollback. No compensation after RELEASED.',
        'finalization': 'After every COMMITTED business receipt, obtain all ACKNOWLEDGED receipts (still ready=false). Broker commits immutable SUCCEEDED before any release; release Credential,Record,Applicant in that order. Retry all release failures after finalization, never compensate. No global simultaneous visibility promise.',
        'recovery': 'Before each dispatch persist exact request, attempt count, next retry instant, trace and receipts; fsync local journal before admission/progress acknowledgment. 429/5xx/timeout/disconnect/invalid receipt are ambiguous: status query or identical replay, never immediate rollback. 409 SAGA_BUSY is retryable. Deterministic rejection is followed by reverse compensation and terminal tombstones. Workflow deadline may initiate compensation only after outcome resolution; per-command budgets remain independent. Persist exponential backoff capped at 60 seconds and recover after restart. No wall-clock participant rollback.',
        'deadlines': 'Start deadlineAt immutable UTC, future and at most seven days on new admission. Existing workflow replay allowed after deadline. Per-command target=500ms, broker=750ms, caller=1000ms; fresh command deadlines on recovery, not original expired transport deadline.',
        'readiness': 'False from saga initialization through execution/compensation/conflict; Applicant profile to Session stays 202 until RELEASED. Outbox intent commits with local effect; receivers consult workflow identity/current state/version. Terminal tombstones are retained without automatic expiry.',
        'controlApi': {'start': 'POST /internal/v1/dossiers/saga/v1', 'status': 'GET /internal/v1/dossiers/saga/v1/{workflowId}',
                       'allowedCallers': list(PARTICIPANTS), 'publisherIdentity': 'message-broker reserved; no external caller token',
                       'startResponse': '202 with durable workflow status; replay exact input 202; conflicting input 409. Status 200, missing 404.',
                       'statusFields': ['protocol','version','workflowId','initializationId','applicantId','deadlineAt','state','ready','snapshots','requests','receipts','acknowledged','released','compensated','retry','lastError'],
                       'statusSemantics': 'Identity/start fields echoed; maps keyed by participant; snapshots/requests/receipts immutable accepted input/outcomes; acknowledged/released/compensated map participant to validated receipt. retry map participant:command to attempts,nextAttemptAt. lastError null or sanitized participant/command/status/code; ready iff SUCCEEDED and all releases acknowledged. No secret/driver details.'},
        'errors': {'400 INVALID_SAGA': 'Malformed protocol/identity/input/fingerprint', '401 UNAUTHENTICATED': 'Target credential required',
                   '403 SERVICE_CALL_FORBIDDEN': 'Only message-broker may drive participants',
                   '409 SAGA_CONFLICT': 'Immutable identity/input mismatch', '409 SAGA_BUSY': 'Retry serialized command',
                   '409 INITIALIZATION_REQUIRED': 'Existing persisted initialization required', '409 GENERATION_PATH_CONFLICT': 'Another path/workflow owns generation',
                   '409 SOURCE_VERSION_CONFLICT': 'Current authoritative source changed', '409 SAGA_TERMINAL': 'Terminal workflow cannot acknowledge/release/snapshot',
                   '409 NOT_COMMITTED': 'Business effect required', '409 COMPLETION_PENDING': 'Completion acknowledgment required',
                   '409 COMPENSATION_CONFLICT': 'Persisted conflict requires intervention', '409 ALREADY_RELEASED': 'Finalized work cannot compensate',
                   '503 SAGA_STORAGE_UNAVAILABLE': 'Ambiguous: resolve by status/replay', '504 TASK_TIMEOUT': 'Ambiguous command deadline'},
        'preservation': 'Additive protocol. Never reinterpret existing LEGACY or DOSSIER_V1 initialization, 2PC journal, receipts or evidence. No PREPARE, COMMIT PREPARED or ROLLBACK PREPARED in saga handlers.'}
    write = lambda path, value: (ROOT / path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    write('contracts/dossier/saga-v1.json', protocol)
    catalog = json.loads((ROOT / 'contracts/http/service-operations.json').read_text(encoding='utf-8'))
    catalog['schemas'].update(schemas)
    catalog['operations'] = [o for o in catalog['operations'] if '.dossierSaga.' not in o['name']]
    ids = ['a0000000-0000-4000-8000-00000000000' + str(i) for i in range(1, 5)]
    for service, (prefix, step, segment) in PARTICIPANTS.items():
        id = dict(protocol=PROTOCOL, version=1, workflowId=ids[0], initializationId=ids[1], applicantId=ids[2], stepId=step,
                  fingerprint=fields(PROTOCOL, *ids[:3]))
        request = dict(identity=id, sourceVersion=ids[3], asOf='2026-11-26T00:00:00Z',
                       inputsJson='{}', credentialIds=[] if prefix == 'credential' else ['c0000000-0000-4000-8000-000000000001'])
        request['inputFingerprint'] = fields(PROTOCOL, *ids[:3], step, id['fingerprint'], ids[3], request['asOf'], request['inputsJson'], *sorted(request['credentialIds']))
        for command in COMMANDS:
            name = prefix + '.dossierSaga.' + command
            path = '/internal/v1/' + segment + '/dossier/saga/v1/' + command
            op = dict(name=name, status='candidate', statusEvidence='Task 9 executable contract; participant implementation/joint acceptance required.',
                      owner=service, method='POST', path=path, callers=['message-broker'],
                      request='dossierSagaApplyV1' if command == 'apply' else 'dossierSagaIdentityV1',
                      response='dossierSagaSnapshotV1' if command == 'snapshot' else 'dossierSagaReceiptV1',
                      semantics='dossier-saga-v1 ordinary local transaction; see contracts/dossier/saga-v1.json for exact durable outcomes.',
                      budgetsMs=dict(target=500, gateway=750, broker=750, caller=1000),
                      idempotency=protocol['idempotency'], retry=protocol['recovery'], errors=protocol['errors'])
            catalog['operations'].append(op)
            phase = {'apply':'COMMITTED','status':'COMMITTED','compensate':'COMPENSATED','acknowledge':'ACKNOWLEDGED','release':'RELEASED'}.get(command)
            response = {**id, 'participant':service, 'state':phase, 'inputFingerprint':request['inputFingerprint'],
                        'effectVersion':ids[3], 'credentialIds':['c0000000-0000-4000-8000-000000000001'],
                        'completionAcknowledged':command in ['acknowledge','release'], 'ready':command=='release', 'errorCode':''}
            if command == 'snapshot':
                response = {**id,'participant':service,'sourceVersion':ids[3],'facts':{'generationPath':'DOSSIER_SAGA_V1'}}
            write('contracts/http/examples/' + name + '.json', {'operation':name,
                'note':'Synthetic shape/fingerprint example. For Credential apply, inputsJson must contain actual complete Applicant/Record snapshots; {} is not executable business data.',
                'request':{'method':'POST','path':path,'headers':{'Authorization':'Bearer <target internal credential>', 'X-Service-Name':'message-broker','X-Trace-Id':'dossier-saga-v1-example','Content-Type':'application/json'},
                           'body':request if command=='apply' else id}, 'response':{'status':200,'body':response}})
    write('contracts/http/service-operations.json', catalog)


if __name__ == '__main__':
    main()
