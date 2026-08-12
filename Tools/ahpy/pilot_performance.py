"""Validate comparable, non-release performance evidence from PRD-8 pilots."""

from __future__ import annotations

import json
import math


ENVIRONMENT_FIELDS = {
    "python_implementation",
    "python_version",
    "hpy_version",
    "platform",
    "machine",
}
NUMERIC_FIELDS = (
    "compiled_ns_per_call",
    "python_reference_ns_per_call",
    "compiled_to_python_ratio",
)


def validate_performance(report, expected_workloads=None):
    """Validate an exact pilot benchmark schema and complete finite samples."""
    if not isinstance(report, dict):
        raise AssertionError("pilot performance report must be an object")
    if report.get("schema_version") != 1:
        raise AssertionError("pilot performance schema_version must be 1")
    environment = report.get("environment")
    if not isinstance(environment, dict) or set(environment) != ENVIRONMENT_FIELDS \
            or not all(isinstance(value, str) and value for value in
                       environment.values()):
        raise AssertionError("pilot performance environment is incomplete")
    workloads = report.get("workloads")
    expected = set(expected_workloads) if expected_workloads is not None else None
    if not isinstance(workloads, dict) or not workloads or \
            (expected is not None and set(workloads) != expected):
        raise AssertionError("pilot performance workloads differ from contract")
    for name, workload in workloads.items():
        if not isinstance(workload, dict):
            raise AssertionError(f"invalid {name} performance workload")
        iterations = workload.get("iterations")
        repeats = workload.get("repeats")
        if type(iterations) is not int or iterations <= 0 \
                or type(repeats) is not int or repeats < 3:
            raise AssertionError(f"invalid {name} performance sampling contract")
        for field in NUMERIC_FIELDS:
            value = workload.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) \
                    or value <= 0:
                raise AssertionError(f"invalid {name} performance field {field}")
    return report


def read_performance(path, expected_workloads):
    """Read and validate one pilot benchmark report from disk."""
    try:
        report = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"invalid pilot performance report: {exc}") from None
    return validate_performance(report, expected_workloads)
