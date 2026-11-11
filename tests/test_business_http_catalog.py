"""Static candidate catalog consistency; this does not prove peer integration."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BusinessCatalogTests(unittest.TestCase):
    def test_catalog_has_exact_openapi_operations_and_no_guessed_peer_routes(self):
        catalog = json.loads((ROOT / 'contracts/http/service-operations.json').read_text())
        api = json.loads((ROOT / 'contracts/http/openapi.json').read_text())
        for operation in catalog['operations']:
            if operation['owner'] not in {'credential-service', 'rules-service'}:
                continue
            route = api['paths'][operation['path'].split('?')[0]][operation['method'].lower()]
            self.assertEqual(route['operationId'], operation['name'])
            expected_status = ('candidate' if operation['name'].startswith('rules.shift.')
                               else 'implemented-pending-review')
            self.assertEqual(operation['status'], expected_status)
            self.assertTrue(route['security'])
        self.assertFalse((ROOT / 'contracts/business-http/operations.json').exists())
        self.assertTrue(catalog['ownedDrafts']['incompatibilities'])

    def test_membership_schema_and_budgets_preserve_candidate(self):
        catalog = json.loads((ROOT / 'contracts/http/service-operations.json').read_text())
        api = json.loads((ROOT / 'contracts/http/openapi.json').read_text())
        operation = next(o for o in catalog['operations'] if o['name'] == 'session.verifyMembership')
        self.assertEqual(operation['path'], '/internal/v1/session-memberships/verify')
        budgets = catalog['transport']['budgetsMs']
        self.assertEqual({key: budgets[key] for key in ('caller', 'gateway', 'target')},
                         {'caller': 1000, 'gateway': 750, 'target': 500})
        self.assertEqual(set(catalog['ownedDrafts']['membershipCallerRequests']), {'credential-service', 'rules-service'})
        self.assertEqual(set(api['components']['schemas']['membershipResponse']['required']), {'member', 'role', 'recordAccess', 'channels'})

    def test_peer_reconciliation_is_preserved_without_promoting_legacy_workflow(self):
        catalog = json.loads((ROOT / 'contracts/http/service-operations.json').read_text())
        operations = {operation['name']: operation for operation in catalog['operations']}
        for name in ('session-state.get', 'applicant.getProfile', 'applicant.getClaims',
                     'record.enrollmentFacts', 'rules.shift.bind', 'rules.shift.read'):
            self.assertIn(name, operations)
        self.assertIn('sessionId', catalog['schemas']['ownedApplicantInitialized']['properties']['payload']['required'])
        self.assertIn('ownedInitializationStatus', catalog['schemas'])
        self.assertIn('ownedReceipt', catalog['schemas'])
        self.assertTrue(catalog['ownedDrafts']['incompatibilities'])


if __name__ == '__main__':
    unittest.main()
