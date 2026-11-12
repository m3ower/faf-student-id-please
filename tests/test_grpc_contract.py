import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from scripts import validate_grpc_contract as contract
from scripts.validate_grpc_contract import PROTO, ROOT, TRANSPORTS, check, check_proto, check_transports


class GrpcContractTests(unittest.TestCase):
    def setUp(self):
        self.proto = (ROOT / PROTO).read_text(encoding="utf-8")
        self.transports = json.loads((ROOT / TRANSPORTS).read_text(encoding="utf-8"))
        self.catalog = json.loads((ROOT / "contracts/messaging/catalog.json").read_text(encoding="utf-8"))

    def test_current_contract(self):
        delivery, _ = check()
        self.assertEqual(len(delivery), 8)
        self.assertEqual(check_proto(self.proto), contract.SERVICES)

    def test_proto_changes_that_break_the_wire_are_refused(self):
        cases = [
            self.proto.replace('syntax = "proto3";', 'syntax = "proto2";'),
            self.proto.replace("package studentid.messaging.v1;", "package studentid.v1;"),
            self.proto.replace("rpc Deliver(Delivery) returns (Reply);", ""),
            self.proto.replace("rpc GetResult(ResultRequest) returns (Result);",
                               "rpc GetResult(ResultRequest) returns (Reply);"),
            self.proto.replace("string deadline_at = 10;", "string deadline_at = 13;"),
            self.proto.replace("bytes body_json = 2;", "bytes body = 2;"),
            self.proto.replace("string trace_id = 5;", "string trace_id = 4;"),
            self.proto.replace("syntax = \"proto3\";", "syntax = \"proto3\";\nimport \"other.proto\";"),
            self.proto.replace("message ListTopicsRequest {", "message ListTopicsRequestX {"),
        ]
        for text in cases:
            self.assertNotEqual(text, self.proto)
            with self.assertRaises(ValueError):
                check_proto(text)

    def test_transport_list_must_cover_exactly_the_consumer_groups(self):
        cases = [
            lambda t: t["delivery"].pop("rules-service"),
            lambda t: t["delivery"].update({"gateway-service": "http"}),
            lambda t: t["delivery"].update({"rules-service": "rest"}),
            lambda t: t.update(grpcPortOffset=2000),
            lambda t: t["broker"].update(grpcPort=9999),
            lambda t: t.update(version=2),
            lambda t: t.update(extra=True),
            lambda t: t.update(delivery=dict(reversed(list(t["delivery"].items())))),
            lambda t: t["health"].update(maxAgeMs=30000),
            lambda t: t["health"].update(service="grpc.health.v1.Health"),
            lambda t: t.pop("protoSha256"),
        ]
        for change in cases:
            broken = copy.deepcopy(self.transports)
            change(broken)
            with self.assertRaises(ValueError):
                check_transports(broken, self.catalog)
        flipped = copy.deepcopy(self.transports)
        flipped["delivery"]["moderation-service"] = "grpc"
        self.assertEqual(check_transports(flipped, self.catalog)["moderation-service"], "grpc")

    def test_the_pin_matches_the_proto_and_ignores_line_endings(self):
        self.assertEqual(self.transports["protoSha256"], contract.proto_sha256((ROOT / PROTO).read_bytes()))
        crlf = (ROOT / PROTO).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        self.assertEqual(contract.proto_sha256(crlf), self.transports["protoSha256"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (PROTO, TRANSPORTS, Path("contracts/messaging/catalog.json")):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, root / relative)
            (root / PROTO).write_text(self.proto + "// drift\n", encoding="utf-8")
            with mock.patch.object(contract, "compile_proto", return_value=None):
                with self.assertRaisesRegex(ValueError, "protoSha256"):
                    check(root)
            vendored = root / "vendored.proto"
            vendored.write_text(self.proto, encoding="utf-8")
            with mock.patch("sys.argv", ["validate", "--vendored", str(vendored)]), mock.patch("builtins.print"):
                contract.main()
            vendored.write_text(self.proto + "// fork\n", encoding="utf-8")
            with mock.patch("sys.argv", ["validate", "--vendored", str(vendored)]):
                with self.assertRaises(SystemExit):
                    contract.main()

    def test_broker_copies_must_be_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            broker = Path(tmp)
            (broker / "contracts").mkdir()
            shutil.copyfile(ROOT / PROTO, broker / "contracts/messaging.proto")
            shutil.copyfile(ROOT / TRANSPORTS, broker / "contracts/transports.json")
            check(broker_root=broker)
            changed = copy.deepcopy(self.transports)
            changed["delivery"]["rules-service"] = "http" if self.transports["delivery"]["rules-service"] == "grpc" else "grpc"
            (broker / "contracts/transports.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "transports copy"):
                check(broker_root=broker)
            shutil.copyfile(ROOT / TRANSPORTS, broker / "contracts/transports.json")
            (broker / "contracts/messaging.proto").write_text(self.proto + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "proto copy"):
                check(broker_root=broker)

    def test_compiler_is_optional_but_reported(self):
        with mock.patch.object(contract.importlib.util, "find_spec", return_value=None):
            self.assertIsNone(contract.compile_proto(ROOT))
            with mock.patch("sys.argv", ["validate", "--require-compiler"]):
                with self.assertRaises(SystemExit):
                    contract.main()
            with mock.patch("sys.argv", ["validate"]), mock.patch("builtins.print") as printed:
                contract.main()
            self.assertIn("not compiled", printed.call_args[0][0])

    @unittest.skipIf(contract.importlib.util.find_spec("grpc_tools") is None, "grpcio-tools not installed")
    def test_proto_compiles_with_the_agreed_services(self):
        self.assertEqual(contract.compile_proto(ROOT), 11)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / PROTO.parent).mkdir(parents=True)
            (root / PROTO).write_text(self.proto.replace("rpc Deliver(Delivery) returns (Reply);",
                                                         "rpc Deliver(Delivery) returns (Result);"), encoding="utf-8")
            with self.assertRaises(ValueError):
                contract.compile_proto(root)
            (root / PROTO).write_text(self.proto.replace("message Reply {", "message Reply { oops"), encoding="utf-8")
            with self.assertRaises(ValueError):
                contract.compile_proto(root)


if __name__ == "__main__":
    unittest.main()
