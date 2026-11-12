import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.validate_messaging_contracts import ROOT, check, generate, subscriptions, validate_examples


class MessagingContractsTests(unittest.TestCase):
    def setUp(self):
        self.http = json.loads((ROOT / "contracts/http/service-operations.json").read_text(encoding="utf-8"))

    def test_current_catalog_and_per_owner_subscriptions(self):
        self.assertEqual(check(), (39, 5, 8))
        groups = subscriptions(generate(self.http))
        self.assertEqual(len(groups["applicant-service"]), 12)
        self.assertEqual(len(groups["university-record-service"]), 9)
        self.assertEqual(len(groups["session-service"]), 7)
        self.assertEqual(len(groups["player-service"]), 4)
        self.assertTrue(all(s["group"] == g for g, entries in groups.items() for s in entries))

    def test_get_query_projection_and_post_arguments(self):
        ops = generate(self.http)["operations"]
        get = ops["operation.applicant.getDeception.v1"]
        self.assertEqual(get["arguments"], ["applicantId", "sessionId"])
        self.assertEqual(get["query"], "sessionId={sessionId}")
        post = ops["operation.credential.initialization.recover.v1"]
        self.assertEqual(post["arguments"], ["eventId"])
        self.assertIsNone(post["bodySchema"])

    def test_examples_keep_original_business_schemas(self):
        validate_examples()

    def test_event_binding_cannot_expand_receiver_grants(self):
        bad = copy.deepcopy(self.http)
        next(o for o in bad["operations"] if o["name"] == "session.decisionRecorded")["callers"] = ["player-service"]
        with self.assertRaisesRegex(ValueError, "receiver-owned"):
            generate(bad)

    def test_requested_operations_are_not_grants(self):
        http = copy.deepcopy(self.http)
        http["operations"].append({"name": "unapproved", "status": "requested"})
        self.assertNotIn("operation.unapproved.v1", generate(http)["operations"])

    def test_drift_in_bindings_subscriptions_and_private_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "contracts/http").mkdir(parents=True)
            (root / "contracts/messaging").mkdir()
            (root / "contracts/http/service-operations.json").write_text(json.dumps(self.http), encoding="utf-8")
            policy = generate(self.http)
            target = root / "contracts/messaging/catalog.json"
            target.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bindings drifted"):
                check(root)
            target.write_text(json.dumps(policy), encoding="utf-8")
            reg = root / "contracts/messaging/subscriptions.json"
            reg.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lists drifted"):
                check(root)
            reg.write_text(json.dumps(subscriptions(policy)), encoding="utf-8")
            broker = root / "broker/contracts"
            broker.mkdir(parents=True)
            (broker / "messaging.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "messaging copy"):
                check(root, broker.parent)
            (broker / "messaging.json").write_text(json.dumps(policy), encoding="utf-8")
            (broker / "service-operations.json").write_text(json.dumps(self.http), encoding="utf-8")
            self.assertEqual(check(root, broker.parent), (39, 5, 8))
