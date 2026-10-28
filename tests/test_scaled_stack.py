import json
import unittest
from unittest.mock import patch

from scripts.scaled_stack import SERVICES, Stack


class FakeStack(Stack):
    def __init__(self):
        self.calls = []
        self.entries = [{"serviceName": "player-service", "baseUrl": "http://player-service-2:8080", "instanceId": "one"}]

    def compose(self, *arguments, data=None, replicas=False):
        self.calls.append((arguments, replicas))
        return ""

    def expected(self, names):
        return [{"serviceName": name.removesuffix("-2"), "baseUrl": "http://" + name + ":8080"} for name in names]

    def registry(self, *arguments, data=None):
        self.calls.append((arguments, data))
        if arguments == ("list",): return json.dumps({"instances": self.entries})
        if arguments[0] == "remove": self.entries = []
        return ""


class ScaledStackTest(unittest.TestCase):
    def test_primary_readiness_precedes_second_set(self):
        stack = FakeStack()
        stack.up()
        self.assertEqual(stack.calls[0], (("up", "-d"), False))
        first = json.loads(stack.calls[1][1])
        self.assertEqual(len(first), len(SERVICES))
        self.assertEqual({item["serviceName"] for item in first}, set(SERVICES))
        self.assertTrue(all(not item["baseUrl"].split("://")[1].split(":")[0].endswith("-2") for item in first))
        self.assertEqual(stack.calls[2], (("up", "-d"), True))
        self.assertEqual(len(json.loads(stack.calls[3][1])), 2 * len(SERVICES))

    def test_remove_deregisters_then_stops_and_checks_for_registration_race(self):
        stack = FakeStack()
        stack.remove("player-service-2")
        self.assertEqual(stack.calls[0][0], ("list",))
        self.assertEqual(stack.calls[1][0], ("remove", "player-service", "one"))
        self.assertEqual(stack.calls[2], (("stop", "--timeout", "5", "player-service-2"), True))
        self.assertEqual(stack.calls[3][0], ("list",))

    def test_add_waits_for_primary_before_second_schema_start(self):
        stack = FakeStack()
        stack.add("rules-service-2")
        self.assertEqual(json.loads(stack.calls[0][1])[0]["baseUrl"], "http://rules-service:8080")
        self.assertEqual(stack.calls[1], (("up", "-d", "rules-service-2"), True))

    def test_infrastructure_cannot_be_stopped_by_replica_command(self):
        for name in ("postgres", "service-discovery", "gateway-service", "player-service-3", "../outside", None):
            with self.assertRaises(ValueError): FakeStack().remove(name)

    def test_compose_failures_do_not_echo_resolved_credentials(self):
        result = type("Result", (), {"returncode": 1, "stdout": "private-secret", "stderr": "private-secret"})()
        with patch("scripts.scaled_stack.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "Compose operation failed") as raised:
                Stack(".env", "isolated-test").compose("config")
            self.assertNotIn("private-secret", str(raised.exception))


if __name__ == "__main__": unittest.main()
