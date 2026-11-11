import copy
import json
import unittest
from pathlib import Path
from scripts import validate_http_contracts as contract


class OwnedContractsTest(unittest.TestCase):
    def test_initialization_vectors_match_the_executable_schema(self):
        catalog = contract.load_catalog()
        path = Path(__file__).resolve().parents[1] / "contracts/http/test-vectors/initialization-v1.json"
        for vector in json.loads(path.read_text()):
            self.assertEqual([], contract.validate(vector["event"], {"$ref": "ownedApplicantInitialized"}, catalog["schemas"]))
            broken = copy.deepcopy(vector["event"])
            del broken["payload"]["sessionId"]
            self.assertTrue(contract.validate(broken, {"$ref": "ownedApplicantInitialized"}, catalog["schemas"]))
            broken = copy.deepcopy(vector["event"])
            broken["payload"]["identity"]["studentId"] = "unsafe?"
            self.assertTrue(contract.validate(broken, {"$ref": "ownedApplicantInitialized"}, catalog["schemas"]))

    def test_patterns_uniqueness_and_pending_responses_are_checked(self):
        self.assertTrue(contract.validate("bad", {"type": "string", "pattern": "^[a-f0-9]{64}$"}, {}))
        self.assertEqual([], contract.validate("a" * 64, {"pattern": "^[a-f0-9]{64}$"}, {}))
        self.assertTrue(contract.validate(["major", "major"], {"uniqueItems": True}, {}))
        catalog = contract.load_catalog()
        broken = copy.deepcopy(catalog)
        broken["operations"][0]["successResponses"] = {"404": "not-a-schema"}
        self.assertTrue(any("invalid success" in e for e in contract.check_catalog(broken)))
        spec = contract.openapi(catalog)
        response = spec["paths"]["/internal/v1/applicants/{applicantId}/profile"]["get"]["responses"]
        self.assertEqual("#/components/schemas/ownedReadiness", response["202"]["content"]["application/json"]["schema"]["$ref"])


if __name__ == "__main__":
    unittest.main()
