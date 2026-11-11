import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import validate_http_contracts as v


class CatalogTest(unittest.TestCase):

    def setUp(self):
        self.catalog = v.load_catalog()

    def test_published_catalog_examples_and_openapi_are_consistent(self):
        self.assertEqual(v.check_catalog(self.catalog), [])
        self.assertEqual(v.check_examples(self.catalog), [])
        self.assertEqual(v.OPENAPI.read_text(encoding="utf-8"), v.render(v.openapi(self.catalog)))
        self.assertEqual(v.main([]), 0)

    def test_the_agreed_membership_path_is_preserved(self):
        op = next(o for o in self.catalog["operations"] if o["name"] == "session.verifyMembership")
        self.assertEqual((op["method"], op["path"]), ("POST", "/internal/v1/session-memberships/verify"))

    def test_every_target_has_its_own_credential(self):
        envs = [t["targetCredentialEnv"] for t in self.catalog["targets"].values()]
        self.assertEqual(len(envs), len(set(envs)))

    def test_catalog_rules_catch_mistakes(self):
        bad = copy.deepcopy(self.catalog)
        ops = bad["operations"]
        ops.append(copy.deepcopy(ops[0]))                     # duplicate name and route
        ops[1]["callers"] = ["nobody-service"]                # unknown caller
        ops[2]["callers"] = [ops[2]["owner"]]                 # owner calling itself
        ops[3]["path"] = "/api/v1/public"                     # not an internal path
        ops[4]["response"] = "missingSchema"
        ops[5]["status"] = "live"                             # unknown status
        bad["targets"]["rules-service"]["targetCredentialEnv"] = "SESSION_INTERNAL_TOKEN"
        problems = "\n".join(v.check_catalog(bad))
        for expected in ("duplicate operation name", "same method and path", "not a known service",
                         "does not call itself", "/internal/v1/", "missingSchema", "unknown status",
                         "shared with another target"):
            self.assertIn(expected, problems)

    def test_schema_validation(self):
        schemas = self.catalog["schemas"]
        ok = {"sessionId": "55555555-5555-5555-5555-555555555555", "playerId": "22222222-2222-2222-2222-222222222222"}
        self.assertEqual(v.validate(ok, {"$ref": "membershipRequest"}, schemas), [])
        errors = v.validate({"sessionId": "nope", "extra": 1}, {"$ref": "membershipRequest"}, schemas)
        self.assertTrue(any("not a UUID" in e for e in errors))
        self.assertTrue(any("missing required 'playerId'" in e for e in errors))
        self.assertTrue(any("unexpected property 'extra'" in e for e in errors))
        env = {"eventId": "59f5ed3b-e286-3554-98bb-a02ce878769e", "type": "DecisionRecorded",
               "occurredAt": "yesterday", "producer": "rules-service", "version": 2,
               "payload": {"decisionId": "x", "correct": "yes"}}
        errors = "\n".join(v.validate(env, {"$ref": "decisionRecordedEnvelope"}, schemas))
        for expected in ("RFC 3339", "producer", "version", "payload.decisionId", "payload.correct", "missing required"):
            self.assertIn(expected, errors)
        self.assertTrue(v.validate({"delta": True}, {"properties": {"delta": {"type": "integer"}}}, schemas))
        self.assertTrue(v.validate([1, 2, 3], {"type": "array", "maxItems": 2}, schemas))
        self.assertTrue(v.validate(5, {"type": "integer", "minimum": 10}, schemas))
        self.assertTrue(v.validate("", {"type": "string", "minLength": 1}, schemas))
        self.assertTrue(v.validate(1, {"$ref": "nothing"}, schemas))

    def test_examples_with_secrets_or_wrong_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for f in v.EXAMPLES.glob("*.json"):
                (folder / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            target = folder / "rules.evaluate.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["request"]["headers"]["Authorization"] = "Bearer abcdefghijklmnopqrstuvwxyz0123456789"
            doc["request"]["path"] = "/internal/v1/rules/somewhere-else"
            doc["response"]["body"]["recommendedAction"] = "PARDON"
            target.write_text(json.dumps(doc), encoding="utf-8")
            (folder / "session.applyScoreChange.json").unlink()
            problems = "\n".join(v.check_examples(self.catalog, folder))
            for expected in ("real bearer credential", "request line does not match", "PARDON",
                             "session.applyScoreChange: no example"):
                self.assertIn(expected, problems)

    def test_check_mode_validates_a_captured_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "ack.json"
            good.write_text(json.dumps({"eventId": "59f5ed3b-e286-3554-98bb-a02ce878769e", "status": "PROCESSED"}))
            self.assertEqual(v.main(["--check", "dms.decisionRecorded", "response", str(good)]), 0)
            good.write_text(json.dumps({"eventId": "59f5ed3b-e286-3554-98bb-a02ce878769e", "status": "MAYBE"}))
            self.assertEqual(v.main(["--check", "dms.decisionRecorded", "response", str(good)]), 1)
            self.assertEqual(v.main(["--check", "record.enrollmentFacts", "response", str(good)]), 1)
            record = json.loads((v.EXAMPLES / "record.enrollmentFacts.json").read_text())
            good.write_text(json.dumps(record["response"]["body"]))
            self.assertEqual(v.main(["--check", "record.enrollmentFacts", "response", str(good)]), 0)


if __name__ == "__main__":
    unittest.main()
