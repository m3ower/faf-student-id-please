"""Validate the shared HTTP/JSON service-operation catalog, its examples and its OpenAPI view.

Standard library only, so it runs anywhere CI runs:

    python scripts/validate_http_contracts.py                 # check catalog, examples, openapi.json
    python scripts/validate_http_contracts.py --write-openapi  # regenerate contracts/http/openapi.json
    python scripts/validate_http_contracts.py --check OPERATION request|response FILE.json
                                                              # validate a captured payload

The schema dialect is the JSON Schema subset the catalog uses: type, enum, required,
properties, additionalProperties=false, items, minItems/maxItems, minimum/maximum,
minLength/maxLength, format uuid/date-time, allOf, and "$ref": "<schema name>".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "contracts" / "http" / "service-operations.json"
EXAMPLES = ROOT / "contracts" / "http" / "examples"
OPENAPI = ROOT / "contracts" / "http" / "openapi.json"

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SECRET_RE = re.compile(r"(?i)bearer\s+(?!<)[A-Za-z0-9._~+/=-]{16,}")
TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
}


class ContractError(Exception):
    pass


def load_catalog(path: Path = CATALOG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[name])


def validate(value, schema: dict, schemas: dict, where: str = "$") -> list[str]:
    """Returns every violation found, each prefixed by its JSON path."""
    errors: list[str] = []
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref not in schemas:
            return [f"{where}: unknown schema {ref!r}"]
        errors += validate(value, schemas[ref], schemas, where)
    for part in schema.get("allOf", []):
        errors += validate(value, part, schemas, where)
    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, t) for t in allowed):
            return errors + [f"{where}: expected {'/'.join(allowed)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        fmt = schema.get("format")
        if fmt == "uuid" and not UUID_RE.match(value):
            errors.append(f"{where}: not a UUID")
        if fmt == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{where}: not an RFC 3339 date-time")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 10**9):
            errors.append(f"{where}: length out of range")
    if _is_type(value, "number"):
        if value < schema.get("minimum", float("-inf")) or value > schema.get("maximum", float("inf")):
            errors.append(f"{where}: {value} out of range")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10**9):
            errors.append(f"{where}: {len(value)} items out of range")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], schemas, f"{where}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{where}: missing required {name!r}")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in props:
                    errors.append(f"{where}: unexpected property {name!r}")
        for name, sub in props.items():
            if name in value:
                errors += validate(value[name], sub, schemas, f"{where}.{name}")
    return errors


def check_catalog(catalog: dict) -> list[str]:
    problems: list[str] = []
    targets = catalog["targets"]
    schemas = catalog["schemas"]
    legend = catalog["statusLegend"]
    seen: dict[tuple, str] = {}
    names = set()
    envs = set()
    for name, target in targets.items():
        env = target["targetCredentialEnv"]
        if env in envs:
            problems.append(f"target {name}: credential env {env} shared with another target")
        envs.add(env)
    for op in catalog["operations"]:
        name = op["name"]
        if name in names:
            problems.append(f"{name}: duplicate operation name")
        names.add(name)
        if op["status"] not in legend:
            problems.append(f"{name}: unknown status {op['status']!r}")
        if op["owner"] not in targets:
            problems.append(f"{name}: owner {op['owner']!r} is not a target")
        if not op.get("callers"):
            problems.append(f"{name}: no callers")
        for caller in op.get("callers", []):
            if caller not in targets:
                problems.append(f"{name}: caller {caller!r} is not a known service")
            if caller == op["owner"]:
                problems.append(f"{name}: an owner does not call itself through the broker")
        if op["status"] == "owner-to-define":
            continue
        if op["method"] not in {"GET", "POST", "PUT", "DELETE"}:
            problems.append(f"{name}: invalid method")
        path = op["path"].split("?")[0]
        if not path.startswith("/internal/v1/"):
            problems.append(f"{name}: service operations live under /internal/v1/")
        key = (op["method"], re.sub(r"\{[^}]+\}", "{}", path))
        if key in seen:
            problems.append(f"{name}: same method and path as {seen[key]}")
        seen[key] = name
        for part in ("request", "response"):
            ref = op.get(part)
            if ref is not None and ref not in schemas:
                problems.append(f"{name}: {part} schema {ref!r} is not defined")
        if op["method"] == "GET" and op.get("request") is not None:
            problems.append(f"{name}: GET operations have no body")
    return problems


def _path_matches(template: str, concrete: str) -> bool:
    pattern = "^" + re.escape(template.split("?")[0]).replace(r"\{", "{").replace(r"\}", "}")
    pattern = re.sub(r"\{[^}]+\}", "[^/?]+", pattern) + "$"
    return re.match(pattern, concrete.split("?")[0]) is not None


def check_examples(catalog: dict, folder: Path = EXAMPLES) -> list[str]:
    problems: list[str] = []
    schemas = catalog["schemas"]
    by_name = {op["name"]: op for op in catalog["operations"]}
    covered = set()
    for file in sorted(folder.glob("*.json")):
        raw = file.read_text(encoding="utf-8")
        if SECRET_RE.search(raw):
            problems.append(f"{file.name}: contains what looks like a real bearer credential; use <placeholders>")
        example = json.loads(raw)
        op = by_name.get(example.get("operation"))
        if op is None:
            problems.append(f"{file.name}: unknown operation {example.get('operation')!r}")
            continue
        covered.add(op["name"])
        req, resp = example["request"], example["response"]
        if req["method"] != op["method"] or not _path_matches(op["path"], req["path"]):
            problems.append(f"{file.name}: request line does not match {op['method']} {op['path']}")
        if op.get("request"):
            problems += [f"{file.name}: request {e}" for e in validate(req.get("body"), {"$ref": op["request"]}, schemas)]
        if resp["status"] == 200 and op.get("response"):
            problems += [f"{file.name}: response {e}" for e in validate(resp.get("body"), {"$ref": op["response"]}, schemas)]
        for header in ("Authorization", "X-Trace-Id"):
            if header not in req.get("headers", {}):
                problems.append(f"{file.name}: request must show {header}")
    for op in catalog["operations"]:
        if op["status"] != "owner-to-define" and op["name"] not in covered:
            problems.append(f"{op['name']}: no example")
    return problems


def openapi(catalog: dict) -> dict:
    """The catalog as OpenAPI 3.1, generated so the two can never drift."""
    def convert(schema):
        if isinstance(schema, dict):
            out = {}
            for k, v in schema.items():
                if k == "$ref":
                    out[k] = f"#/components/schemas/{v}"
                else:
                    out[k] = convert(v)
            return out
        if isinstance(schema, list):
            return [convert(v) for v in schema]
        return schema

    paths: dict = {}
    for op in catalog["operations"]:
        if op["status"] == "owner-to-define":
            continue
        path = op["path"].split("?")[0]
        params = [{"name": p, "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
                  for p in re.findall(r"\{([^}]+)\}", path)]
        query = op["path"].split("?")[1] if "?" in op["path"] else ""
        params += [{"name": q.split("=")[0], "in": "query", "required": True,
                    "schema": {"type": "string", "format": "uuid"}} for q in query.split("&") if q]
        params += [{"name": "X-Trace-Id", "in": "header", "required": False, "schema": {"type": "string"}},
                   {"name": "X-Service-Name", "in": "header", "required": True,
                    "description": "set by the message broker to the authenticated caller",
                    "schema": {"type": "string", "enum": op["callers"]}}]
        operation = {
            "operationId": op["name"],
            "summary": op["semantics"],
            "x-owner": op["owner"],
            "x-status": op["status"],
            "x-callers": op["callers"],
            "x-idempotency": op["idempotency"],
            "security": [{"brokerServiceCredential": []}],
            "parameters": params,
            "responses": {
                "200": {"description": "OK", "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{op['response']}"}}}},
                **{code.split(" ")[0]: {"description": f"{code}: {why}",
                                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/errorEnvelope"}}}}
                   for code, why in op["errors"].items()},
            },
        }
        if op.get("request"):
            operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{op['request']}"}}}}
        paths.setdefault(path, {})[op["method"].lower()] = operation
    schemas = {name: convert(s) for name, s in catalog["schemas"].items()}
    schemas["errorEnvelope"] = {
        "type": "object", "required": ["error"],
        "properties": {"error": {"type": "object", "required": ["code", "message", "service", "traceId"],
                                 "properties": {k: {"type": "string"} for k in ("code", "message", "service", "traceId")}}},
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "Student ID, please: service operations through the message broker",
                 "version": catalog["catalogVersion"],
                 "description": "Generated from contracts/http/service-operations.json. Do not edit by hand."},
        "paths": dict(sorted(paths.items())),
        "components": {"schemas": schemas,
                       "securitySchemes": {"brokerServiceCredential": {"type": "http", "scheme": "bearer",
                                                                        "description": "caller credential to the broker; target credential from the broker"}}},
    }


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-openapi", action="store_true")
    parser.add_argument("--check", nargs=3, metavar=("OPERATION", "PART", "FILE"))
    args = parser.parse_args(argv)
    catalog = load_catalog()

    if args.check:
        name, part, file = args.check
        op = next((o for o in catalog["operations"] if o["name"] == name), None)
        if op is None or not op.get(part):
            print(f"no {part} schema for {name}", file=sys.stderr)
            return 2
        errors = validate(json.loads(Path(file).read_text(encoding="utf-8")), {"$ref": op[part]}, catalog["schemas"])
        for e in errors:
            print(e)
        print("OK" if not errors else f"{len(errors)} violation(s)")
        return 0 if not errors else 1

    if args.write_openapi:
        OPENAPI.write_text(render(openapi(catalog)), encoding="utf-8")
    problems = check_catalog(catalog) + check_examples(catalog)
    if not OPENAPI.exists() or OPENAPI.read_text(encoding="utf-8") != render(openapi(catalog)):
        problems.append("contracts/http/openapi.json is out of date: run with --write-openapi")
    for p in problems:
        print(p)
    ops = [o for o in catalog["operations"]]
    print(f"{len(ops)} operations, {len(list(EXAMPLES.glob('*.json')))} examples: "
          + ("OK" if not problems else f"{len(problems)} problem(s)"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
