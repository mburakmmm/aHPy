from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import benchmark_hpy


class BenchmarkHPyTest(unittest.TestCase):
    @staticmethod
    def _module():
        def raise_value():
            raise ValueError("aHPy benchmark")

        return SimpleNamespace(
            identity=lambda value: value,
            add=lambda left, right: left + right,
            make_pair=lambda left, right: [left, right],
            get_value=lambda value: value.value,
            call_zero=lambda callable_object: callable_object(),
            raise_value=raise_value,
        )

    def _report(self):
        return {
            "runtime": {
                name: {"ratio": 1.0}
                for name in benchmark_hpy.OPERATIONS
            },
            "footprint": {
                "generated_c_bytes": 100,
                "generated_binary_bytes": 200,
                "binary_to_reference_ratio": 2.0,
            },
        }

    def _budgets(self):
        return {
            "runtime_ratio": {
                name: 2.0 for name in benchmark_hpy.OPERATIONS
            },
            "footprint": {
                "generated_c_bytes": 1000,
                "generated_binary_bytes": 2000,
                "binary_to_reference_ratio": 4.0,
            },
        }

    def test_thresholds_accept_report_inside_all_budgets(self):
        self.assertEqual(
            benchmark_hpy.check_thresholds(self._report(), self._budgets()), [])

    def test_thresholds_report_runtime_and_footprint_regressions(self):
        report = self._report()
        report["runtime"]["call"]["ratio"] = 2.5
        report["footprint"]["generated_c_bytes"] = 1001
        violations = benchmark_hpy.check_thresholds(report, self._budgets())
        self.assertEqual(len(violations), 2)
        self.assertIn("runtime.call", violations[0])
        self.assertIn("generated_c_bytes", violations[1])

    def test_budget_schema_requires_exact_operation_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "budgets.toml"
            path.write_text(
                "schema_version = 1\n"
                "[runtime_ratio]\nidentity = 2.0\n"
                "[footprint]\ngenerated_c_bytes = 1\n",
                encoding="utf8",
            )
            with self.assertRaisesRegex(ValueError, "runtime ratio keys differ"):
                benchmark_hpy.load_budgets(path)

    def test_environment_pin_mismatch_is_rejected(self):
        report = {
            "environment": {
                "hpy_version": "0.10.0",
                "python_implementation": "CPython",
            },
        }
        budgets = {
            "environment": {
                "abi": "universal",
                "hpy": "0.9.0",
                "python_implementation": "CPython",
            },
        }
        self.assertEqual(
            benchmark_hpy.check_environment(report, budgets),
            ["environment.hpy '0.10.0' does not match budget '0.9.0'"],
        )

    def test_default_budget_file_is_valid_and_json_serializable(self):
        budgets = benchmark_hpy.load_budgets(benchmark_hpy.DEFAULT_BUDGETS)
        self.assertEqual(budgets["schema_version"], 1)
        self.assertEqual(tuple(budgets["runtime_ratio"]),
                         benchmark_hpy.OPERATIONS)
        json.dumps(budgets, sort_keys=True)

    def test_measurement_exercises_every_operation_and_reports_samples(self):
        module = self._module()
        with (
            mock.patch.object(
                benchmark_hpy.importlib, "import_module", return_value=module),
            mock.patch.object(
                benchmark_hpy.importlib.metadata, "version", return_value="0.9.0"),
        ):
            report = benchmark_hpy.measure_loaded_modules(
                Path("unused"), iterations=20, warmups=1, repeats=3)
        self.assertEqual(tuple(report["runtime"]), benchmark_hpy.OPERATIONS)
        for operation in benchmark_hpy.OPERATIONS:
            result = report["runtime"][operation]
            self.assertEqual(len(result["generated_samples"]), 3)
            self.assertEqual(len(result["reference_samples"]), 3)
            self.assertGreater(result["ratio"], 0.0)
        self.assertEqual(report["environment"]["hpy_version"], "0.9.0")

    def test_semantic_check_rejects_wrong_reference_behavior(self):
        module = self._module()
        module.add = lambda left, right: 0
        with self.assertRaisesRegex(AssertionError, "arithmetic semantic mismatch"):
            benchmark_hpy._verify_semantics(module)


if __name__ == "__main__":
    unittest.main()
