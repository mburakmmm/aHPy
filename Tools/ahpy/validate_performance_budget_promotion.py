#!/usr/bin/env python3
"""Verify that release budgets exactly promote one reviewed calibration proposal."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from benchmark_hpy import COMMIT_RE, OPERATIONS, load_budgets, validate_budgets
from calibrate_performance_budgets import CALIBRATION_SCHEMA_VERSION


PROMOTION_SCHEMA_VERSION = 1
RELEASE_ABSOLUTE_PROPOSALS = {
    "cython_seconds": ("build_time", "cython_seconds"),
    "native_build_seconds": ("build_time", "native_build_seconds"),
    "generated_peak_rss_bytes": (
        "peak_memory", "generated_peak_rss_bytes"),
    "generated_to_reference_peak_rss_ratio": (
        "peak_memory", "generated_to_reference_ratio"),
    "large_type_frontend_seconds": (
        "large_type_compile", "frontend_seconds"),
    "large_type_o0_seconds": ("large_type_compile", "o0_seconds"),
}
FOOTPRINT_PROPOSALS = {
    "generated_c_bytes": "generated_c_bytes_proposed_maximum",
    "generated_binary_bytes": "generated_binary_bytes_proposed_maximum",
    "binary_to_reference_ratio":
        "binary_to_reference_ratio_proposed_maximum",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive_integer(value, field):
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value > 0,
        "%s must be a positive integer" % field,
    )
    return value


def _positive_number(value, field):
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool) and
        math.isfinite(value) and value > 0,
        "%s must be a positive finite number" % field,
    )
    return value


def _proposed_maximum(proposal, path):
    value = proposal
    field = []
    for part in path:
        field.append(part)
        _require(
            isinstance(value, dict) and part in value,
            "proposal.%s is missing" % ".".join(field),
        )
        value = value[part]
    _require(
        isinstance(value, dict) and "proposed_maximum" in value,
        "proposal.%s.proposed_maximum is missing" % ".".join(path),
    )
    return _positive_number(
        value["proposed_maximum"],
        "proposal.%s.proposed_maximum" % ".".join(path),
    )


def validate_proposal(proposal):
    """Validate the immutable inputs needed to review a promotion."""
    _require(isinstance(proposal, dict), "calibration proposal must be an object")
    _require(
        proposal.get("schema_version") == CALIBRATION_SCHEMA_VERSION,
        "calibration proposal schema_version must be %d" %
        CALIBRATION_SCHEMA_VERSION,
    )
    _require(
        proposal.get("proposal_only") is True and
        proposal.get("apply_automatically") is False,
        "calibration proposal must remain proposal-only and non-automatic",
    )
    source_commit = proposal.get("source_commit")
    _require(
        isinstance(source_commit, str) and COMMIT_RE.fullmatch(source_commit),
        "calibration proposal source_commit must be a full lowercase Git commit",
    )
    report_count = _positive_integer(
        proposal.get("report_count"), "proposal.report_count")
    minimum_reports = _positive_integer(
        proposal.get("minimum_reports"), "proposal.minimum_reports")
    _require(
        report_count >= minimum_reports,
        "calibration proposal has fewer reports than its declared minimum",
    )

    policy = proposal.get("input_budget_policy")
    contract = proposal.get("input_budget_contract")
    try:
        validate_budgets(contract)
    except ValueError as error:
        raise ValueError(
            "calibration proposal input budget contract is invalid: %s" %
            error) from None
    environment = contract.get("environment")
    _require(
        isinstance(environment, dict) and
        environment.get("abi") == "universal" and
        all(
            isinstance(environment.get(field), str) and environment[field]
            for field in ("hpy", "python_implementation")
        ),
        "calibration proposal input environment is not Universal HPy",
    )
    _require(
        contract["policy"] == policy,
        "calibration proposal input policy differs from its contract",
    )
    _require(
        policy["classification"] == "regression" and
        policy["release_enforced"] is False and
        policy["calibration_status"] == "hosted-history-pending" and
        policy["candidate_binding"] == "unbound" and
        policy["calibration_source_commit"] == "",
        "calibration proposal input policy is not pending regression policy",
    )
    _require(
        minimum_reports >= policy["minimum_hosted_reports"],
        "calibration proposal minimum weakens its input budget policy",
    )

    runtime = proposal.get("runtime_ratio")
    _require(
        isinstance(runtime, dict) and set(runtime) == set(OPERATIONS),
        "calibration proposal runtime operations differ from the release corpus",
    )
    for operation in OPERATIONS:
        _proposed_maximum(proposal, ("runtime_ratio", operation))
    footprint = proposal.get("footprint")
    _require(isinstance(footprint, dict), "calibration proposal lacks footprint")
    for proposal_field in FOOTPRINT_PROPOSALS.values():
        _positive_number(
            footprint.get(proposal_field),
            "proposal.footprint.%s" % proposal_field,
        )
    for path in RELEASE_ABSOLUTE_PROPOSALS.values():
        _proposed_maximum(proposal, path)
    return proposal


def load_proposal(path):
    path = Path(path)
    try:
        proposal = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            "cannot read calibration proposal %s: %s" % (path, error)
        ) from None
    return validate_proposal(proposal)


def _require_equal(actual, expected, field):
    _require(
        actual == expected,
        "%s differs from the reviewed calibration proposal" % field,
    )


def validate_promotion(proposal_path, budget_path):
    """Return a summary only when a release budget is an exact promotion."""
    proposal = load_proposal(proposal_path)
    try:
        budgets = load_budgets(budget_path)
    except (OSError, ValueError) as error:
        raise ValueError(
            "cannot read release budget %s: %s" % (budget_path, error)
        ) from None

    policy = budgets["policy"]
    _require(
        policy["classification"] == "release",
        "promoted performance budget must use release policy",
    )
    _require_equal(
        policy["calibration_source_commit"], proposal["source_commit"],
        "policy.calibration_source_commit",
    )
    _require(
        proposal["report_count"] >= policy["minimum_hosted_reports"],
        "reviewed proposal has fewer reports than the release policy requires",
    )
    input_contract = proposal["input_budget_contract"]
    for section in ("environment", "measurement", "large_type_compile"):
        _require_equal(
            budgets[section], input_contract[section], section,
        )

    checked_fields = 0
    for operation in OPERATIONS:
        _require_equal(
            budgets["runtime_ratio"][operation],
            _proposed_maximum(proposal, ("runtime_ratio", operation)),
            "runtime_ratio.%s" % operation,
        )
        checked_fields += 1
    for budget_field, proposal_field in FOOTPRINT_PROPOSALS.items():
        _require_equal(
            budgets["footprint"][budget_field],
            proposal["footprint"][proposal_field],
            "footprint.%s" % budget_field,
        )
        checked_fields += 1
    for budget_field, proposal_path_parts in \
            RELEASE_ABSOLUTE_PROPOSALS.items():
        _require_equal(
            budgets["release_absolute"][budget_field],
            _proposed_maximum(proposal, proposal_path_parts),
            "release_absolute.%s" % budget_field,
        )
        checked_fields += 1

    return {
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "status": "valid",
        "calibration_source_commit": proposal["source_commit"],
        "report_count": proposal["report_count"],
        "checked_fields": checked_fields,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path)
    parser.add_argument("budget", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_promotion(args.proposal, args.budget)
    except ValueError as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "aHPy release performance promotion is valid: "
            "%d thresholds from %d hosted reports (%s)" % (
                result["checked_fields"], result["report_count"],
                result["calibration_source_commit"],
            )
        )


if __name__ == "__main__":
    main()
