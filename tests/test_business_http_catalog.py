"""Static candidate catalog consistency; this does not prove peer integration."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BusinessCatalogTests(unittest.TestCase):
    def test_catalog_has_exact_openapi_operations_and_no_guessed_peer_routes(self):
        catalog = json.loads((ROOT / 'contracts/business-http/operations.json').read_text())
        api = json.loads((ROOT / 'contracts/business-http/openapi.json').read_text())
        self.assertEqual(catalog['status'], 'not-approved-not-integration-ready')
        for operation in catalog['operations']:
            route = api['paths'][operation['path']][operation['method'].lower()]
            self.assertEqual(route['operationId'], operation['operationId'])
            self.assertEqual(operation['automaticRetries'], 0)
            self.assertTrue(route['security'])
        self.assertEqual(len(api['paths']), len(catalog['operations']))
        for dependency in catalog['missingReceiverOwnedContracts']:
            self.assertNotIn('path', dependency)

    def test_membership_schema_and_budgets_preserve_candidate(self):
        catalog = json.loads((ROOT / 'contracts/business-http/operations.json').read_text())
        api = json.loads((ROOT / 'contracts/business-http/openapi.json').read_text())
        operation = catalog['operations'][0]
        self.assertEqual(operation['path'], '/internal/v1/session-memberships/verify')
        self.assertEqual((operation['callerBudgetMs'], operation['gatewayBudgetMs'], operation['receiverBudgetMs']), (1000, 750, 500))
        self.assertEqual(set(operation['currentlyAllowedCallers']), {'university-record-service', 'discord-dms-service'})
        self.assertEqual(set(operation['requestedAdditionalCallers']), {'credential-service', 'rules-service'})
        self.assertEqual(set(api['components']['schemas']['MembershipResponse']['required']), {'member', 'role', 'recordAccess', 'channels'})


if __name__ == '__main__':
    unittest.main()
