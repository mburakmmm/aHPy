#!/usr/bin/env python3
"""Validate aHPy's machine-readable maintenance and ownership policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "tests" / "ahpy" / "maintenance-policy.toml"
HANDLE = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})\Z")
CADENCE = {"continuous-and-weekly", "monthly", "quarterly"}


class MaintenancePolicyError(ValueError):
    """The maintenance policy is incomplete, unsafe, or inconsistent."""


def _require(condition, message):
    if not condition:
        raise MaintenancePolicyError(message)


def _exact_keys(mapping, keys, context):
    _require(isinstance(mapping, dict), f"{context} must be a table")
    expected = set(keys)
    observed = set(mapping)
    _require(observed == expected, "%s keys mismatch; missing=%s unknown=%s" % (
        context,
        ",".join(sorted(expected - observed)) or "none",
        ",".join(sorted(observed - expected)) or "none",
    ))


def _safe_repo_path(value, context):
    _require(isinstance(value, str) and value, f"{context} must be a path")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts,
             f"{context} must stay inside the repository")
    return path


def validate_policy(data, root=ROOT, source="maintenance policy"):
    _exact_keys(data, {
        "schema_version", "policy_version", "project_status", "ownership",
        "branches", "support", "cadence", "deprecation", "security",
        "recovery", "automation", "required_documents",
    }, source)
    _require(data["schema_version"] == 1 and data["policy_version"] == 1,
             f"{source}: unsupported schema or policy version")
    _require(data["project_status"] == "preview",
             f"{source}: project_status must remain preview before release")

    ownership = data["ownership"]
    _exact_keys(ownership, {
        "project_maintainers", "security_maintainers", "release_maintainers",
        "bus_factor", "release_approval_minimum",
    }, "ownership")
    for role in ("project_maintainers", "security_maintainers", "release_maintainers"):
        handles = ownership[role]
        _require(isinstance(handles, list) and handles and
                 len(handles) == len(set(handles)) and
                 all(isinstance(item, str) and HANDLE.fullmatch(item)
                     for item in handles), f"ownership.{role} is invalid")
    _require(type(ownership["bus_factor"]) is int and ownership["bus_factor"] >= 1,
             "ownership.bus_factor must be a positive integer")
    _require(type(ownership["release_approval_minimum"]) is int and
             1 <= ownership["release_approval_minimum"] <=
             len(ownership["release_maintainers"]),
             "ownership.release_approval_minimum exceeds named maintainers")

    branches = data["branches"]
    _exact_keys(branches, {
        "integration", "release_pattern", "topic_prefix", "backport_categories",
        "direct_push", "history_rewrite",
    }, "branches")
    _require(branches["integration"] == "main" and
             branches["release_pattern"] ==
             "ahpy/<cython-major>.<cython-minor>" and
             isinstance(branches["topic_prefix"], str) and
             branches["topic_prefix"].endswith("/"),
             "branches do not match the release policy")
    _require(branches["backport_categories"] ==
             ["compatibility", "correctness", "packaging", "security"],
             "branches.backport_categories must be sorted and complete")
    _require(branches["direct_push"] is False and
             branches["history_rewrite"] is False,
             "release branches must reject direct pushes and history rewrites")

    support = data["support"]
    _exact_keys(support, {
        "preview_branch", "stable_release_lines",
        "maximum_simultaneous_stable_lines", "eol_requires_public_record",
        "unpublished_preview_has_sla",
    }, "support")
    _require(support["preview_branch"] == "main" and
             support["stable_release_lines"] == 0 and
             support["maximum_simultaneous_stable_lines"] == 1 and
             support["eol_requires_public_record"] is True and
             support["unpublished_preview_has_sla"] is False,
             "support must describe the unpublished single-line preview")

    cadence = data["cadence"]
    _exact_keys(cadence, {
        "dependency_updates", "cython_upstream_review", "hpy_review",
        "python_review", "platform_compiler_review", "security_scanning",
    }, "cadence")
    _require(all(value in CADENCE for value in cadence.values()),
             "cadence contains an unsupported interval")
    _require(cadence["security_scanning"] == "continuous-and-weekly",
             "security scanning must cover changes and a weekly schedule")

    deprecation = data["deprecation"]
    _exact_keys(deprecation, {
        "preview_notice_required", "stable_minimum_release_cycles",
        "stable_removal_release_boundary",
        "migration_document_required", "silent_abi_fallback_allowed",
        "emergency_exceptions", "emergency_owner_approval",
        "compatibility_surfaces", "notice_channels", "required_evidence",
    }, "deprecation")
    _require(deprecation["preview_notice_required"] is True and
             type(deprecation["stable_minimum_release_cycles"]) is int and
             deprecation["stable_minimum_release_cycles"] >= 1 and
             deprecation["stable_removal_release_boundary"] is True and
             deprecation["migration_document_required"] is True and
             deprecation["silent_abi_fallback_allowed"] is False and
             deprecation["emergency_exceptions"] == ["correctness", "security"] and
             deprecation["emergency_owner_approval"] is True and
             deprecation["compatibility_surfaces"] == [
                 "artifact", "cli", "diagnostic", "generated-source",
                 "runtime-semantics", "source"] and
             deprecation["notice_channels"] == [
                 "changelog", "migration-guide", "release-notes",
                 "support-matrix"] and
             deprecation["required_evidence"] == [
                 "action-id", "old-and-new-tests", "replacement-or-rationale"],
             "deprecation and compatibility-break contract is incomplete")

    security = data["security"]
    _exact_keys(security, {
        "private_advisory_url", "public_vulnerability_issues",
        "pre_stable_response_sla", "coordinated_upstream_disclosure",
    }, "security")
    _require(security["private_advisory_url"] ==
             "https://github.com/mburakmmm/aHPy/security/advisories/new" and
             security["public_vulnerability_issues"] is False and
             security["pre_stable_response_sla"] is False and
             security["coordinated_upstream_disclosure"] is True,
             "security policy must use private coordinated reporting")

    recovery = data["recovery"]
    _exact_keys(recovery, {
        "standard_defect_action", "replacement_version_required",
        "public_reason_required", "delete_allowed_for",
        "unyank_requires_owner_approval", "security_coordination",
        "backport_regression_test_required",
        "backport_mandatory_matrix_required", "support_expansion_allowed",
    }, "recovery")
    _require(
        recovery["standard_defect_action"] == "yank" and
        recovery["replacement_version_required"] is True and
        recovery["public_reason_required"] is True and
        recovery["delete_allowed_for"] == [
            "credential-disclosure", "legal-demand", "malware"] and
        recovery["unyank_requires_owner_approval"] is True and
        recovery["security_coordination"] == "private-until-disclosure" and
        recovery["backport_regression_test_required"] is True and
        recovery["backport_mandatory_matrix_required"] is True and
        recovery["support_expansion_allowed"] is False,
        "release recovery policy is incomplete or unsafe")

    automation = data["automation"]
    _exact_keys(automation, {
        "security_workflow", "dependabot", "codeql_languages",
        "dependency_review", "immutable_action_pins",
    }, "automation")
    _require(automation["codeql_languages"] == ["c-cpp", "python"] and
             automation["dependency_review"] is True and
             automation["immutable_action_pins"] is True,
             "security automation contract is incomplete")
    automation_paths = [
        _safe_repo_path(automation["security_workflow"], "automation.security_workflow"),
        _safe_repo_path(automation["dependabot"], "automation.dependabot"),
    ]

    documents = data["required_documents"]
    _require(isinstance(documents, list) and documents and
             len(documents) == len(set(documents)),
             "required_documents must be a unique non-empty array")
    document_paths = [
        _safe_repo_path(value, "required_documents") for value in documents]
    missing = [str(path) for path in (*automation_paths, *document_paths)
               if not (Path(root) / path).is_file()]
    _require(not missing, "required maintenance files are missing: %s" %
             ", ".join(missing))
    return data


def load_policy(path=DEFAULT_POLICY, root=ROOT):
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MaintenancePolicyError(f"cannot read maintenance policy {path}: {exc}") from exc
    return validate_policy(data, root=root, source=str(path))


def render_text(policy):
    owners = policy["ownership"]
    cadence = policy["cadence"]
    return (
        "aHPy maintenance policy: valid\n"
        f"project status: {policy['project_status']}\n"
        f"project maintainers: {', '.join(owners['project_maintainers'])}\n"
        f"bus factor: {owners['bus_factor']}\n"
        f"dependency updates: {cadence['dependency_updates']}\n"
        f"security scanning: {cadence['security_scanning']}\n"
        f"standard recovery: {policy['recovery']['standard_defect_action']}\n"
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
    except MaintenancePolicyError as exc:
        parser.error(str(exc))
    if options.as_json:
        rendered = json.dumps(policy, indent=2, sort_keys=True) + "\n"
    else:
        rendered = render_text(policy)
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
