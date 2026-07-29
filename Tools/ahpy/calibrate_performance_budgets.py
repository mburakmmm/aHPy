#!/usr/bin/env python3
"""Build a fail-closed release-budget proposal from hosted benchmark history."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import statistics

from benchmark_hpy import OPERATIONS


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_MINIMUM_REPORTS = 5
DEFAULT_MARGIN = 0.20


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive_number(value, field):
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool) and
        math.isfinite(value) and value > 0,
        "%s must be a positive finite number" % field,
    )
    return value


def _positive_integer(value, field):
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value > 0,
        "%s must be a positive integer" % field,
    )
    return value


def load_hosted_report(path):
    path = Path(path)
    try:
        report = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read benchmark report %s: %s" % (
            path, error)) from None

    _require(report.get("schema_version") == 1,
             "%s has unsupported benchmark schema" % path)
    _require(report.get("violations") == [],
             "%s contains benchmark violations" % path)
    _require(report.get("debug_leak_check") == "passed",
             "%s lacks a passing HPy Debug check" % path)
    _require(
        isinstance(report.get("created_utc"), str) and report["created_utc"],
        "%s lacks a creation timestamp" % path,
    )

    provenance = report.get("provenance")
    _require(isinstance(provenance, dict),
             "%s lacks benchmark provenance" % path)
    commit = provenance.get("source_commit")
    _require(isinstance(commit, str) and COMMIT_RE.fullmatch(commit),
             "%s has an invalid source commit" % path)
    _require(provenance.get("execution") == "github-actions",
             "%s is not hosted GitHub Actions evidence" % path)

    github = provenance.get("github")
    _require(isinstance(github, dict),
             "%s lacks GitHub Actions provenance" % path)
    _require(github.get("sha") == commit,
             "%s GitHub SHA differs from its source commit" % path)
    _positive_integer(github.get("run_id"), "%s github.run_id" % path)
    _positive_integer(
        github.get("run_attempt"), "%s github.run_attempt" % path)
    for field in ("repository", "workflow_ref", "job"):
        _require(
            isinstance(github.get(field), str) and github[field].strip(),
            "%s github.%s is missing" % (path, field),
        )

    environment = report.get("environment")
    _require(isinstance(environment, dict),
             "%s lacks benchmark environment" % path)
    for field in (
            "python_implementation", "python_version", "machine",
            "hpy_version"):
        _require(
            isinstance(environment.get(field), str) and environment[field],
            "%s environment.%s is missing" % (path, field),
        )

    measurement = report.get("measurement")
    _require(isinstance(measurement, dict),
             "%s lacks measurement contract" % path)
    for field in ("iterations", "repeats"):
        _positive_integer(
            measurement.get(field), "%s measurement.%s" % (path, field))
    _require(
        isinstance(measurement.get("warmups"), int) and
        not isinstance(measurement["warmups"], bool) and
        measurement["warmups"] >= 0,
        "%s measurement.warmups must be a non-negative integer" % path,
    )

    build = report.get("build")
    _require(isinstance(build, dict), "%s lacks build evidence" % path)
    compiler = build.get("compiler")
    _require(isinstance(compiler, str) and compiler,
             "%s lacks compiler identity" % path)
    runtime = report.get("runtime")
    _require(isinstance(runtime, dict) and set(runtime) == set(OPERATIONS),
             "%s runtime operations differ from the release corpus" % path)
    for operation in OPERATIONS:
        _require(
            isinstance(runtime[operation], dict),
            "%s runtime.%s must be an object" % (path, operation),
        )
        _positive_number(
            runtime[operation].get("ratio"),
            "%s runtime.%s.ratio" % (path, operation),
        )

    footprint = report.get("footprint")
    _require(isinstance(footprint, dict),
             "%s lacks footprint evidence" % path)
    for field in (
            "generated_c_bytes", "reference_c_bytes",
            "generated_binary_bytes", "reference_binary_bytes",
            "binary_to_reference_ratio"):
        _positive_number(
            footprint.get(field), "%s footprint.%s" % (path, field))

    large_type = report.get("large_type_compile")
    _require(isinstance(large_type, dict),
             "%s lacks large-type compile evidence" % path)
    o0 = large_type.get("o0")
    _require(isinstance(o0, dict),
             "%s lacks large-type O0 evidence" % path)
    _require(o0.get("timed_out") is False,
             "%s required large-type O0 compile timed out" % path)
    _positive_number(
        o0.get("seconds"),
        "%s large_type_compile.o0.seconds" % path,
    )
    return report


def _cohort_key(report):
    environment = report["environment"]
    return {
        "repository": report["provenance"]["github"]["repository"],
        "workflow_ref": report["provenance"]["github"]["workflow_ref"],
        "python_implementation": environment["python_implementation"],
        "python_version": environment["python_version"],
        "machine": environment["machine"],
        "hpy_version": environment["hpy_version"],
        "compiler": report["build"]["compiler"],
        "measurement": report["measurement"],
    }


def _nearest_rank(values, percentile):
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _ceil_limit(value, margin, digits=2):
    scale = 10 ** digits
    return math.ceil(value * (1.0 + margin) * scale) / scale


def calibrate(
        report_paths, *, expected_commit, repository,
        minimum_reports=DEFAULT_MINIMUM_REPORTS, margin=DEFAULT_MARGIN):
    _require(
        isinstance(expected_commit, str) and
        COMMIT_RE.fullmatch(expected_commit),
        "expected commit must be a full lowercase Git commit",
    )
    _require(isinstance(repository, str) and repository.strip(),
             "repository must be non-empty")
    _positive_integer(minimum_reports, "minimum_reports")
    _require(
        isinstance(margin, (int, float)) and not isinstance(margin, bool) and
        math.isfinite(margin) and 0 < margin <= 1,
        "margin must be within (0, 1]",
    )

    reports = [load_hosted_report(path) for path in report_paths]
    _require(
        len(reports) >= minimum_reports,
        "release calibration requires at least %d hosted reports; got %d" %
        (minimum_reports, len(reports)),
    )
    for report in reports:
        provenance = report["provenance"]
        _require(
            provenance["source_commit"] == expected_commit,
            "report source commit differs from expected release commit",
        )
        _require(
            provenance["github"]["repository"] == repository,
            "report repository differs from expected repository",
        )

    identities = [
        (
            report["provenance"]["github"]["repository"],
            report["provenance"]["github"]["run_id"],
            report["provenance"]["github"]["run_attempt"],
        )
        for report in reports
    ]
    _require(len(set(identities)) == len(identities),
             "duplicate GitHub run evidence is not allowed")
    reports.sort(
        key=lambda report: (
            report["provenance"]["github"]["run_id"],
            report["provenance"]["github"]["run_attempt"],
        )
    )

    cohort = _cohort_key(reports[0])
    for report in reports[1:]:
        _require(
            _cohort_key(report) == cohort,
            "hosted reports do not share one release measurement cohort",
        )

    deterministic_fields = (
        "generated_c_bytes", "reference_c_bytes",
        "generated_binary_bytes", "reference_binary_bytes",
    )
    for field in deterministic_fields:
        values = {report["footprint"][field] for report in reports}
        _require(
            len(values) == 1,
            "footprint.%s is not byte-stable within the cohort" % field,
        )

    runtime = {}
    for operation in OPERATIONS:
        values = [report["runtime"][operation]["ratio"] for report in reports]
        observed_max = max(values)
        runtime[operation] = {
            "samples": values,
            "median": round(statistics.median(values), 6),
            "p95_nearest_rank": round(_nearest_rank(values, 0.95), 6),
            "maximum": round(observed_max, 6),
            "proposed_maximum": _ceil_limit(observed_max, margin),
        }

    binary_ratios = [
        report["footprint"]["binary_to_reference_ratio"]
        for report in reports
    ]
    o0_seconds = [
        report["large_type_compile"]["o0"]["seconds"] for report in reports
    ]
    run_evidence = sorted(
        (
            {
                "run_id": report["provenance"]["github"]["run_id"],
                "run_attempt": report["provenance"]["github"]["run_attempt"],
                "created_utc": report.get("created_utc"),
            }
            for report in reports
        ),
        key=lambda item: (item["run_id"], item["run_attempt"]),
    )
    return {
        "schema_version": 1,
        "proposal_only": True,
        "apply_automatically": False,
        "source_commit": expected_commit,
        "cohort": cohort,
        "report_count": len(reports),
        "minimum_reports": minimum_reports,
        "headroom_fraction": margin,
        "runs": run_evidence,
        "runtime_ratio": runtime,
        "footprint": {
            field: reports[0]["footprint"][field]
            for field in deterministic_fields
        } | {
            "binary_to_reference_ratio_maximum": round(
                max(binary_ratios), 6),
            "binary_to_reference_ratio_proposed_maximum": _ceil_limit(
                max(binary_ratios), margin),
        },
        "large_type_compile": {
            "o0_seconds_median": round(statistics.median(o0_seconds), 6),
            "o0_seconds_p95_nearest_rank": round(
                _nearest_rank(o0_seconds, 0.95), 6),
            "o0_seconds_maximum": round(max(o0_seconds), 6),
            "o3_timeout_count": sum(
                report["large_type_compile"].get(
                    "o3", {}).get("timed_out") is True
                for report in reports
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--minimum-reports", type=int, default=DEFAULT_MINIMUM_REPORTS)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        proposal = calibrate(
            args.reports,
            expected_commit=args.expected_commit,
            repository=args.repository,
            minimum_reports=args.minimum_reports,
            margin=args.margin,
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(proposal, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    print(
        "aHPy release performance proposal prepared from %d hosted runs: %s" %
        (proposal["report_count"], args.output)
    )


if __name__ == "__main__":
    main()
