"""Executable correlation/fingerprint vectors for Credential and owned participants."""
import copy
import json
from pathlib import Path
import unittest
from scripts.build_dossier_saga_contract import fields, PROTOCOL, PARTICIPANTS, COMMANDS
from scripts.validate_http_contracts import validate

ROOT = Path(__file__).resolve().parents[1]


class SagaContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'contracts/http/service-operations.json').read_text())

    def test_grants_are_additive_and_outside_services_unchanged(self):
        operations = [o for o in self.catalog['operations'] if '.dossierSaga.' in o['name']]
        self.assertEqual(len(operations), 18)
        self.assertEqual({o['owner'] for o in operations}, set(PARTICIPANTS))
        for op in operations:
            self.assertEqual(op['callers'], ['message-broker'])
            self.assertEqual(op['method'], 'POST')
        self.assertEqual(len([o for o in self.catalog['operations'] if '.dossier.' in o['name']]), 24)

    def test_apply_fingerprints_bind_full_exact_inputs_and_references(self):
        for prefix, step, segment in PARTICIPANTS.values():
            example = json.loads((ROOT / ('contracts/http/examples/' + prefix + '.dossierSaga.apply.json')).read_text())
            body = example['request']['body']; identity = body['identity']
            correlated = [identity[k] for k in ['workflowId', 'initializationId', 'applicantId']]
            self.assertEqual(identity['fingerprint'], fields(PROTOCOL, *correlated))
            raw = [PROTOCOL, *correlated, step, identity['fingerprint'], body['sourceVersion'], body['asOf'], body['inputsJson'], *sorted(body['credentialIds'])]
            self.assertEqual(body['inputFingerprint'], fields(*raw))
            for index in range(len(raw)):
                changed = raw.copy(); changed[index] += 'x'
                self.assertNotEqual(fields(*changed), body['inputFingerprint'])

    def test_schema_rejects_wrong_protocol_and_unrecognized_input(self):
        example = json.loads((ROOT / 'contracts/http/examples/applicant.dossierSaga.apply.json').read_text())['request']['body']
        schemas = self.catalog['schemas']
        self.assertFalse(validate(example, schemas['dossierSagaApplyV1'], schemas))
        for change in [lambda b: b['identity'].update(protocol='dossier-v1'),
                       lambda b: b['identity'].update(version=True),
                       lambda b: b.update(sourceVersion='envelope-hash'),
                       lambda b: b.update(unrecognized=True)]:
            invalid = copy.deepcopy(example); change(invalid)
            self.assertTrue(validate(invalid, schemas['dossierSagaApplyV1'], schemas))


if __name__ == '__main__':
    unittest.main()
