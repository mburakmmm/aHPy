#!/usr/bin/env python3
"""Validate and execute the frontend-neutral aHPy conformance protocol."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "tests" / "ahpy-conformance.toml"
PROTOCOL = "ahpy-universal-conformance-v1"
CASE_ID = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
TAGGED_VALUES = {"$dict", "$list", "$ref", "$set", "$tuple"}
REQUIRED_GATES = {
    "semantic_contract",
    "hpy_debug",
    "forbidden_legacy_source",
    "forbidden_legacy_symbols",
    "same_binary_cross_interpreter",
    "fault_injection",
}


class ConformanceError(ValueError):
    """The conformance contract or an implementation is invalid."""


def _read_toml(path):
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConformanceError(f"cannot read conformance manifest {path}: {exc}") from exc


def _read_json(path):
    try:
        raw = Path(path).read_bytes()
        return raw, json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConformanceError(f"cannot read conformance suite {path}: {exc}") from exc


def load_manifest(path=DEFAULT_MANIFEST):
    path = Path(path).resolve()
    data = _read_toml(path)
    if data.get("schema_version") != 2 or data.get("protocol") != PROTOCOL:
        raise ConformanceError(f"{path}: unsupported conformance manifest")
    if data.get("module_contract") != "python-callable-surface-map":
        raise ConformanceError(f"{path}: unsupported module contract")
    if data.get("runner") != "Tools/ahpy/run_conformance.py":
        raise ConformanceError(f"{path}: unsupported conformance runner")
    if data.get("frontend_sources_required") is not False:
        raise ConformanceError(f"{path}: frontend_sources_required must be false")
    suite_name = data.get("suite")
    if not isinstance(suite_name, str):
        raise ConformanceError(f"{path}: suite must be a relative path")
    relative = Path(suite_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ConformanceError(f"{path}: suite path must stay below the manifest directory")
    suite_path = (path.parent / relative).resolve()
    digest = data.get("suite_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ConformanceError(f"{path}: suite_sha256 must be lowercase SHA-256")
    gates = data.get("required_gates")
    if not isinstance(gates, dict) or set(gates) != REQUIRED_GATES or \
            any(value is not True for value in gates.values()):
        raise ConformanceError(f"{path}: required_gates contract is incomplete")
    raw, suite = _read_json(suite_path)
    observed = hashlib.sha256(raw).hexdigest()
    if observed != digest:
        raise ConformanceError(
            f"{path}: suite SHA-256 mismatch: expected {digest}, observed {observed}")
    return data, suite_path, suite


def _validate_value(value, fixtures, location):
    if value is None or type(value) in {bool, int, float, str}:
        return
    if isinstance(value, dict):
        tags = set(value) & TAGGED_VALUES
        if len(value) != 1 or len(tags) != 1:
            raise ConformanceError(f"{location}: value objects require exactly one known tag")
        tag = next(iter(tags))
        payload = value[tag]
        if tag == "$ref":
            if not isinstance(payload, str) or payload not in fixtures:
                raise ConformanceError(f"{location}: unknown fixture reference {payload!r}")
            return
        if not isinstance(payload, list):
            raise ConformanceError(f"{location}: {tag} payload must be an array")
        if tag == "$dict":
            for index, pair in enumerate(payload):
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ConformanceError(f"{location}: $dict item {index} must be a pair")
                _validate_value(pair[0], fixtures, f"{location}.$dict[{index}].key")
                _validate_value(pair[1], fixtures, f"{location}.$dict[{index}].value")
        else:
            for index, item in enumerate(payload):
                _validate_value(item, fixtures, f"{location}.{tag}[{index}]")
        return
    raise ConformanceError(f"{location}: unsupported encoded value")


def _validate_exception(spec, fixtures, location):
    if not isinstance(spec, dict) or set(spec) - {"type", "args", "cause"}:
        raise ConformanceError(f"{location}: malformed exception expectation")
    if not isinstance(spec.get("type"), str) or not spec["type"].startswith("builtins."):
        raise ConformanceError(f"{location}: exception type must name a builtin")
    if "args" not in spec:
        raise ConformanceError(f"{location}: exception args are required")
    _validate_value(spec["args"], fixtures, f"{location}.args")
    if "cause" in spec:
        _validate_exception(spec["cause"], fixtures, f"{location}.cause")


def validate_suite(suite):
    if not isinstance(suite, dict) or suite.get("schema_version") != 1 or \
            suite.get("protocol") != PROTOCOL:
        raise ConformanceError("unsupported conformance suite")
    fixtures = suite.get("fixtures")
    if not isinstance(fixtures, dict):
        raise ConformanceError("fixtures must be an object")
    for name, fixture in fixtures.items():
        if not CASE_ID.fullmatch(name) or fixture != {"kind": "fresh-object"}:
            raise ConformanceError(f"invalid fixture {name!r}")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ConformanceError("cases must be a non-empty array")
    seen = set()
    surfaces = set()
    for index, case in enumerate(cases):
        location = f"cases[{index}]"
        if not isinstance(case, dict) or set(case) != {
                "id", "surface", "callable", "args", "kwargs", "expect"}:
            raise ConformanceError(f"{location}: case shape is invalid")
        case_id = case["id"]
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id) or case_id in seen:
            raise ConformanceError(f"{location}: invalid or duplicate case id {case_id!r}")
        seen.add(case_id)
        surface = case["surface"]
        callable_name = case["callable"]
        if not isinstance(surface, str) or not CASE_ID.fullmatch(surface):
            raise ConformanceError(f"{case_id}: invalid surface")
        if not isinstance(callable_name, str) or not callable_name.isidentifier():
            raise ConformanceError(f"{case_id}: invalid callable")
        surfaces.add(surface)
        if not isinstance(case["args"], list) or not isinstance(case["kwargs"], dict) or \
                any(not isinstance(key, str) for key in case["kwargs"]):
            raise ConformanceError(f"{case_id}: args/kwargs shape is invalid")
        for arg_index, value in enumerate(case["args"]):
            _validate_value(value, fixtures, f"{case_id}.args[{arg_index}]")
        for key, value in case["kwargs"].items():
            _validate_value(value, fixtures, f"{case_id}.kwargs.{key}")
        expect = case["expect"]
        if not isinstance(expect, dict) or len(expect) != 1:
            raise ConformanceError(f"{case_id}: exactly one expectation is required")
        kind = next(iter(expect))
        if kind == "return":
            _validate_value(expect[kind], fixtures, f"{case_id}.expect.return")
        elif kind == "identity":
            if not isinstance(expect[kind], str) or expect[kind] not in fixtures:
                raise ConformanceError(f"{case_id}: identity fixture is invalid")
        elif kind == "raises":
            _validate_exception(expect[kind], fixtures, f"{case_id}.expect.raises")
        else:
            raise ConformanceError(f"{case_id}: unknown expectation {kind!r}")
    return surfaces


def _decode(value, fixtures):
    if not isinstance(value, dict):
        return value
    tag, payload = next(iter(value.items()))
    if tag == "$ref":
        return fixtures[payload]
    values = [_decode(item, fixtures) for item in payload]
    if tag == "$list":
        return values
    if tag == "$tuple":
        return tuple(values)
    if tag == "$set":
        return set(values)
    if tag == "$dict":
        return dict(values)
    raise AssertionError(f"unvalidated tag {tag}")


def _matches(actual, expected, fixtures):
    if isinstance(expected, dict):
        tag, payload = next(iter(expected.items()))
        if tag == "$ref":
            return actual is fixtures[payload]
        if tag == "$list":
            return type(actual) is list and len(actual) == len(payload) and all(
                _matches(item, wanted, fixtures) for item, wanted in zip(actual, payload))
        if tag == "$tuple":
            return type(actual) is tuple and len(actual) == len(payload) and all(
                _matches(item, wanted, fixtures) for item, wanted in zip(actual, payload))
        if tag == "$set":
            try:
                return type(actual) is set and actual == _decode(expected, fixtures)
            except (TypeError, ValueError):
                return False
        if tag == "$dict":
            wanted = _decode(expected, fixtures)
            return type(actual) is dict and actual == wanted
    return type(actual) is type(expected) and actual == expected


def _exception_name(exc):
    cls = type(exc)
    return f"{cls.__module__}.{cls.__qualname__}"


def _match_exception(exc, spec, fixtures):
    if _exception_name(exc) != spec["type"] or not _matches(exc.args, spec["args"], fixtures):
        return False
    if "cause" in spec:
        return exc.__cause__ is not None and _match_exception(
            exc.__cause__, spec["cause"], fixtures)
    return True


def parse_module_map(values, surfaces):
    result = {}
    for value in values:
        surface, separator, module = value.partition("=")
        if not separator or surface not in surfaces or not module or surface in result:
            raise ConformanceError(f"invalid or duplicate module mapping {value!r}")
        result[surface] = module
    missing = surfaces - set(result)
    if missing:
        raise ConformanceError(f"missing module mappings: {', '.join(sorted(missing))}")
    return result


def _validated_timestamp(value):
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ConformanceError("generated_at must be an ISO-8601 string") from exc
    if parsed.tzinfo is None:
        raise ConformanceError("generated_at must include a timezone")
    return value


def run_suite(suite, module_map, mode="normal", generated_at=None):
    surfaces = validate_suite(suite)
    if set(module_map) != surfaces:
        missing = surfaces - set(module_map)
        extra = set(module_map) - surfaces
        raise ConformanceError(
            "module mapping mismatch; missing=%s extra=%s" %
            (",".join(sorted(missing)) or "none", ",".join(sorted(extra)) or "none"))
    if mode not in {"normal", "trace", "debug"}:
        raise ConformanceError(f"unknown HPy mode {mode!r}")
    try:
        modules = {
            surface: importlib.import_module(name)
            for surface, name in module_map.items()
        }
    except (ImportError, TypeError, ValueError) as exc:
        raise ConformanceError(f"cannot import conformance module: {exc}") from exc
    fixtures = {name: object() for name in suite["fixtures"]}
    results = []
    for case in suite["cases"]:
        status = "pass"
        detail = None
        try:
            function = getattr(modules[case["surface"]], case["callable"])
            args = [_decode(value, fixtures) for value in case["args"]]
            kwargs = {key: _decode(value, fixtures) for key, value in case["kwargs"].items()}
            try:
                actual = function(*args, **kwargs)
            except Exception as exc:
                raises = case["expect"].get("raises")
                if raises is None or not _match_exception(exc, raises, fixtures):
                    status = "fail"
                    detail = f"unexpected exception {_exception_name(exc)}: {exc}"
            else:
                expect = case["expect"]
                if "raises" in expect:
                    status = "fail"
                    detail = f"expected {expect['raises']['type']} but call returned"
                elif "identity" in expect:
                    if actual is not fixtures[expect["identity"]]:
                        status = "fail"
                        detail = "identity expectation failed"
                elif not _matches(actual, expect["return"], fixtures):
                    status = "fail"
                    detail = f"return expectation failed: {actual!r}"
        except (AttributeError, TypeError, ValueError) as exc:
            status = "fail"
            detail = f"implementation contract error: {exc}"
        item = {"id": case["id"], "status": status}
        if detail is not None:
            item["detail"] = detail
        results.append(item)
    timestamp = _validated_timestamp(generated_at)
    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "generated_at": timestamp,
        "mode": mode,
        "modules": dict(sorted(module_map.items())),
        "passed": sum(item["status"] == "pass" for item in results),
        "failed": sum(item["status"] == "fail" for item in results),
        "cases": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--module", action="append", default=[], metavar="SURFACE=MODULE")
    parser.add_argument("--mode", choices=("normal", "trace", "debug"), default="normal")
    parser.add_argument("--generated-at")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    try:
        manifest, suite_path, suite = load_manifest(options.manifest)
        surfaces = validate_suite(suite)
        if options.validate_only:
            if options.module:
                raise ConformanceError("--module cannot be used with --validate-only")
            report = {
                "schema_version": 1,
                "protocol": PROTOCOL,
                "manifest": str(options.manifest.resolve()),
                "suite": str(suite_path),
                "suite_sha256": manifest["suite_sha256"],
                "cases": len(suite["cases"]),
                "surfaces": sorted(surfaces),
                "status": "valid",
            }
        else:
            module_map = parse_module_map(options.module, surfaces)
            report = run_suite(suite, module_map, options.mode, options.generated_at)
    except ConformanceError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 1 if report.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
