"""Generate/check reviewed messaging bindings without accessing private repositories.

    python scripts/validate_messaging_contracts.py [--write] [--broker-root PATH]

Business methods, schemas, caller grants and budgets come from the existing HTTP
catalog. Only the event fan-out table below is new transport policy. This tool
does not grant a subscription, contact a service or rewrite a private repository.
"""

import argparse
import json
from pathlib import Path
import re
import sys
from uuid import UUID

# Support both direct execution and unittest's package import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_http_contracts import validate

ROOT = Path(__file__).resolve().parents[1]
HTTP = ROOT / "contracts/http/service-operations.json"
BINDINGS = ROOT / "contracts/messaging/catalog.json"
EVENTS = {
    "DecisionRecorded": ("moderation-service", {"session-service": "session.decisionRecorded",
                                              "discord-dms-service": "dms.decisionRecorded"}),
    "ShiftStarted": ("session-service", {"discord-dms-service": "dms.shiftStarted"}),
    "CredentialsReady": ("credential-service", {"applicant-service": "applicant.credentialsReady",
                                             "university-record-service": "record.credentialsReady"}),
    "SessionCompleted": ("session-service", {"player-service": "session-completions.record"}),
    "PlayerProgressed": ("player-service", {"session-service": "player-progressions.record"}),
}


def generate(http):
    operations = {}
    for op in http["operations"]:
        if op["status"] not in {"candidate", "implemented-pending-review"}:
            continue
        path, _, query = op["path"].partition("?")
        operations["operation." + op["name"] + ".v1"] = {
            "operation": op["name"], "group": op["owner"], "method": op["method"],
            "path": path, "query": query,
            "arguments": list(dict.fromkeys(re.findall(r"\{([^}]+)\}", op["path"]))),
            "bodySchema": op.get("request"), "callers": sorted(op["callers"]),
            "budgetMs": op.get("budgetsMs", http["transport"]["budgetsMs"])["broker"],
        }
    events = {"event." + name + ".v1": {"eventType": name, "publisher": producer, "groups": groups}
              for name, (producer, groups) in EVENTS.items()}
    by_name = {op["operation"]: op for op in operations.values()}
    for event in events.values():
        for group, operation in event["groups"].items():
            op = by_name[operation]
            if op["group"] != group or event["publisher"] not in op["callers"] or op["method"] != "POST":
                raise ValueError("Event binding conflicts with receiver-owned operation: " + operation)
    groups = sorted({op["group"] for op in operations.values()})
    return {"version": 1, "operations": operations, "events": events,
            "queues": {"service." + group + ".v1": group for group in groups}}


def subscriptions(catalog):
    groups = {group: [] for group in catalog["queues"].values()}
    for topic, binding in catalog["operations"].items():
        groups[binding["group"]].append({"topic": topic, "group": binding["group"]})
    for topic, event in catalog["events"].items():
        for group in event["groups"]:
            groups[group].append({"topic": topic, "group": group})
    return {group: sorted(values, key=lambda entry: entry["topic"]) for group, values in groups.items()}


def check(root=ROOT, broker_root=None):
    expected = generate(json.loads((root / "contracts/http/service-operations.json").read_text(encoding="utf-8")))
    actual = json.loads((root / "contracts/messaging/catalog.json").read_text(encoding="utf-8"))
    if expected != actual:
        raise ValueError("Messaging bindings drifted; review HTTP changes then run --write")
    registered = json.loads((root / "contracts/messaging/subscriptions.json").read_text(encoding="utf-8"))
    if registered != subscriptions(actual):
        raise ValueError("Generated subscription lists drifted")
    for group, entries in registered.items():
        # The longest real service registrations must still fit Discovery's 4 KiB bound.
        registration = {"serviceName": group, "instanceId": "11111111-1111-1111-1111-111111111111",
                        "baseUrl": "http://" + group + "-1:8080", "readinessPath": "/health/ready",
                        "subscriptions": entries}
        if len(json.dumps(registration, separators=(",", ":")).encode()) > 4096:
            raise ValueError("Subscription registration exceeds Discovery's wire bound")
    if broker_root:
        bundled = json.loads((broker_root / "contracts/messaging.json").read_text(encoding="utf-8"))
        if bundled != actual:
            raise ValueError("Broker messaging copy differs")
        business = json.loads((broker_root / "contracts/service-operations.json").read_text(encoding="utf-8"))
        if generate(business) != actual:
            raise ValueError("Broker business catalog differs")
    return len(actual["operations"]), len(actual["events"]), len(actual["queues"])


