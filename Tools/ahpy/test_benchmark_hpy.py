from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

import benchmark_hpy


class BenchmarkHPyTest(unittest.TestCase):
    @staticmethod
    def _regression_budget_text():
        release = benchmark_hpy.DEFAULT_BUDGETS.read_text(encoding="utf8")
        regression = release.split("\n[release_absolute]\n", 1)[0] + "\n"
        return regression.replace(
            'classification = "release"', 'classification = "regression"', 1
        ).replace(
            "release_enforced = true", "release_enforced = false", 1
        ).replace(
            'calibration_status = "approved"',
            'calibration_status = "hosted-history-pending"',
            1,
        ).replace(
            'candidate_binding = "hosted-checkout"',
            'candidate_binding = "unbound"',
            1,
        ).replace(
            'calibration_source_commit = '
            '"22d8cbe1b50506f65e01be7ff05081616c656f2d"',
            'calibration_source_commit = ""',
            1,
        )

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
            sequence_last=lambda values, /: values[-1] if values else None,
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
            "policy": {
                "classification": "regression",
                "release_enforced": False,
                "calibration_status": "hosted-history-pending",
                "minimum_hosted_reports": 5,
                "candidate_binding": "unbound",
                "calibration_source_commit": "",
            },
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
        report["footprint"]["binary_to_reference_ratio"] = float("inf")
        violations = benchmark_hpy.check_thresholds(report, self._budgets())
        self.assertEqual(len(violations), 3)
        self.assertIn("runtime.call", violations[0])
        self.assertIn("generated_c_bytes", violations[1])
        self.assertIn("binary_to_reference_ratio", violations[2])

    def test_release_absolute_thresholds_require_complete_evidence(self):
        budgets = self._budgets()
        budgets["policy"].update({
            "classification": "release",
            "release_enforced": True,
            "calibration_status": "approved",
            "candidate_binding": "hosted-checkout",
            "calibration_source_commit": "a" * 40,
        })
        budgets["release_absolute"] = {
            "cython_seconds": 1.0,
            "native_build_seconds": 2.0,
            "generated_peak_rss_bytes": 1000,
            "generated_to_reference_peak_rss_ratio": 1.5,
            "large_type_frontend_seconds": 3.0,
            "large_type_o0_seconds": 4.0,
        }
        incomplete = self._report()
        violations = benchmark_hpy.check_thresholds(incomplete, budgets)
        self.assertEqual(len(violations), 6)
        self.assertTrue(all("evidence is missing" in item for item in violations))

        report = self._report()
        report.update({
            "build": {
                "cython_seconds": 1.0,
                "native_build_seconds": 2.0,
            },
            "peak_memory": {
                "generated": {"peak_rss_bytes": 1000},
                "generated_to_reference_ratio": 1.5,
            },
        })
        report["large_type_compile"].update({
            "frontend_seconds": 3.0,
            "o0": {"timed_out": False, "seconds": 4.0},
        })
        self.assertEqual(
            benchmark_hpy.check_thresholds(report, budgets), [])

        report["build"].update(
            cython_seconds=1.1, native_build_seconds=float("inf"))
        report["peak_memory"]["generated"]["peak_rss_bytes"] = 1001
        report["peak_memory"]["generated_to_reference_ratio"] = 1.6
        report["large_type_compile"]["frontend_seconds"] = 3.1
        report["large_type_compile"]["o0"]["seconds"] = 4.1
        violations = benchmark_hpy.check_thresholds(report, budgets)
        self.assertEqual(len(violations), 6)
        self.assertIn("cython_seconds", violations[0])
        self.assertIn("missing or invalid", violations[1])
        self.assertIn("generated_peak_rss_bytes", violations[2])
        self.assertIn("large_type_o0_seconds", violations[-1])

    def test_regression_policy_allows_local_history(self):
        report = {
            "provenance": {
                "execution": "local",
                "source_commit": "a" * 40,
                "github": None,
            },
        }
        self.assertEqual(
            benchmark_hpy.check_budget_policy(report, self._budgets()), [])

    def test_release_policy_requires_hosted_exact_commit(self):
        commit = "a" * 40
        budgets = self._budgets()
        budgets["policy"] = {
            "classification": "release",
            "release_enforced": True,
            "calibration_status": "approved",
            "minimum_hosted_reports": 5,
            "candidate_binding": "hosted-checkout",
            "calibration_source_commit": "b" * 40,
        }
        report = {
            "provenance": {
                "execution": "github-actions",
                "source_commit": commit,
                "github": {"sha": commit},
            },
        }
        self.assertEqual(
            benchmark_hpy.check_budget_policy(report, budgets), [])

        local = json.loads(json.dumps(report))
        local["provenance"].update(execution="local", github=None)
        self.assertEqual(
            benchmark_hpy.check_budget_policy(local, budgets),
            [
                "release budget requires hosted GitHub Actions execution",
                "release budget requires hosted GitHub SHA matching the "
                "benchmark source commit",
            ],
        )

        wrong = json.loads(json.dumps(report))
        wrong["provenance"]["source_commit"] = "b" * 40
        wrong["provenance"]["github"]["sha"] = "c" * 40
        violations = benchmark_hpy.check_budget_policy(wrong, budgets)
        self.assertEqual(len(violations), 1)
        self.assertIn("hosted GitHub SHA", violations[0])

        invalid_source = json.loads(json.dumps(report))
        invalid_source["provenance"]["source_commit"] = "short"
        violations = benchmark_hpy.check_budget_policy(invalid_source, budgets)
        self.assertEqual(len(violations), 2)
        self.assertIn("full benchmark source commit", violations[0])

    def test_release_policy_rejects_missing_or_unknown_provenance(self):
        budgets = self._budgets()
        budgets["policy"]["classification"] = "unknown"
        self.assertIn(
            "not recognized",
            benchmark_hpy.check_budget_policy({}, budgets)[0],
        )
        budgets["policy"]["classification"] = "release"
        self.assertEqual(
            benchmark_hpy.check_budget_policy({}, budgets),
            ["release budget requires complete benchmark provenance"],
        )

    def test_budget_schema_requires_exact_operation_set(self):
        with self.assertRaisesRegex(ValueError, "document must be a table"):
            benchmark_hpy.validate_budgets(None)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "budgets.toml"
            path.write_text(
                self._regression_budget_text().replace(
                    "identity = 1.26\n", "", 1),
                encoding="utf8")
            with self.assertRaisesRegex(ValueError, "runtime ratio keys differ"):
                benchmark_hpy.load_budgets(path)

    def test_budget_schema_rejects_invalid_types_and_measurements(self):
        original = self._regression_budget_text()
        cases = (
            (
                original.replace(
                    "schema_version = 1", "schema_version = 2", 1),
                "schema_version must be 1",
            ),
            (
                original.replace("identity = 1.26", "identity = 0", 1),
                "budget identity must be positive",
            ),
            (
                original.replace("timeout_seconds = 60", "timeout_seconds = 0"),
                "timeout_seconds must be positive",
            ),
            (
                original.replace("enforce_o3 = false", 'enforce_o3 = "no"'),
                "enforce_o3 must be boolean",
            ),
            (
                original.replace("warmups = 2", "warmups = -1"),
                "warmups must be a non-negative integer",
            ),
            (
                original.replace("iterations = 100000", "iterations = 0"),
                "iterations > 0",
            ),
            (
                original.replace("repeats = 7", "repeats = 2"),
                "repeats >= 3",
            ),
            (
                original.replace(
                    'classification = "regression"',
                    'classification = "candidate"',
                ),
                "classification must be regression or release",
            ),
            (
                original.replace("minimum_hosted_reports = 5",
                                 "minimum_hosted_reports = 4"),
                "minimum_hosted_reports must be at least 5",
            ),
            (
                original.replace("release_enforced = false",
                                 "release_enforced = true"),
                "regression budgets must remain non-release",
            ),
            (
                original.replace('calibration_source_commit = ""\n', "", 1),
                "policy must contain exactly",
            ),
            (
                original.replace("release_enforced = false",
                                 'release_enforced = "no"'),
                "release_enforced must be boolean",
            ),
            (
                original.replace('candidate_binding = "unbound"',
                                 "candidate_binding = 123"),
                "candidate_binding must be a string",
            ),
            (
                original.replace('calibration_source_commit = ""',
                                 "calibration_source_commit = 123"),
                "calibration_source_commit must be a string",
            ),
            (
                original + "\n[release_absolute]\ncython_seconds = 1\n",
                "regression budgets must not declare release_absolute",
            ),
            (
                original + "\nunknown = 1\n",
                "footprint must contain exactly",
            ),
            (
                original.replace('abi = "universal"', 'abi = "cpython"'),
                "environment.abi must be universal",
            ),
            (
                original.replace('hpy = "0.9.0"', 'hpy = ""'),
                "environment.hpy must be a non-empty string",
            ),
            (
                original.replace(
                    'python_implementation = "CPython"',
                    'python_implementation = 3',
                ),
                "python_implementation must be a non-empty string",
            ),
            (
                original.replace("iterations = 100000\n", "", 1),
                "measurement must contain exactly",
            ),
            (
                original.replace("enforce_o3 = false\n", "", 1),
                "large_type_compile must contain exactly",
            ),
            (
                original.replace("generated_c_bytes = 36420\n", "", 1),
                "footprint must contain exactly",
            ),
            (
                original.replace("identity = 1.26", 'identity = "slow"', 1),
                "positive and finite",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "budgets.toml"
            for content, message in cases:
                with self.subTest(message=message):
                    path.write_text(content, encoding="utf8")
                    with self.assertRaisesRegex(ValueError, message):
                        benchmark_hpy.load_budgets(path)

    def test_budget_schema_requires_exact_tables_and_top_level_keys(self):
        base = benchmark_hpy.load_budgets(benchmark_hpy.DEFAULT_BUDGETS)
        cases = (
            ("environment", [], "environment must contain exactly"),
            ("runtime_ratio", [], "runtime_ratio must be a table"),
            ("footprint", [], "footprint must contain exactly"),
            ("large_type_compile", [], "large_type_compile must contain"),
            ("measurement", [], "measurement must contain exactly"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                budget = json.loads(json.dumps(base))
                budget[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    benchmark_hpy.validate_budgets(budget)
        budget = json.loads(json.dumps(base))
        budget["unknown"] = True
        with self.assertRaisesRegex(ValueError, "top-level keys differ"):
            benchmark_hpy.validate_budgets(budget)

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

    def test_environment_gate_rejects_nonuniversal_and_interpreter_drift(self):
        report = {
            "environment": {
                "hpy_version": "0.9.0",
                "python_implementation": "PyPy",
            },
        }
        budgets = {
            "environment": {
                "abi": "cpython",
                "hpy": "0.9.0",
                "python_implementation": "CPython",
            },
        }
        self.assertEqual(
            benchmark_hpy.check_environment(report, budgets),
            [
                "budget ABI must be universal",
                "environment.python_implementation 'PyPy' does not match "
                "budget 'CPython'",
            ],
        )

    def test_default_budget_file_is_valid_and_json_serializable(self):
        budgets = benchmark_hpy.load_budgets(benchmark_hpy.DEFAULT_BUDGETS)
        self.assertEqual(budgets["schema_version"], 1)
        self.assertEqual(budgets["policy"], {
            "classification": "release",
            "release_enforced": True,
            "calibration_status": "approved",
            "minimum_hosted_reports": 5,
            "candidate_binding": "hosted-checkout",
            "calibration_source_commit":
                "22d8cbe1b50506f65e01be7ff05081616c656f2d",
        })
        self.assertEqual(
            budgets["large_type_compile"]["timeout_seconds"], 60)
        self.assertFalse(budgets["large_type_compile"]["enforce_o3"])
        self.assertEqual(tuple(budgets["runtime_ratio"]),
                         benchmark_hpy.OPERATIONS)
        json.dumps(budgets, sort_keys=True)

    def test_approved_release_budget_requires_exact_commit(self):
        release = benchmark_hpy.DEFAULT_BUDGETS.read_text(encoding="utf8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "release-budgets.toml"
            without_absolute = release.split("\n[release_absolute]\n", 1)[0]
            path.write_text(without_absolute + "\n", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "release_absolute"):
                benchmark_hpy.load_budgets(path)
            path.write_text(release, encoding="utf8")
            self.assertTrue(
                benchmark_hpy.load_budgets(path)["policy"]["release_enforced"])
            path.write_text(
                release.replace(
                    "22d8cbe1b50506f65e01be7ff05081616c656f2d",
                    "short", 1),
                encoding="utf8")
            with self.assertRaisesRegex(ValueError, "full calibration"):
                benchmark_hpy.load_budgets(path)
            path.write_text(
                release.replace("cython_seconds = 1.77",
                                "cython_seconds = 0", 1),
                encoding="utf8",
            )
            with self.assertRaisesRegex(ValueError, "positive finite"):
                benchmark_hpy.load_budgets(path)

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
            "AHPY_BENCHMARK_SAMPLE_ID": "4",
        }
        with mock.patch.object(
                benchmark_hpy, "source_commit", return_value="a" * 40):
            result = benchmark_hpy.benchmark_provenance(environment)
        self.assertEqual(result["execution"], "github-actions")
        self.assertEqual(result["github"]["run_id"], 123)
        self.assertEqual(result["github"]["run_attempt"], 2)
        self.assertEqual(result["github"]["sha"], "a" * 40)
        self.assertEqual(result["github"]["sample_id"], "4")

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
        completed = SimpleNamespace(
            stdout="wrapped clang 21\nmore detail\n",
            stderr="",
        )
        with (
            mock.patch.object(
                benchmark_hpy.shutil, "which",
                return_value="/usr/bin/ccache"),
            mock.patch.object(
                benchmark_hpy.subprocess, "run",
                return_value=completed) as run,
        ):
            identity = benchmark_hpy._compiler_identity(
                {"CC": "ccache clang"})
        self.assertEqual(identity, "wrapped clang 21")
        run.assert_called_once_with(
            ["/usr/bin/ccache", "clang", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        with self.assertRaisesRegex(ValueError, "compiler command"):
            benchmark_hpy._compiler_identity({"CC": "   "})

    def test_thresholds_reject_large_type_compile_timeout(self):
        report = self._report()
        report["large_type_compile"] = {
            "o0": {"timed_out": False}, "o3": {"timed_out": True}}
        violations = benchmark_hpy.check_thresholds(report, self._budgets())
        self.assertIn(
            "large_type_compile.o3 exceeded timeout budget", violations)
        report["large_type_compile"]["o0"]["timed_out"] = True
        self.assertIn(
            "large_type_compile.o0 exceeded timeout budget",
            benchmark_hpy.check_thresholds(report, self._budgets()),
        )

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

    def test_semantic_check_rejects_every_oracle_drift(self):
        class WrongBox:
            def __init__(self, value, /):
                self.value = value

            def identity(self):
                return object()

        cases = (
            ("identity", lambda module: setattr(
                module, "identity", lambda value, /: object())),
            ("container", lambda module: setattr(
                module, "make_pair", lambda left, right, /: [])),
            ("attribute", lambda module: setattr(
                module, "get_value", lambda value, /: object())),
            ("call", lambda module: setattr(
                module, "call_zero", lambda callable_object, /: object())),
            ("extension type", lambda module: setattr(
                module, "BenchmarkBox", WrongBox)),
            ("empty iteration", lambda module: setattr(
                module, "sequence_last",
                lambda values, /: object() if not values else values[-1])),
            ("iteration semantic", lambda module: setattr(
                module, "sequence_last",
                lambda values, /: None)),
            ("iteration error", lambda module: setattr(
                module, "sequence_last",
                lambda values, /: values[-1] if isinstance(values, list)
                and values else None)),
            ("external C", lambda module: setattr(
                module, "external_add", lambda: 0)),
            ("positional-only", lambda module: setattr(
                module, "identity", lambda value: value)),
            ("exception message", lambda module: setattr(
                module, "raise_value",
                lambda: (_ for _ in ()).throw(ValueError("wrong")))),
            ("did not raise", lambda module: setattr(
                module, "raise_value", lambda: None)),
        )
        for message, mutate in cases:
            with self.subTest(message=message):
                module = self._module()
                mutate(module)
                with self.assertRaisesRegex(AssertionError, message):
                    benchmark_hpy._verify_semantics(module)

    def test_debug_check_balances_leak_detector_and_source_path(self):
        events = []

        class LeakDetector:
            def start(self):
                events.append("start")

            def stop(self):
                events.append("stop")

        hpy = ModuleType("hpy")
        debug = ModuleType("hpy.debug")
        debug.LeakDetector = LeakDetector
        modules = [self._module(), self._module()]
        initial_path = list(sys.path)
        with (
            mock.patch.dict(
                sys.modules, {"hpy": hpy, "hpy.debug": debug}),
            mock.patch.object(
                benchmark_hpy.importlib, "import_module",
                side_effect=modules),
        ):
            benchmark_hpy.debug_check_loaded_modules(Path("/build/lib"))
        self.assertEqual(events, ["start", "stop"])
        self.assertEqual(sys.path, initial_path)

    def test_peak_rss_reports_positive_native_process_usage(self):
        self.assertGreater(benchmark_hpy._peak_rss_bytes(), 0)

    def test_peak_rss_uses_windows_process_memory_counters(self):
        fake_ctypes = SimpleNamespace()
        fake_ctypes.Structure = object
        fake_ctypes.c_size_t = int
        fake_ctypes.wintypes = SimpleNamespace(DWORD=int)
        fake_ctypes.sizeof = lambda counters: 64
        fake_ctypes.byref = lambda counters: counters
        fake_ctypes.windll = SimpleNamespace(
            kernel32=SimpleNamespace(GetCurrentProcess=lambda: 17),
            psapi=SimpleNamespace(),
        )

        def memory_info(process, counters, size):
            self.assertEqual(process, 17)
            self.assertEqual(size, 64)
            counters.PeakWorkingSetSize = 123456
            return True

        fake_ctypes.windll.psapi.GetProcessMemoryInfo = memory_info
        with (
            mock.patch.object(benchmark_hpy.os, "name", "nt"),
            mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}),
        ):
            self.assertEqual(benchmark_hpy._peak_rss_bytes(), 123456)

        fake_ctypes.windll.psapi.GetProcessMemoryInfo = (
            lambda process, counters, size: False
        )
        with (
            mock.patch.object(benchmark_hpy.os, "name", "nt"),
            mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}),
            self.assertRaisesRegex(OSError, "GetProcessMemoryInfo failed"),
        ):
            benchmark_hpy._peak_rss_bytes()

    def test_trace_counts_report_api_totals_and_handle_churn(self):
        counts = {"ctx_Dup": 0, "ctx_Close": 0}

        def counted_module():
            module = self._module()
            for name in (
                    "identity", "add", "make_pair", "get_value",
                    "call_zero", "raise_value", "sequence_last",
                    "external_add"):
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

    def test_trace_counts_load_default_public_hpy_trace_provider(self):
        hpy = ModuleType("hpy")
        hpy_trace = ModuleType("hpy.trace")
        hpy_trace.get_call_counts = lambda: {}
        hpy.trace = hpy_trace
        with (
            mock.patch.dict(
                sys.modules, {"hpy": hpy, "hpy.trace": hpy_trace}
            ),
            mock.patch.object(
                benchmark_hpy.importlib, "import_module",
                side_effect=(self._module(), self._module()),
            ),
        ):
            report = benchmark_hpy.trace_loaded_modules(Path("unused"), 1)
        self.assertEqual(report["iterations"], 1)

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

    def test_checked_runner_and_extension_discovery_fail_closed(self):
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(
                benchmark_hpy.subprocess, "run",
                return_value=completed) as run:
            self.assertIs(
                benchmark_hpy._run(["python", "-V"], cwd=Path("/tmp")),
                completed,
            )
        run.assert_called_once_with(
            ["python", "-V"], check=True, cwd=Path("/tmp"))

        error = subprocess.CalledProcessError(
            7, ["python", "-m", "cython"], stderr="compiler failed")
        with (
            mock.patch.object(
                benchmark_hpy.subprocess, "run", side_effect=error),
            self.assertRaisesRegex(
                RuntimeError, "(?s)command failed.*compiler failed"),
        ):
            benchmark_hpy._run(["python", "-m", "cython"])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            universal = root / "demo.hpy0.so"
            cpython = root / "demo.cpython.so"
            universal.touch()
            cpython.touch()
            self.assertEqual(
                benchmark_hpy._find_extension(root, "demo", True),
                universal,
            )
            self.assertEqual(
                benchmark_hpy._find_extension(root, "demo", False),
                cpython,
            )
            with self.assertRaisesRegex(
                    AssertionError, "expected one demo extension"):
                benchmark_hpy._find_extension(root, "demo")

    def test_benchmark_modules_must_share_one_build_root(self):
        generated = Path("build/lib/generated.hpy0.so")
        reference = Path("build/lib/reference.hpy0.so")
        self.assertEqual(
            benchmark_hpy._require_shared_build_root(
                generated, reference, "split roots"
            ),
            generated.parent,
        )
        with self.assertRaisesRegex(AssertionError, "split roots"):
            benchmark_hpy._require_shared_build_root(
                generated, Path("other/reference.hpy0.so"), "split roots"
            )

    def test_native_compile_command_supports_msvc(self):
        fake_os = SimpleNamespace(name="nt")
        with mock.patch.object(benchmark_hpy, "os", fake_os):
            command = benchmark_hpy._native_compile_command(
                "cl.exe", 0, Path("include"), Path("input.c"),
                Path("output.obj"))
        self.assertIn("/Od", command)
        self.assertIn("/DHPY_ABI_UNIVERSAL", command)
        self.assertIn("/Iinclude", command)
        self.assertIn("/Fooutput.obj", command)

    def test_large_type_compile_records_profiles_timeouts_and_failures(self):
        def run_frontend(command, **options):
            if "-m" in command and "cython" in command:
                output = Path(command[command.index("-o") + 1])
                output.write_text("line one\nline two\n", encoding="utf8")
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(
                stdout="/reviewed/include\n", stderr="", returncode=0)

        successful = SimpleNamespace(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                mock.patch.object(
                    benchmark_hpy, "_run", side_effect=run_frontend),
                mock.patch.object(
                    benchmark_hpy.subprocess, "run",
                    side_effect=[successful, successful]),
                mock.patch.object(
                    benchmark_hpy, "_compiler_identity",
                    return_value="reviewed cc"),
            ):
                result = benchmark_hpy.measure_large_type_compile(
                    "/tool/python", root, {"CC": "cc"}, 5)
            self.assertFalse(result["o0"]["timed_out"])
            self.assertFalse(result["o3"]["timed_out"])
            self.assertEqual(result["generated_c_lines"], 2)
            self.assertEqual(result["generated_c_bytes"], 18)
            self.assertEqual(result["compiler"], "reviewed cc")
            self.assertIn("o3_to_o0_ratio", result)

            timeout = subprocess.TimeoutExpired(["cc"], 5)
            with (
                mock.patch.object(
                    benchmark_hpy, "_run", side_effect=run_frontend),
                mock.patch.object(
                    benchmark_hpy.subprocess, "run",
                    side_effect=[timeout, successful]),
                mock.patch.object(
                    benchmark_hpy, "_compiler_identity",
                    return_value="reviewed cc"),
            ):
                result = benchmark_hpy.measure_large_type_compile(
                    "/tool/python", root, {"CC": "cc"}, 5)
            self.assertTrue(result["o0"]["timed_out"])
            self.assertNotIn("o3_to_o0_ratio", result)

            failed = SimpleNamespace(
                returncode=9, stdout="", stderr="native failure\n")
            with (
                mock.patch.object(
                    benchmark_hpy, "_run", side_effect=run_frontend),
                mock.patch.object(
                    benchmark_hpy.subprocess, "run",
                    return_value=failed),
                self.assertRaisesRegex(
                    RuntimeError, "large type compile failed.*native failure"),
            ):
                benchmark_hpy.measure_large_type_compile(
                    "/tool/python", root, {"CC": "cc"}, 5)

    def test_build_and_measure_assembles_all_abi_evidence(self):
        budgets = self._budgets()
        budgets.update({
            "environment": {
                "abi": "universal",
                "hpy": "0.9.0",
                "python_implementation": "CPython",
            },
            "measurement": {
                "iterations": 20,
                "warmups": 1,
                "repeats": 3,
            },
        })
        budgets["large_type_compile"]["timeout_seconds"] = 5
        runtime = {
            operation: {
                "generated_ns_per_call": 1.0,
                "reference_ns_per_call": 1.0,
                "ratio": 1.0,
                "generated_samples": [1.0, 1.0, 1.0],
                "reference_samples": [1.0, 1.0, 1.0],
            }
            for operation in benchmark_hpy.OPERATIONS
        }
        universal_report = {
            "runtime": runtime,
            "environment": {
                "hpy_version": "0.9.0",
                "python_implementation": "CPython",
            },
        }
        single_runtime = {
            operation: {
                "ns_per_call": 1.0,
                "samples": [1.0, 1.0, 1.0],
            }
            for operation in benchmark_hpy.OPERATIONS
        }
        calls = []

        def run(command, **options):
            calls.append((command, options))
            if "-m" in command and "cython" in command:
                generated = Path(command[command.index("-o") + 1])
                generated.write_bytes(b"generated C\n")
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            if "--run-built" in command:
                return SimpleNamespace(
                    stdout=json.dumps(universal_report),
                    stderr="",
                    returncode=0,
                )
            if "--run-single" in command:
                return SimpleNamespace(
                    stdout=json.dumps({"runtime": single_runtime}),
                    stderr="",
                    returncode=0,
                )
            if "--peak-memory" in command:
                implementation = command[
                    command.index("--implementation") + 1]
                peak = {
                    "generated": 200,
                    "reference": 100,
                    "classic": 150,
                }[implementation]
                return SimpleNamespace(
                    stdout=json.dumps({
                        "implementation": implementation,
                        "iterations_per_operation": 20,
                        "peak_rss_bytes": peak,
                    }),
                    stderr="",
                    returncode=0,
                )
            if "--trace-counts" in command:
                return SimpleNamespace(
                    stdout=json.dumps({
                        "iterations": 20,
                        "operations": {},
                    }),
                    stderr="",
                    returncode=0,
                )
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        def find_extension(build_root, module_name, universal=None):
            parent = Path(build_root) / "lib"
            parent.mkdir(parents=True, exist_ok=True)
            suffix = ".hpy0.so" if universal is True else ".cpython.so"
            binary = parent / (module_name + suffix)
            sizes = {
                benchmark_hpy.GENERATED_NAME: 200,
                benchmark_hpy.REFERENCE_NAME: 100,
                benchmark_hpy.CLASSIC_NAME: 150,
            }
            binary.write_bytes(b"x" * sizes[module_name])
            return binary

        large_type = {
            "o0": {"seconds": 1.0, "timed_out": False},
            "o3": {"seconds": 2.0, "timed_out": False},
            "timeout_seconds": 5,
        }
        provenance = {
            "source_commit": "a" * 40,
            "execution": "local",
            "github": None,
        }
        first_budget_contract = json.loads(json.dumps(budgets))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "evidence" / "benchmark.json"
            budget_path = root / "budgets.toml"
            budget_path.touch()
            with (
                mock.patch.object(
                    benchmark_hpy, "benchmark_provenance",
                    return_value=provenance),
                mock.patch.object(
                    benchmark_hpy, "_run", side_effect=run),
                mock.patch.object(
                    benchmark_hpy, "_find_extension",
                    side_effect=find_extension),
                mock.patch.object(
                    benchmark_hpy, "verify_source_boundary") as source_audit,
                mock.patch.object(
                    benchmark_hpy, "verify_binary_boundary") as binary_audit,
                mock.patch.object(
                    benchmark_hpy, "measure_large_type_compile",
                    side_effect=lambda *args: json.loads(json.dumps(large_type))),
                mock.patch.object(
                    benchmark_hpy, "_compiler_identity",
                    return_value="reviewed cc"),
                mock.patch.dict(
                    benchmark_hpy.os.environ,
                    {
                        "CC": "cc",
                        "CFLAGS": "-O2",
                        "CPPFLAGS": "-DREVIEWED",
                        "LDFLAGS": "-Wl,reviewed",
                        "ARCHFLAGS": "-arch reviewed",
                    },
                    clear=True,
                ),
            ):
                report = benchmark_hpy.build_and_measure(
                    "/tool/python", budgets, budget_path, output)
                budgets["large_type_compile"]["enforce_o3"] = False
                o0_report = benchmark_hpy.build_and_measure(
                    "/tool/python", budgets, budget_path,
                    root / "evidence" / "benchmark-o0.json",
                )
            self.assertEqual(json.loads(output.read_text()), report)

        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["budget_policy"]["classification"],
                         "regression")
        self.assertEqual(report["budget_contract"], first_budget_contract)
        self.assertEqual(report["provenance"], provenance)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["debug_leak_check"], "passed")
        self.assertEqual(
            report["large_type_compile"]["enforced_profiles"],
            ["o0", "o3"],
        )
        self.assertEqual(
            o0_report["large_type_compile"]["enforced_profiles"], ["o0"]
        )
        self.assertEqual(
            set(report["abi_matrix"]),
            {"hpy_universal", "hpy_cpython", "classic_cython"},
        )
        self.assertEqual(
            report["peak_memory"]["generated_to_reference_ratio"], 2.0)
        self.assertEqual(
            report["abi_matrix"]["hpy_cpython"]["abi"], "cpython")
        self.assertEqual(
            report["abi_matrix"]["classic_cython"]["abi"],
            "classic-cython-cpython",
        )
        self.assertEqual(report["trace"]["iterations"], 20)
        self.assertEqual(report["build"]["compiler"], "reviewed cc")
        self.assertEqual(
            report["build"]["configuration"]["cflags"], "-O2")
        self.assertGreaterEqual(len(calls), 14)
        self.assertEqual(source_audit.call_count, 2)
        self.assertEqual(binary_audit.call_count, 4)

    def test_main_dispatches_internal_measurement_modes(self):
        modes = (
            (
                ["benchmark_hpy.py", "--debug-check", "/build"],
                "debug_check_loaded_modules",
                (Path("/build"),),
            ),
            (
                [
                    "benchmark_hpy.py", "--trace-counts", "/build",
                    "--iterations", "3",
                ],
                "trace_loaded_modules",
                (Path("/build"), 3),
            ),
            (
                [
                    "benchmark_hpy.py", "--peak-memory", "/build",
                    "--implementation", "generated", "--iterations", "3",
                ],
                "peak_memory_loaded_module",
                (Path("/build"), "generated", 3),
            ),
            (
                [
                    "benchmark_hpy.py", "--run-built", "/build",
                    "--iterations", "3", "--warmups", "1", "--repeats", "3",
                ],
                "measure_loaded_modules",
                (Path("/build"), 3, 1, 3),
            ),
            (
                [
                    "benchmark_hpy.py", "--run-single", "/build",
                    "--module-name", "classic", "--iterations", "3",
                    "--warmups", "1", "--repeats", "3",
                ],
                "measure_single_loaded_module",
                (Path("/build"), "classic", 3, 1, 3),
            ),
        )
        for argv, function_name, expected_args in modes:
            with (
                self.subTest(function=function_name),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    benchmark_hpy, function_name,
                    return_value={"mode": function_name}) as function,
                mock.patch("builtins.print"),
            ):
                benchmark_hpy.main()
            function.assert_called_once_with(*expected_args)

    def test_main_rejects_incomplete_internal_modes(self):
        argv_cases = (
            ["benchmark_hpy.py", "--trace-counts", "/build"],
            [
                "benchmark_hpy.py", "--peak-memory", "/build",
                "--iterations", "3",
            ],
            [
                "benchmark_hpy.py", "--run-built", "/build",
                "--iterations", "3",
            ],
            [
                "benchmark_hpy.py", "--run-single", "/build",
                "--iterations", "3", "--warmups", "1", "--repeats", "3",
            ],
        )
        for argv in argv_cases:
            with (
                self.subTest(argv=argv),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                benchmark_hpy.main()
            self.assertEqual(raised.exception.code, 2)

    def test_main_reports_success_regression_and_missing_interpreter(self):
        budgets = self._budgets()
        report = self._report()
        report["violations"] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            python = root / "python"
            python.touch()
            output = root / "benchmark.json"
            budgets_path = root / "budgets.toml"
            budgets_path.touch()
            argv = [
                "benchmark_hpy.py",
                "--python", str(python),
                "--budgets", str(budgets_path),
                "--output", str(output),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    benchmark_hpy, "load_budgets",
                    return_value=budgets),
                mock.patch.object(
                    benchmark_hpy, "build_and_measure",
                    return_value=report) as build,
                mock.patch("builtins.print") as printed,
            ):
                benchmark_hpy.main()
            build.assert_called_once_with(
                os.path.abspath(python), budgets, budgets_path, output)
            self.assertEqual(printed.call_count, 2)

            budgets["policy"].update({
                "classification": "release",
                "release_enforced": True,
                "calibration_status": "approved",
                "candidate_binding": "hosted-checkout",
                "calibration_source_commit": "a" * 40,
            })
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    benchmark_hpy, "load_budgets", return_value=budgets),
                mock.patch.object(
                    benchmark_hpy, "build_and_measure", return_value=report),
                mock.patch("builtins.print") as release_printed,
            ):
                benchmark_hpy.main()
            self.assertIn(
                "release performance budgets",
                release_printed.call_args_list[0].args[0],
            )

            report["violations"] = ["runtime.call exceeded"]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    benchmark_hpy, "load_budgets",
                    return_value=budgets),
                mock.patch.object(
                    benchmark_hpy, "build_and_measure",
                    return_value=report),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                benchmark_hpy.main()
            self.assertEqual(raised.exception.code, 1)

        with (
            mock.patch.object(sys, "argv", [
                "benchmark_hpy.py", "--python", "missing-python"]),
            mock.patch.object(
                benchmark_hpy.shutil, "which", return_value=None),
            mock.patch.object(sys, "stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            benchmark_hpy.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
