#!/usr/bin/env python3
"""Validate and canonically serialize an aHPy NOX package manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

import nox_integration_policy


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "tests" / "ahpy" / "nox-hpy-manifest-v1.json"
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
PACKAGE_NAME = re.compile(r"[a-z][a-z0-9_-]*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class NoxManifestError(ValueError):
    """The NOX package manifest is malformed or incompatible."""


def _require(condition, message):
    if not condition:
        raise NoxManifestError(message)


def _exact_keys(mapping, keys, context):
    _require(isinstance(mapping, dict), f"{context} must be an object")
    expected = set(keys)
    observed = set(mapping)
    _require(observed == expected, "%s keys mismatch; missing=%s unknown=%s" % (
        context,
        ",".join(sorted(expected - observed)) or "none",
        ",".join(sorted(observed - expected)) or "none",
    ))


def _nonempty_string(value, context):
    _require(isinstance(value, str) and value, f"{context} must be a string")
    return value


def _sorted_unique_strings(value, context):
    _require(isinstance(value, list) and value,
             f"{context} must be a non-empty array")
    _require(all(isinstance(item, str) and item for item in value),
             f"{context} must contain strings")
    _require(value == sorted(set(value)),
             f"{context} must be sorted and unique")
    return value


def _validate_digest(value, context, pattern=SHA256):
    _require(isinstance(value, str) and pattern.fullmatch(value),
             f"{context} has invalid digest identity")


def _validate_value_kind(kind, capabilities, policy, context):
    required = set(policy["types"]["required"])
    conditional = set(policy["types"]["conditional"])
    _require(kind in required or kind in conditional,
             f"{context} uses unsupported type {kind!r}")
    if kind == "bytes":
        _require("bytes" in capabilities,
                 f"{context} requires the bytes capability")


def _validate_export(export, capabilities, policy, context):
    _exact_keys(export, {"kind", "name", "parameters", "result"}, context)
    kind = _nonempty_string(export["kind"], f"{context}.kind")
    allowed_calls = set(policy["calls"]["required"])
    allowed_calls.update(policy["calls"]["conditional"])
    _require(kind in {"constructor", "method", "module-function"},
             f"{context}.kind is unsupported")
    name = _nonempty_string(export["name"], f"{context}.name")
    name_parts = name.split(".")
    _require(all(IDENTIFIER.fullmatch(part) for part in name_parts),
             f"{context}.name is not a dotted identifier")
    parameters = export["parameters"]
    _require(isinstance(parameters, list),
             f"{context}.parameters must be an array")
    parameter_names = []
    for index, parameter in enumerate(parameters):
        parameter_context = f"{context}.parameters[{index}]"
        _exact_keys(parameter, {"name", "kind", "call_kind", "ownership"},
                    parameter_context)
        parameter_name = _nonempty_string(
            parameter["name"], f"{parameter_context}.name")
        _require(IDENTIFIER.fullmatch(parameter_name),
                 f"{parameter_context}.name is not an identifier")
        parameter_names.append(parameter_name)
        _validate_value_kind(
            parameter["kind"], capabilities, policy,
            f"{parameter_context}.kind")
        call_kind = parameter["call_kind"]
        _require(call_kind in {
            "keyword-only", "positional-only", "positional-or-keyword",
        } and (call_kind == "positional-only" or
               "call-keywords" in capabilities),
                 f"{parameter_context}.call_kind is unavailable")
        _require(parameter["ownership"] in {"borrowed", "owned", "value"},
                 f"{parameter_context}.ownership is invalid")
    _require(len(parameter_names) == len(set(parameter_names)),
             f"{context} has duplicate parameter names")
    result = export["result"]
    _exact_keys(result, {"kind", "ownership"}, f"{context}.result")
    _validate_value_kind(
        result["kind"], capabilities, policy, f"{context}.result.kind")
    _require(result["ownership"] in {"owned", "value"},
             f"{context}.result.ownership is invalid")
    if result["kind"] == "opaque-object":
        _require(result["ownership"] == "owned",
                 f"{context} object result must be owned")
    else:
        _require(result["ownership"] == "value",
                 f"{context} scalar result must use value ownership")
    if kind == "constructor":
        _require(result == {"kind": "opaque-object", "ownership": "owned"},
                 f"{context} constructor must return an owned object")
    _require(kind in allowed_calls, f"{context}.kind is not enabled by policy")
    return kind, name


def validate_manifest(data, policy=None, source="NOX package manifest"):
    if policy is None:
        policy = nox_integration_policy.load_policy()
    _exact_keys(data, {
        "schema_version", "package", "producer", "host", "module",
        "exports", "artifacts",
    }, source)
    _require(data["schema_version"] == policy["contract_version"] == 1,
             f"{source} has an incompatible schema version")

    package = data["package"]
    _exact_keys(package, {"name", "version"}, "package")
    _require(isinstance(package["name"], str) and
             PACKAGE_NAME.fullmatch(package["name"]),
             "package.name is invalid")
    _nonempty_string(package["version"], "package.version")

    producer = data["producer"]
    _exact_keys(producer, {
        "ahpy_version", "cython_base", "source_digest",
        "compiler_options_digest",
    }, "producer")
    _nonempty_string(producer["ahpy_version"], "producer.ahpy_version")
    _validate_digest(producer["cython_base"], "producer.cython_base", SHA40)
    _validate_digest(producer["source_digest"], "producer.source_digest")
    _validate_digest(
        producer["compiler_options_digest"], "producer.compiler_options_digest")

    host = data["host"]
    _exact_keys(host, {
        "profile", "hpy_abi", "hpy_version", "required_capabilities",
    }, "host")
    _require(host["profile"] == policy["host"]["profile"] and
             host["hpy_abi"] == policy["host"]["hpy_abi"] and
             host["hpy_version"] == policy["host"]["hpy_version"],
             "host identity is incompatible")
    capabilities = _sorted_unique_strings(
        host["required_capabilities"], "host.required_capabilities")
    allowed_capabilities = set(policy["host"]["required_capabilities"])
    allowed_capabilities.update(policy["host"]["optional_capabilities"])
    _require(set(policy["host"]["required_capabilities"]) <= set(capabilities),
             "host.required_capabilities omits the v1 minimum")
    _require(set(capabilities) <= allowed_capabilities,
             "host.required_capabilities contains an unknown capability")

    module = data["module"]
    _exact_keys(module, {"name", "init_symbol"}, "module")
    module_name = _nonempty_string(module["name"], "module.name")
    parts = module_name.split(".")
    _require(all(IDENTIFIER.fullmatch(part) for part in parts),
             "module.name is not a dotted identifier")
    _require(module["init_symbol"] == "HPyInit_%s" % parts[-1],
             "module.init_symbol does not match the module leaf")

    exports = data["exports"]
    _require(isinstance(exports, list), "exports must be an array")
    export_keys = [
        _validate_export(export, set(capabilities), policy, f"exports[{index}]")
        for index, export in enumerate(exports)
    ]
    _require(export_keys == sorted(set(export_keys)),
             "exports must be sorted and unique by kind/name")

    artifacts = data["artifacts"]
    _require(isinstance(artifacts, list) and artifacts,
             "artifacts must be a non-empty array")
    artifact_targets = []
    for index, artifact in enumerate(artifacts):
        context = f"artifacts[{index}]"
        _exact_keys(artifact, {"target", "path", "sha256", "size"}, context)
        target = artifact["target"]
        _require(target in policy["targets"]["declared"],
                 f"{context}.target is not declared")
        artifact_targets.append(target)
        path_string = _nonempty_string(artifact["path"], f"{context}.path")
        path = PurePosixPath(path_string)
        _require(not path.is_absolute() and ".." not in path.parts and
                 path.suffix == policy["artifacts"]["extension_suffix"] and
                 path.as_posix() == path_string,
                 f"{context}.path is unsafe or has the wrong suffix")
        _validate_digest(artifact["sha256"], f"{context}.sha256")
        _require(type(artifact["size"]) is int and artifact["size"] > 0,
                 f"{context}.size must be a positive integer")
    _require(artifact_targets == sorted(set(artifact_targets)),
             "artifacts must be sorted with one entry per target")
    return data


def canonical_manifest_bytes(data, policy=None):
    validate_manifest(data, policy=policy)
    return (json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) +
        "\n").encode("utf8")


def load_manifest(path=DEFAULT_MANIFEST):
    try:
        data = json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NoxManifestError(f"cannot read NOX manifest {path}: {exc}") from exc
    return validate_manifest(data, source=str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-canonical", action="store_true")
    options = parser.parse_args(argv)
    try:
        manifest = load_manifest(options.manifest)
        rendered = canonical_manifest_bytes(manifest)
        if options.check_canonical:
            _require(options.manifest.read_bytes() == rendered,
                     f"{options.manifest} is not canonical JSON")
    except NoxManifestError as exc:
        parser.error(str(exc))
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_bytes(rendered)
    else:
        sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