def validate_examples(root=ROOT):
    policy = generate(json.loads((root / "contracts/http/service-operations.json").read_text(encoding="utf-8")))
    business = json.loads((root / "contracts/http/service-operations.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "contracts/messaging/envelope.schema.json").read_text(encoding="utf-8"))
    for path in sorted((root / "contracts/messaging/examples").glob("*.json")):
        message = json.loads(path.read_text(encoding="utf-8"))
        errors = validate(message, schema, {})
        for field in ("messageId", "correlationId"):
            if not UUID(message[field]).int:
                errors.append("Nonzero UUID required")
        if bool(message.get("topic")) == bool(message.get("queue")):
            errors.append("Exactly one topic or queue required")
        if message.get("queue"):
            if message["queue"] not in policy["queues"] or message["kind"] != "request":
                errors.append("Invalid public queue")
            # The existing dependency-free business validator supports homogeneous
            # items, not Draft2020 prefixItems. Header tuples have two strings.
            public = json.loads(json.dumps(schema["$defs"]["publicRequest"]))
            public["properties"]["headers"]["items"]["items"] = {"type": "string"}
            errors += validate(message["payload"], public, {})
        elif message["kind"] == "event":
            event = policy["events"][message["topic"]]
            if message["payload"]["producer"] != event["publisher"]:
                errors.append("Invalid publisher")
            operation = next(iter(event["groups"].values()))
            binding = policy["operations"]["operation." + operation + ".v1"]
            errors += validate(message["payload"], business["schemas"][binding["bodySchema"]], business["schemas"])
        else:
            binding = policy["operations"][message["topic"]]
            fields = message.get("arguments", {}) if binding["method"] != "GET" else message["payload"]
            if set(fields) != set(binding["arguments"]) or any(not UUID(v).int for v in fields.values()):
                errors.append("Invalid URI projection")
            if binding["bodySchema"]:
                errors += validate(message["payload"], business["schemas"][binding["bodySchema"]], business["schemas"])
            elif binding["method"] != "GET" and message.get("payload") is not None:
                errors.append("Unexpected request body")
        if errors:
            raise ValueError(path.name + ": " + "; ".join(errors))


def validate_topics(root=ROOT):
    """The topic listing contract (Lab 4 Grade 7): its example matches the schema and
    every listed topic agrees with the generated bindings."""
    schema = json.loads((root / "contracts/messaging/topics.schema.json").read_text(encoding="utf-8"))
    policy = generate(json.loads((root / "contracts/http/service-operations.json").read_text(encoding="utf-8")))
    examples = schema.get("examples") or []
    if not examples:
        raise ValueError("topics.schema.json: an example is required")
    for listing in examples:
        errors = validate(listing, schema, schema["$defs"])
        names = [t["topic"] for t in listing.get("topics", [])]
        if names != sorted(names):
            errors.append("topics must be sorted by name")
        for topic in listing.get("topics", []):
            name = topic["topic"]
            if topic["kind"] == "request":
                binding = policy["operations"].get(name)
                if (binding is None or topic.get("operation") != binding["operation"]
                        or topic["groups"] != [binding["group"]] or topic["publishers"] != binding["callers"]
                        or topic.get("budgetMs") != binding["budgetMs"] or "eventType" in topic):
                    errors.append(name + " disagrees with its operation binding")
            else:
                event = policy["events"].get(name)
                if (event is None or topic.get("eventType") != event["eventType"]
                        or topic["groups"] != sorted(event["groups"]) or topic["publishers"] != [event["publisher"]]
                        or "operation" in topic or "budgetMs" in topic):
                    errors.append(name + " disagrees with its event binding")
            subscribers = topic.get("subscribers")
            if subscribers is not None:
                if sorted(subscribers) != sorted(topic["groups"]):
                    errors.append(name + " subscribers must name exactly its groups")
                for count in subscribers.values():
                    errors += validate(count, schema["$defs"]["subscriberCount"], schema["$defs"], name)
                    if count.get("ready", 0) > count.get("registered", 0):
                        errors.append(name + " cannot have more ready than registered subscribers")
        if listing.get("discovery") == "UNAVAILABLE" and any(t["subscribers"] is not None for t in listing["topics"]):
            errors.append("subscribers must be null while Discovery is unavailable")
        if errors:
            raise ValueError("topics.schema.json: " + "; ".join(errors))
    return len(examples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--broker-root", type=Path)
    args = parser.parse_args()
    if args.write:
        value = generate(json.loads(HTTP.read_text(encoding="utf-8")))
        BINDINGS.parent.mkdir(parents=True, exist_ok=True)
        BINDINGS.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        (BINDINGS.parent / "subscriptions.json").write_text(
            json.dumps(subscriptions(value), indent=2) + "\n", encoding="utf-8")
    operations, events, queues = check(broker_root=args.broker_root)
    validate_examples()
    validate_topics()
    print(f"Messaging bindings passed: {operations} operations, {events} events, {queues} queues; topic listing example OK")


if __name__ == "__main__":
    main()
