"""Validate the Lab 4 Grade 8 gRPC messaging contract.

The proto declares the Broker and consumer services with their RPCs; transports.json names
every consumer group of the messaging catalog exactly once, with http or grpc delivery; and
with --broker-root the Broker's bundled copies are byte-identical. When grpcio-tools is
installed (CI), the proto is also compiled and its descriptors are checked.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROTO = Path("contracts/proto/studentid/messaging/v1/messaging.proto")
TRANSPORTS = Path("contracts/proto/transports.json")
SERVICES = {
    "MessageBroker": {"Publish": ("Envelope", "Result"), "GetResult": ("ResultRequest", "Result"),
                      "ListTopics": ("ListTopicsRequest", "TopicList")},
    "MessageConsumer": {"Deliver": ("Delivery", "Reply")},
}
# Fields every receiver and the Broker rely on, by number: renumbering breaks the wire.
FIELDS = {
    "Envelope": {"message_id": 1, "schema_version": 2, "kind": 3, "topic": 4, "trace_id": 5,
                 "correlation_id": 6, "causation_id": 7, "deadline_at": 8, "arguments": 9, "payload_json": 10},
    "Delivery": {"message_id": 1, "kind": 2, "topic": 3, "group": 4, "operation": 5, "publisher": 6,
                 "trace_id": 7, "correlation_id": 8, "causation_id": 9, "deadline_at": 10, "arguments": 11,
                 "payload_json": 12},
    "Reply": {"status": 1, "body_json": 2, "content_type": 3},
    "Result": {"message_id": 1, "correlation_id": 2, "state": 3, "groups": 4},
    "GroupResult": {"state": 1, "acknowledged": 2, "status": 3, "body": 4, "headers": 5},
}


def parse(text):
    """Services, messages and their numbered fields from proto3 text (comments stripped)."""
    text = re.sub(r"//[^\n]*", "", text)
    if not re.search(r'^\s*syntax\s*=\s*"proto3"\s*;', text, re.M):
        raise ValueError("messaging.proto must be proto3")
    if not re.search(r"^\s*package\s+studentid\.messaging\.v1\s*;", text, re.M):
        raise ValueError("messaging.proto must be package studentid.messaging.v1")
    if re.search(r"^\s*import\s", text, re.M):
        raise ValueError("messaging.proto must not import other files")
    services = {}
    for name, body in re.findall(r"service\s+(\w+)\s*\{(.*?)\}", text, re.S):
        services[name] = {rpc: (req, res) for rpc, req, res in
                          re.findall(r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)", body)}
    messages = {}
    for name, body in re.findall(r"message\s+(\w+)\s*\{(.*?)\}", text, re.S):
        fields = {}
        for field, number in re.findall(r"(\w+)\s*=\s*(\d+)\s*;", body):
            if field in fields or int(number) in fields.values():
                raise ValueError(f"{name}: duplicate field name or number")
            fields[field] = int(number)
        messages[name] = fields
    return services, messages


def check_proto(text):
    services, messages = parse(text)
    if services != SERVICES:
        raise ValueError("messaging.proto must declare exactly the agreed services and RPCs")
    for message, fields in FIELDS.items():
        actual = messages.get(message, {})
        if any(actual.get(field) != number for field, number in fields.items()):
            raise ValueError(f"{message}: agreed fields must keep their names and numbers")
    for rpc in SERVICES.values():
        for request, response in rpc.values():
            if request not in messages or response not in messages:
                raise ValueError(f"messaging.proto: message {request} or {response} is missing")
    return services


def check_transports(transports, catalog):
    groups = set()
    for binding in catalog["operations"].values():
        groups.add(binding["group"])
    for event in catalog["events"].values():
        groups.update(event["groups"])
    if set(transports) != {"version", "proto", "grpcPortOffset", "broker", "delivery"}:
        raise ValueError("transports.json: unexpected or missing keys")
    if transports["version"] != 1 or transports["proto"] != PROTO.as_posix():
        raise ValueError("transports.json: version 1 and the shared proto path are required")
    if transports["grpcPortOffset"] != 1000:
        raise ValueError("transports.json: the agreed gRPC port offset is 1000")
    broker = transports["broker"]
    if broker != {"service": "message-broker", "httpPort": 8093, "grpcPort": 8093 + 1000}:
        raise ValueError("transports.json: the Broker serves gRPC on its HTTP port + 1000")
    delivery = transports["delivery"]
    if set(delivery) != groups:
        raise ValueError("transports.json: delivery must name exactly the catalog's consumer groups")
    if list(delivery) != sorted(delivery) or any(value not in ("http", "grpc") for value in delivery.values()):
        raise ValueError("transports.json: sorted groups with http or grpc delivery are required")
    return delivery


def compile_proto(root):
    """Compile with grpcio-tools when it is installed; None when it is not."""
    if importlib.util.find_spec("grpc_tools") is None:
        return None
    from grpc_tools import protoc
    with tempfile.TemporaryDirectory() as out:
        status = protoc.main(["protoc", "-I" + str(root / "contracts/proto"), "--python_out=" + out,
                              "--descriptor_set_out=" + out + "/set.pb", str(root / PROTO)])
        if status != 0:
            raise ValueError("messaging.proto does not compile")
        from google.protobuf import descriptor_pb2
        files = descriptor_pb2.FileDescriptorSet.FromString(Path(out, "set.pb").read_bytes())
        proto = files.file[0]
        declared = {s.name: {m.name: (m.input_type.rsplit(".", 1)[1], m.output_type.rsplit(".", 1)[1])
                             for m in s.method} for s in proto.service}
        if proto.package != "studentid.messaging.v1" or declared != SERVICES:
            raise ValueError("compiled messaging.proto disagrees with the agreed services")
        return len(proto.message_type)


def check(root=ROOT, broker_root=None):
    proto_text = (root / PROTO).read_text(encoding="utf-8")
    check_proto(proto_text)
    transports = json.loads((root / TRANSPORTS).read_text(encoding="utf-8"))
    catalog = json.loads((root / "contracts/messaging/catalog.json").read_text(encoding="utf-8"))
    delivery = check_transports(transports, catalog)
    compiled = compile_proto(root)
    if broker_root:
        if (broker_root / "contracts/messaging.proto").read_bytes() != (root / PROTO).read_bytes():
            raise ValueError("Broker proto copy differs")
        if json.loads((broker_root / "contracts/transports.json").read_text(encoding="utf-8")) != transports:
            raise ValueError("Broker transports copy differs")
    return delivery, compiled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-root", type=Path)
    parser.add_argument("--require-compiler", action="store_true")
    args = parser.parse_args()
    delivery, compiled = check(broker_root=args.broker_root)
    if compiled is None and args.require_compiler:
        sys.exit("grpcio-tools is required to compile messaging.proto")
    grpc_groups = sorted(group for group, value in delivery.items() if value == "grpc")
    print(f"gRPC contract passed: {len(delivery)} consumer groups, gRPC delivery for "
          f"{', '.join(grpc_groups) or 'none yet'}; "
          + ("compiled " + str(compiled) + " messages" if compiled is not None else "not compiled (no grpcio-tools)"))


if __name__ == "__main__":
    main()
