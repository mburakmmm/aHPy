#!/usr/bin/env python3
"""Validate the one-way aHPy to NOX package integration contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "tests" / "ahpy" / "nox-integration-policy.toml"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class NoxIntegrationPolicyError(ValueError):
    """The aHPy to NOX contract is incomplete, unsafe, or inconsistent."""


def _require(condition, message):
    if not condition:
        raise NoxIntegrationPolicyError(message)


def _exact_keys(mapping, keys, context):
    _require(isinstance(mapping, dict), f"{context} must be a table")
    expected = set(keys)
    observed = set(mapping)
    _require(observed == expected, "%s keys mismatch; missing=%s unknown=%s" % (
        context,
        ",".join(sorted(expected - observed)) or "none",
        ",".join(sorted(observed - expected)) or "none",
    ))


def _sorted_unique_strings(value, context, *, nonempty=True):
    _require(isinstance(value, list), f"{context} must be an array")
    _require(all(isinstance(item, str) and item for item in value),
             f"{context} must contain non-empty strings")
    _require(value == sorted(set(value)),
             f"{context} must be sorted and unique")
    if nonempty:
        _require(value, f"{context} must not be empty")
    return value


def _safe_repo_path(value, context):
    _require(isinstance(value, str) and value, f"{context} must be a path")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts,
             f"{context} must stay inside the repository")
    return path


def _load_manifest_schema(path):
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoxIntegrationPolicyError(
            f"cannot read NOX package schema {path}: {exc}") from exc


def _validate_manifest_schema(schema, source):
    _require(isinstance(schema, dict), f"{source} must be an object")
    _require(schema.get("$schema") ==
             "https://json-schema.org/draft/2020-12/schema",
             f"{source} must use JSON Schema 2020-12")
    _require(schema.get("type") == "object" and
             schema.get("additionalProperties") is False,
             f"{source} root must be a closed object")
    _require(schema.get("required") == [
        "schema_version", "package", "producer", "host", "module",
        "exports", "artifacts",
    ], f"{source} root fields must be exact and ordered")
    properties = schema.get("properties", {})
    _require(properties.get("schema_version") == {"const": 1},
             f"{source} schema_version must be one")
    host = properties.get("host", {}).get("properties", {})
    _require(host.get("profile") == {"const": "nox-hpy-host-v1"} and
             host.get("hpy_abi") == {"const": "universal"} and
             host.get("hpy_version") == {"const": "0.9"},
             f"{source} host identity does not match the policy")
    definitions = schema.get("$defs", {})
    _require(definitions.get("sha256", {}).get("pattern") ==
             "^[0-9a-f]{64}$",
             f"{source} must require lowercase SHA-256")
    artifact = definitions.get("artifact", {})
    artifact_properties = artifact.get("properties", {})
    _require(artifact.get("additionalProperties") is False and
             artifact_properties.get("size") == {
                 "type": "integer", "minimum": 1,
             }, f"{source} artifact record is not fail-closed")
    _require(".hpy0" in artifact_properties.get("path", {}).get("pattern", ""),
             f"{source} artifact path must require .hpy0")
    return schema


def validate_policy(data, root=ROOT, source="NOX integration policy"):
    _exact_keys(data, {
        "schema_version", "contract_version", "status", "direction",
        "reverse_direction_supported", "silent_fallback_allowed",
        "partial_package_allowed", "nox_source_mutation_allowed",
        "required_documents", "artifacts", "host", "ownership", "types",
        "calls", "diagnostics", "targets", "baseline",
    }, source)
    _require(data["schema_version"] == 1 and data["contract_version"] == 1,
             f"{source}: unsupported schema or contract version")
    _require(data["status"] == "planned",
             f"{source}: status must remain planned before retained evidence")
    _require(data["direction"] == "ahpy-universal-to-nox" and
             data["reverse_direction_supported"] is False,
             f"{source}: only aHPy Universal to NOX is in scope")
    _require(data["silent_fallback_allowed"] is False and
             data["partial_package_allowed"] is False and
             data["nox_source_mutation_allowed"] is False,
             f"{source}: fallback, partial output, and NOX mutation are banned")

    artifacts = data["artifacts"]
    _exact_keys(artifacts, {
        "package_manifest", "integration_manifest", "integration_schema",
        "facade_suffix", "extension_suffix", "hash_algorithm", "path_mode",
        "serialization", "reproducible", "provenance_required",
    }, "artifacts")
    _require(artifacts == {
        "package_manifest": "nox.json",
        "integration_manifest": "nox-hpy.json",
        "integration_schema": "tests/ahpy/nox-hpy-package.schema.json",
        "facade_suffix": ".nox",
        "extension_suffix": ".hpy0",
        "hash_algorithm": "sha256",
        "path_mode": "package-relative",
        "serialization": "canonical-json-utf8",
        "reproducible": True,
        "provenance_required": True,
    }, "artifact contract does not match the v1 package layout")

    host = data["host"]
    _exact_keys(host, {
        "profile", "hpy_abi", "hpy_version", "minimum_nox_release",
        "support_status", "capability_query_required",
        "preload_validation_required", "required_capabilities",
        "optional_capabilities",
    }, "host")
    _require(host["profile"] == "nox-hpy-host-v1" and
             host["hpy_abi"] == "universal" and
             host["hpy_version"] == "0.9",
             "host profile must pin HPy 0.9 Universal")
    _require(host["minimum_nox_release"] == "unreleased" and
             host["support_status"] == "blocked",
             "no released NOX host may be claimed before retained evidence")
    _require(host["capability_query_required"] is True and
             host["preload_validation_required"] is True,
             "host capability and preload validation must be mandatory")
    _require(_sorted_unique_strings(
        host["required_capabilities"], "host.required_capabilities") == [
            "call-positional", "error-take", "extension-object",
            "module-close", "module-open", "object-close",
        ], "required host capabilities must match profile v1")
    _require(_sorted_unique_strings(
        host["optional_capabilities"], "host.optional_capabilities") == [
            "bytes", "call-keywords", "hpy-debug", "hpy-trace",
        ], "optional host capabilities must match profile v1")

    ownership = data["ownership"]
    _exact_keys(ownership, {"ahpy", "nox"}, "ownership")
    _require(_sorted_unique_strings(ownership["ahpy"], "ownership.ahpy") == [
        "artifact-build", "artifact-validation", "export-analysis",
        "facade-generation", "manifest-generation", "package-assembly",
    ], "aHPy ownership boundary is incomplete")
    _require(_sorted_unique_strings(ownership["nox"], "ownership.nox") == [
        "backend-correctness", "dynamic-loading", "host-abi",
        "lifetime-safety", "package-resolution", "runtime-error-translation",
    ], "NOX ownership boundary is incomplete")

    types = data["types"]
    _exact_keys(types, {"required", "conditional", "blocked"}, "types")
    _require(_sorted_unique_strings(types["required"], "types.required") == [
        "bool", "float64", "int64", "none", "opaque-object", "unicode",
        "void",
    ], "required type profile is incomplete")
    _require(_sorted_unique_strings(
        types["conditional"], "types.conditional") == ["bytes"],
        "conditional type profile is incomplete")
    _sorted_unique_strings(types["blocked"], "types.blocked")
    _require(not set(types["required"]) & set(types["conditional"]) and
             not set(types["required"]) & set(types["blocked"]) and
             not set(types["conditional"]) & set(types["blocked"]),
             "type classifications must not overlap")

    calls = data["calls"]
    _exact_keys(calls, {"required", "conditional", "blocked"}, "calls")
    for field in ("required", "conditional", "blocked"):
        _sorted_unique_strings(calls[field], f"calls.{field}")
    _require(not set(calls["required"]) & set(calls["conditional"]) and
             not set(calls["required"]) & set(calls["blocked"]) and
             not set(calls["conditional"]) & set(calls["blocked"]),
             "call classifications must not overlap")

    diagnostics = data["diagnostics"]
    diagnostic_names = {
        "ambiguous_ownership", "artifact_integrity", "incompatible_schema",
        "missing_capability", "name_collision", "target_unavailable",
        "unsupported_call", "unsupported_type",
    }
    _exact_keys(diagnostics, diagnostic_names, "diagnostics")
    _require(list(diagnostics) == sorted(diagnostic_names),
             "diagnostic names must be sorted")
    _require(list(diagnostics.values()) == [
        "AHPY_NOX001", "AHPY_NOX002", "AHPY_NOX003", "AHPY_NOX004",
        "AHPY_NOX005", "AHPY_NOX006", "AHPY_NOX007", "AHPY_NOX008",
    ], "diagnostic identifiers must be unique and contiguous")

    targets = data["targets"]
    _exact_keys(targets, {"status", "artifact_selection", "declared"},
                "targets")
    _require(targets["status"] == "planned" and
             targets["artifact_selection"] == "exact-target",
             "targets must stay planned and exact-match only")
    declared_targets = _sorted_unique_strings(
        targets["declared"], "targets.declared")

    baseline = data["baseline"]
    _exact_keys(baseline, {
        "observed_on", "analyzed_nox_commit", "analyzed_nox_release",
        "installed_nox_release", "qbe_status", "llvm_status",
        "llvm_failure_id", "support_claim", "retained_hosted_evidence",
    }, "baseline")
    _require(re.fullmatch(r"20\d\d-\d\d-\d\d", baseline["observed_on"]),
             "baseline.observed_on must be an ISO date string")
    _require(SHA40.fullmatch(baseline["analyzed_nox_commit"]),
             "baseline.analyzed_nox_commit must be an exact commit")
    _require(baseline["qbe_status"] == "local-probe-pass" and
             baseline["llvm_status"] == "local-probe-fail" and
             baseline["llvm_failure_id"] == "nox-llvm-hpy-error-width" and
             baseline["support_claim"] is False and
             baseline["retained_hosted_evidence"] is False,
             "baseline must not overstate local probe evidence")

    document_paths = [
        _safe_repo_path(path, "required_documents")
        for path in _sorted_unique_strings(
            data["required_documents"], "required_documents")
    ]
    schema_path = _safe_repo_path(
        artifacts["integration_schema"], "artifacts.integration_schema")
    missing = [str(path) for path in (*document_paths, schema_path)
               if not (Path(root) / path).is_file()]
    _require(not missing, "required NOX integration files are missing: %s" %
             ", ".join(missing))
    schema = _validate_manifest_schema(
        _load_manifest_schema(Path(root) / schema_path), str(schema_path))
    schema_targets = schema["$defs"]["artifact"]["properties"]["target"][
        "enum"]
    _require(schema_targets == declared_targets,
             "manifest schema targets must match the policy")
    return data


def load_policy(path=DEFAULT_POLICY, root=ROOT):
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NoxIntegrationPolicyError(
            f"cannot read NOX integration policy {path}: {exc}") from exc
    return validate_policy(data, root=root, source=str(path))


def render_text(policy):
    baseline = policy["baseline"]
    return (
        "aHPy to NOX integration policy: valid\n"
        f"status: {policy['status']}\n"
        f"direction: {policy['direction']}\n"
        f"host profile: {policy['host']['profile']}\n"
        f"HPy ABI: {policy['host']['hpy_abi']} {policy['host']['hpy_version']}\n"
        f"QBE baseline: {baseline['qbe_status']}\n"
        f"LLVM baseline: {baseline['llvm_status']}\n"
        "support claim: false\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    try:
        policy = load_policy(options.policy, options.root)
    except NoxIntegrationPolicyError as exc:
        parser.error(str(exc))
    rendered = (json.dumps(policy, indent=2, sort_keys=True) + "\n"
                if options.as_json else render_text(policy))
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
