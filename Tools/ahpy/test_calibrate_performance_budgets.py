from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import calibrate_performance_budgets as calibration


COMMIT = "a" * 40
REPOSITORY = "owner/aHPy"


class PerformanceBudgetCalibrationTest(unittest.TestCase):
    def _report(self, run_id, **updates):
        runtime = {
            operation: {"ratio": round(1.0 + run_id / 1000, 6)}
            for operation in calibration.OPERATIONS
        }
        report = {
            "schema_version": 1,
            "created_utc": "2026-07-29T00:00:%02d+00:00" % run_id,
            "violations": [],
            "debug_leak_check": "passed",
            "provenance": {
                "source_commit": COMMIT,
                "execution": "github-actions",
                "github": {
                    "repository": REPOSITORY,
                    "run_id": run_id,
                    "run_attempt": 1,
                    "sha": COMMIT,
                    "workflow_ref": "owner/aHPy/.github/workflows/"
                                    "ahpy-universal.yml@refs/pull/2/merge",
                    "job": "compiler-and-quality",
                },
            },
            "environment": {
                "python_implementation": "CPython",
                "python_version": "3.11.15",
                "platform": "Linux-test",
                "machine": "x86_64",
                "hpy_version": "0.9.0",
            },
            "measurement": {
                "iterations": 100000,
                "warmups": 2,
                "repeats": 7,
            },
            "build": {"compiler": "gcc 13.3.0"},
            "runtime": runtime,
            "footprint": {
                "generated_c_bytes": 30000,
                "reference_c_bytes": 10000,
                "generated_binary_bytes": 76000,
                "reference_binary_bytes": 75000,
                "binary_to_reference_ratio": 1.013333,
            },
            "large_type_compile": {
                "o0": {"seconds": 5.0 + run_id / 100, "timed_out": False},
                "o3": {"seconds": 60.0, "timed_out": True},
            },
        }
        for dotted_name, value in updates.items():
            target = report
            parts = dotted_name.split("__")
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        return report

    def _write_reports(self, root, count=5, **updates):
        paths = []
        for run_id in range(1, count + 1):
            path = Path(root) / ("report-%d.json" % run_id)
            path.write_text(
                json.dumps(self._report(run_id, **updates)),
                encoding="utf8",
            )
            paths.append(path)
        return paths

    def test_five_unique_hosted_reports_produce_proposal_only_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = self._write_reports(temp_dir)
            result = calibration.calibrate(
                reports,
                expected_commit=COMMIT,
                repository=REPOSITORY,
            )
        self.assertEqual(result["report_count"], 5)
        self.assertTrue(result["proposal_only"])
        self.assertFalse(result["apply_automatically"])
        self.assertEqual([run["run_id"] for run in result["runs"]],
                         [1, 2, 3, 4, 5])
        identity = result["runtime_ratio"]["identity"]
        self.assertEqual(identity["maximum"], 1.005)
        self.assertEqual(identity["p95_nearest_rank"], 1.005)
        self.assertEqual(identity["proposed_maximum"], 1.21)
        self.assertEqual(result["large_type_compile"]["o3_timeout_count"], 5)

    def test_report_order_does_not_change_proposal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = self._write_reports(temp_dir)
            first = calibration.calibrate(
                reports, expected_commit=COMMIT, repository=REPOSITORY)
            second = calibration.calibrate(
                reversed(reports),
                expected_commit=COMMIT,
                repository=REPOSITORY,
            )
        self.assertEqual(first, second)

    def test_too_few_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = self._write_reports(temp_dir, count=4)
            with self.assertRaisesRegex(ValueError, "at least 5"):
                calibration.calibrate(
                    reports,
                    expected_commit=COMMIT,
                    repository=REPOSITORY,
                )

    def test_duplicate_run_attempt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = self._write_reports(temp_dir)
            duplicate = Path(temp_dir) / "duplicate.json"
            duplicate.write_text(reports[0].read_text(), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "duplicate GitHub"):
                calibration.calibrate(
                    reports + [duplicate],
                    expected_commit=COMMIT,
                    repository=REPOSITORY,
                )

    def test_one_matrix_run_accepts_five_distinct_sample_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = []
            for sample_id in range(1, 6):
                report = self._report(
                    100,
                    provenance__github__sample_id=str(sample_id),
                )
                path = Path(temp_dir) / ("sample-%d.json" % sample_id)
                path.write_text(json.dumps(report), encoding="utf8")
                reports.append(path)
            result = calibration.calibrate(
                reports,
                expected_commit=COMMIT,
                repository=REPOSITORY,
            )
        self.assertEqual(result["report_count"], 5)
        self.assertEqual(
            [run["sample_id"] for run in result["runs"]],
            ["1", "2", "3", "4", "5"],
        )

    def test_mixed_commit_repository_and_cohort_are_rejected(self):
        cases = (
            ("provenance__source_commit", "b" * 40, "source commit"),
            ("provenance__github__repository", "other/repo", "repository"),
            ("environment__python_version", "3.14.6", "cohort"),
            ("footprint__generated_c_bytes", 30001, "byte-stable"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temp_dir:
                    reports = self._write_reports(temp_dir)
                    report = json.loads(reports[-1].read_text())
                    target = report
                    parts = field.split("__")
                    for part in parts[:-1]:
                        target = target[part]
                    target[parts[-1]] = value
                    if field == "provenance__source_commit":
                        report["provenance"]["github"]["sha"] = value
                    reports[-1].write_text(json.dumps(report), encoding="utf8")
                    with self.assertRaisesRegex(ValueError, message):
                        calibration.calibrate(
                            reports,
                            expected_commit=COMMIT,
                            repository=REPOSITORY,
                        )

    def test_local_failed_debug_and_timed_out_reports_are_rejected(self):
        cases = (
            ("provenance__execution", "local", "not hosted"),
            ("violations", ["runtime.call"], "violations"),
            ("debug_leak_check", "failed", "Debug"),
            ("large_type_compile__o0__timed_out", True, "timed out"),
            ("provenance__github__sample_id", "", "sample_id"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = self._write_reports(temp_dir, count=1)[0]
                    report = json.loads(path.read_text())
                    target = report
                    parts = field.split("__")
                    for part in parts[:-1]:
                        target = target[part]
                    target[parts[-1]] = value
                    path.write_text(json.dumps(report), encoding="utf8")
                    with self.assertRaisesRegex(ValueError, message):
                        calibration.load_hosted_report(path)

    def test_invalid_json_and_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text("{", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "cannot read"):
                calibration.load_hosted_report(path)
            path.write_text(json.dumps({"schema_version": 2}), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                calibration.load_hosted_report(path)

    def test_runtime_contract_and_numeric_fields_are_validated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_reports(temp_dir, count=1)[0]
            report = json.loads(path.read_text())
            del report["runtime"]["call"]
            path.write_text(json.dumps(report), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "operations differ"):
                calibration.load_hosted_report(path)
            report = self._report(1)
            report["runtime"]["call"]["ratio"] = float("inf")
            path.write_text(json.dumps(report), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "positive finite"):
                calibration.load_hosted_report(path)

    def test_calibration_arguments_are_fail_closed(self):
        cases = (
            ({"expected_commit": "short"}, "full lowercase"),
            ({"repository": ""}, "non-empty"),
            ({"minimum_reports": 0}, "positive integer"),
            ({"margin": 0}, "within"),
            ({"margin": 1.1}, "within"),
        )
        for changes, message in cases:
            with self.subTest(changes=changes):
                arguments = {
                    "expected_commit": COMMIT,
                    "repository": REPOSITORY,
                    "minimum_reports": 5,
                    "margin": 0.2,
                }
                arguments.update(changes)
                with self.assertRaisesRegex(ValueError, message):
                    calibration.calibrate([], **arguments)

    def test_main_writes_machine_readable_proposal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = self._write_reports(temp_dir)
            output = Path(temp_dir) / "nested" / "proposal.json"
            argv = [
                "calibrate_performance_budgets.py",
                *(str(path) for path in reports),
                "--expected-commit", COMMIT,
                "--repository", REPOSITORY,
                "--output", str(output),
            ]
            with mock.patch("sys.argv", argv):
                calibration.main()
            proposal = json.loads(output.read_text())
        self.assertEqual(proposal["source_commit"], COMMIT)
        self.assertEqual(proposal["report_count"], 5)


if __name__ == "__main__":
    unittest.main()
