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

        class BenchmarkBox:
            def __init__(self, value, /):
                self.value = value

            def identity(self):
                return self.value

        return SimpleNamespace(
            identity=lambda value, /: value,
            add=lambda left, right, /: left + right,
            make_pair=lambda left, right, /: [left, right],
            get_value=lambda value, /: value.value,
            call_zero=lambda callable_object, /: callable_object(),
            raise_value=raise_value,
            BenchmarkBox=BenchmarkBox,
            external_add=lambda: 42,
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
            "large_type_compile": {
                "o0": {"timed_out": False},
                "o3": {"timed_out": False},
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
            "large_type_compile": {"enforce_o3": True},
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
        self.assertEqual(
            budgets["large_type_compile"]["timeout_seconds"], 60)
        self.assertFalse(budgets["large_type_compile"]["enforce_o3"])
        self.assertEqual(tuple(budgets["runtime_ratio"]),
                         benchmark_hpy.OPERATIONS)
        json.dumps(budgets, sort_keys=True)

    def test_local_benchmark_provenance_records_exact_source_commit(self):
        with mock.patch.object(
                benchmark_hpy, "source_commit", return_value="a" * 40):
            result = benchmark_hpy.benchmark_provenance({})
        self.assertEqual(result, {
            "source_commit": "a" * 40,
            "execution": "local",
            "github": None,
        })

    def test_hosted_benchmark_provenance_is_complete_and_typed(self):
        environment = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "owner/aHPy",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKFLOW_REF": "owner/aHPy/workflow.yml@refs/heads/main",
            "GITHUB_JOB": "compiler-and-quality",
        }
        with mock.patch.object(
                benchmark_hpy, "source_commit", return_value="a" * 40):
            result = benchmark_hpy.benchmark_provenance(environment)
        self.assertEqual(result["execution"], "github-actions")
        self.assertEqual(result["github"]["run_id"], 123)
        self.assertEqual(result["github"]["run_attempt"], 2)
        self.assertEqual(result["github"]["sha"], "a" * 40)

    def test_hosted_benchmark_provenance_rejects_missing_or_wrong_identity(self):
        base = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "owner/aHPy",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKFLOW_REF": "owner/aHPy/workflow.yml@refs/heads/main",
            "GITHUB_JOB": "compiler-and-quality",
        }
        with mock.patch.object(
                benchmark_hpy, "source_commit", return_value="a" * 40):
            missing = dict(base)
            del missing["GITHUB_JOB"]
            with self.assertRaisesRegex(ValueError, "incomplete"):
                benchmark_hpy.benchmark_provenance(missing)
            wrong = dict(base, GITHUB_SHA="b" * 40)
            with self.assertRaisesRegex(ValueError, "differs"):
                benchmark_hpy.benchmark_provenance(wrong)
            non_integer = dict(base, GITHUB_RUN_ID="not-an-integer")
            with self.assertRaisesRegex(ValueError, "must be integers"):
                benchmark_hpy.benchmark_provenance(non_integer)
            non_positive = dict(base, GITHUB_RUN_ID="0")
            with self.assertRaisesRegex(ValueError, "must be positive"):
                benchmark_hpy.benchmark_provenance(non_positive)

    def test_native_compile_command_keeps_optimization_and_universal_abi(self):
        command = benchmark_hpy._native_compile_command(
            "ccache clang", 3, Path("include"), Path("input.c"),
            Path("output.o"))
        self.assertEqual(command[:2], ["ccache", "clang"])
        self.assertIn("-O3", command)
        self.assertIn("-DHPY_ABI_UNIVERSAL", command)
        self.assertIn("-Iinclude", command)

    def test_thresholds_reject_large_type_compile_timeout(self):
        report = self._report()
        report["large_type_compile"] = {
            "o0": {"timed_out": False}, "o3": {"timed_out": True}}
        violations = benchmark_hpy.check_thresholds(report, self._budgets())
        self.assertIn(
            "large_type_compile.o3 exceeded timeout budget", violations)

    def test_diagnostic_o3_timeout_does_not_fail_required_o0_gate(self):
        report = self._report()
        report["large_type_compile"]["o3"]["timed_out"] = True
        budgets = self._budgets()
        budgets["large_type_compile"]["enforce_o3"] = False
        self.assertEqual(benchmark_hpy.check_thresholds(report, budgets), [])

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

    def test_single_measurement_has_no_cross_abi_ratio(self):
        module = self._module()
        with mock.patch.object(
                benchmark_hpy.importlib, "import_module", return_value=module):
            report = benchmark_hpy.measure_single_loaded_module(
                Path("unused"), "classic", iterations=20,
                warmups=1, repeats=3)
        self.assertEqual(tuple(report["runtime"]), benchmark_hpy.OPERATIONS)
        for result in report["runtime"].values():
            self.assertEqual(3, len(result["samples"]))
            self.assertNotIn("ratio", result)

    def test_semantic_check_rejects_wrong_reference_behavior(self):
        module = self._module()
        module.add = lambda left, right: 0
        with self.assertRaisesRegex(AssertionError, "arithmetic semantic mismatch"):
            benchmark_hpy._verify_semantics(module)

    def test_trace_counts_report_api_totals_and_handle_churn(self):
        counts = {"ctx_Dup": 0, "ctx_Close": 0}

        def counted_module():
            module = self._module()
            for name in (
                    "identity", "add", "make_pair", "get_value",
                    "call_zero", "raise_value", "external_add"):
                function = getattr(module, name)

                def wrapper(*args, _function=function):
                    counts["ctx_Dup"] += 1
                    counts["ctx_Close"] += 1
                    return _function(*args)

                setattr(module, name, wrapper)
            original_box = module.BenchmarkBox

            class CountedBox(original_box):
                def __init__(self, *args):
                    counts["ctx_Dup"] += 1
                    counts["ctx_Close"] += 1
                    super().__init__(*args)

                def identity(self):
                    counts["ctx_Dup"] += 1
                    counts["ctx_Close"] += 1
                    return super().identity()

            module.BenchmarkBox = CountedBox
            return module

        modules = [counted_module(), counted_module()]
        with mock.patch.object(
                benchmark_hpy.importlib, "import_module", side_effect=modules):
            report = benchmark_hpy.trace_loaded_modules(
                Path("unused"), iterations=5,
                get_counts=lambda: dict(counts),
            )
        self.assertEqual(5, report["iterations"])
        self.assertEqual(tuple(report["operations"]), benchmark_hpy.OPERATIONS)
        for operation in benchmark_hpy.OPERATIONS:
            for implementation in ("generated", "reference"):
                result = report["operations"][operation][implementation]
                expected_calls = 12 if operation == "type_method" else 10
                expected_churn = 6 if operation == "type_method" else 5
                self.assertEqual(expected_calls, result["total_api_calls"])
                self.assertEqual(expected_calls / 5,
                                 result["api_calls_per_iteration"])
                self.assertEqual(
                    {"dup": expected_churn, "close": expected_churn},
                    result["handle_churn"])

    def test_trace_delta_and_iteration_validation(self):
        self.assertEqual(
            {"ctx_Dup": 2},
            benchmark_hpy._trace_count_delta(
                {"ctx_Dup": 1, "ctx_Close": 3},
                {"ctx_Dup": 3, "ctx_Close": 2},
            ),
        )
        with self.assertRaisesRegex(ValueError, "must be positive"):
            benchmark_hpy.trace_loaded_modules(Path("unused"), 0, lambda: {})

    def test_peak_memory_runs_each_operation_for_one_implementation(self):
        module = self._module()
        with (
            mock.patch.object(
                benchmark_hpy.importlib, "import_module", return_value=module),
            mock.patch.object(benchmark_hpy, "_time_operation") as time_operation,
            mock.patch.object(benchmark_hpy, "_peak_rss_bytes",
                              return_value=123456),
        ):
            report = benchmark_hpy.peak_memory_loaded_module(
                Path("unused"), "generated", 7)
        self.assertEqual(123456, report["peak_rss_bytes"])
        self.assertEqual(7, report["iterations_per_operation"])
        self.assertEqual(
            [(module, operation, 7) for operation in benchmark_hpy.OPERATIONS],
            [call.args for call in time_operation.call_args_list],
        )

    def test_peak_memory_rejects_unknown_implementation_and_zero_iterations(self):
        with self.assertRaisesRegex(ValueError, "unknown benchmark"):
            benchmark_hpy.peak_memory_loaded_module(
                Path("unused"), "unknown", 1)
        with self.assertRaisesRegex(ValueError, "must be positive"):
            benchmark_hpy.peak_memory_loaded_module(
                Path("unused"), "generated", 0)


if __name__ == "__main__":
    unittest.main()
