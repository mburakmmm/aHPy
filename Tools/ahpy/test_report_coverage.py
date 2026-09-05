from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import threading
import trace
import unittest
from unittest import mock

import report_coverage


class CoverageReportTest(unittest.TestCase):
    def test_executable_lines_include_nested_code(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(
                "value = 1\n"
                "def function():\n"
                "    return value\n"
                "def interface_stub(\n"
                "    argument,\n"
                "):\n"
                '    """Interface documentation."""\n'
                "    ...\n"
                "if str(ROOT) not in sys.path:\n"
                "    sys.path.insert(0, str(ROOT))\n"
                "if __name__ == '__main__':\n"
                "    main()\n",
                encoding="utf8",
            )
            lines = report_coverage.executable_lines(path)
        self.assertTrue({1, 2, 3}.issubset(lines))
        self.assertIn(4, lines)
        self.assertNotIn(5, lines)
        self.assertNotIn(6, lines)
        self.assertNotIn(7, lines)
        self.assertNotIn(8, lines)
        self.assertNotIn(10, lines)
        self.assertNotIn(12, lines)

    def test_bootstrap_exclusion_is_narrow_and_keeps_real_conditionals(self):
        source = (
            "if str(ROOT) not in sys.path:\n"
            "    sys.path.insert(0, str(ROOT))\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
            "if enabled:\n"
            "    run_feature()\n"
            "if __name__ == '__main__':\n"
            "    marker = 'not dispatch'\n"
        )
        self.assertEqual(
            report_coverage.excluded_bootstrap_lines(source), {2, 4}
        )

    def test_line_ranges_are_sorted_deduplicated_and_collapsed(self):
        self.assertEqual(
            report_coverage.collapse_line_ranges([8, 3, 4, 4, 6, 9, 12]),
            ["3-4", "6", "8-9", "12"],
        )
        self.assertEqual(report_coverage.collapse_line_ranges([]), [])

    def test_suite_discovery_runs_under_trace(self):
        class TraceAwareLoader:
            traced = False

            def loadTestsFromNames(self, names):
                self.traced = sys.gettrace() is not None
                return unittest.TestSuite()

        loader = TraceAwareLoader()
        suite = report_coverage._load_suite_under_trace(
            trace.Trace(count=True, trace=False),
            loader,
            ("example.tests",),
        )
        self.assertTrue(loader.traced)
        self.assertEqual(suite.countTestCases(), 0)

    def test_suite_discovery_restores_an_outer_trace_function(self):
        class EmptyLoader:
            def loadTestsFromNames(self, names):
                return unittest.TestSuite()

        def outer_trace(frame, event, argument):
            return outer_trace

        original_trace = sys.gettrace()
        try:
            sys.settrace(outer_trace)
            report_coverage._load_suite_under_trace(
                trace.Trace(count=True, trace=False),
                EmptyLoader(),
                ("example.tests",),
            )
            self.assertIs(sys.gettrace(), outer_trace)
        finally:
            sys.settrace(original_trace)

    def test_suite_runner_traces_workers_and_restores_thread_trace(self):
        worker_traces = []

        class Runner:
            def run(self, suite):
                worker = threading.Thread(
                    target=lambda: worker_traces.append(sys.gettrace()))
                worker.start()
                worker.join()
                return "result"

        def outer_thread_trace(frame, event, argument):
            return outer_thread_trace

        original_trace = sys.gettrace()
        original_thread_trace = threading.gettrace()
        try:
            threading.settrace(outer_thread_trace)
            result = report_coverage._run_suite_under_trace(
                trace.Trace(count=True, trace=False), Runner(), object())
            self.assertEqual(result, "result")
            self.assertEqual(len(worker_traces), 1)
            self.assertIsNotNone(worker_traces[0])
            self.assertIs(sys.gettrace(), original_trace)
            self.assertIs(threading.gettrace(), outer_thread_trace)
        finally:
            sys.settrace(original_trace)
            threading.settrace(original_thread_trace)

    def test_measured_source_finder_prefers_the_reported_python_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compiler = root / "Cython" / "Compiler"
            tools = root / "Tools" / "ahpy"
            compiler.mkdir(parents=True)
            tools.mkdir(parents=True)
            for filename in report_coverage.BACKEND_FILES:
                path = root / filename
                path.write_text("value = 1\n", encoding="utf8")
            for filename in report_coverage.FRONTEND_FILES:
                path = root / filename
                path.write_text("value = 1\n", encoding="utf8")
            expected = root / report_coverage.BACKEND_FILES[0]
            finder = report_coverage._MeasuredSourceFinder(root)
            spec = finder.find_spec("Cython.Compiler.HPyModuleWriter")
        self.assertEqual(Path(spec.origin), expected)
        self.assertIsNone(finder.find_spec("unmeasured.module"))

    def test_coverage_area_and_module_discovery_include_packaging_tools(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tools = root / "Tools" / "ahpy"
            compiler = root / "Cython" / "Compiler"
            tools.mkdir(parents=True)
            compiler.mkdir(parents=True)
            (tools / "doctor.py").write_text("value = 1\n", encoding="utf8")
            (tools / "test_ignored.py").write_text(
                "value = 1\n", encoding="utf8")
            (root / "ahpy_version.py").write_text(
                "value = 1\n", encoding="utf8")
            files = report_coverage.utility_files(root)
            self.assertEqual(
                files, ("Tools/ahpy/doctor.py", "ahpy_version.py"))
            areas = report_coverage.coverage_areas(root)
            self.assertEqual(areas["quality_tools"], files)
            modules = report_coverage.measured_source_modules(root)
            self.assertEqual(modules["doctor"], tools / "doctor.py")
            self.assertEqual(
                modules["Tools.ahpy.doctor"], tools / "doctor.py")
            self.assertEqual(
                modules["ahpy_version"], root / "ahpy_version.py")

    def test_report_groups_files_and_counts_hits(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = root / "Cython" / "Compiler"
            tools = root / "Tools" / "ahpy"
            backend.mkdir(parents=True)
            tools.mkdir(parents=True)
            for filename in report_coverage.BACKEND_FILES:
                path = root / filename
                path.write_text("value = 1\n", encoding="utf8")
            for filename in report_coverage.FRONTEND_FILES:
                path = root / filename
                path.write_text("value = 1\n", encoding="utf8")
            utility = tools / "doctor.py"
            utility.write_text("value = 1\n", encoding="utf8")
            counts = {(str((root / report_coverage.BACKEND_FILES[0]).resolve()), 1): 1}
            report = report_coverage.build_report(counts, [], root)
        areas = {area["name"]: area for area in report["areas"]}
        self.assertEqual(areas["backend"]["covered_lines"], 1)
        self.assertEqual(areas["backend"]["executable_lines"], 3)
        self.assertEqual(
            areas["backend"]["files"][0]["missing_lines"], [])
        self.assertEqual(
            areas["backend"]["files"][1]["missing_ranges"], ["1"])
        self.assertEqual(areas["quality_tools"]["executable_lines"], 1)
        self.assertEqual(report["schema_version"], 2)

    def test_excluded_stub_lines_handle_async_docstrings_and_real_bodies(self):
        source = (
            "async def interface(\n"
            "    value,\n"
            "):\n"
            "    \"\"\"documented\"\"\"\n"
            "    ...\n\n"
            "def implemented():\n"
            "    return 1\n"
        )
        excluded = report_coverage.excluded_stub_lines(source)
        self.assertEqual(excluded, {2, 3, 4, 5})
        self.assertNotIn(8, excluded)
        self.assertEqual(
            report_coverage.excluded_stub_lines(
                "def multi():\n    value = 1\n    return value\n"
            ),
            set(),
        )

    def test_family_and_quality_loaders_delegate_to_unittest_loader(self):
        loader = mock.Mock()
        family = object()
        quality = object()
        loader.loadTestsFromNames.return_value = family
        loader.discover.return_value = quality
        self.assertIs(
            report_coverage._load_family_suite(loader, ("tests.one",)),
            family,
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertIs(
                report_coverage._load_quality_suite(loader, root), quality)
        loader.loadTestsFromNames.assert_called_once_with(("tests.one",))
        loader.discover.assert_called_once_with(
            str(root / "Tools" / "ahpy"),
            pattern="test_*.py",
            top_level_dir=str(root / "Tools" / "ahpy"),
        )

    def test_quality_suite_selection_and_trace_cleanup_failure_paths(self):
        loader = mock.Mock()
        loader.discover.return_value = unittest.TestSuite()
        suite = report_coverage._load_suite_under_trace(
            trace.Trace(count=True, trace=False), loader, None
        )
        self.assertEqual(suite.countTestCases(), 0)
        loader.discover.assert_called_once()

        tracer = mock.Mock()
        tracer.runfunc.side_effect = RuntimeError("trace failed")
        with (
            mock.patch.object(report_coverage.sys, "settrace") as settrace,
            self.assertRaisesRegex(RuntimeError, "trace failed"),
        ):
            report_coverage._load_suite_under_trace(
                tracer, loader, ("tests.one",)
            )
        settrace.assert_called_once()

    def test_report_ignores_unresolvable_trace_filenames(self):
        unresolved = mock.Mock()
        unresolved.resolve.side_effect = OSError("unresolvable")
        with (
            mock.patch.object(report_coverage, "Path", return_value=unresolved),
            mock.patch.object(report_coverage, "coverage_areas", return_value={}),
        ):
            report = report_coverage.build_report(
                {("missing-source.py", 1): 1}, [], Path(".")
            )
        self.assertEqual(report["areas"], [])

    def test_traced_runner_reports_each_family_and_failure_state(self):
        class Suite:
            def countTestCases(self):
                return 2

        class Result:
            failures = [("test", "failure")]
            errors = []
            skipped = [("test", "skip")]

            def wasSuccessful(self):
                return False

        class Runner:
            def __init__(self, **options):
                self.options = options

            def run(self, suite):
                return Result()

        class TraceResult:
            counts = {("measured.py", 1): 1}

        class Tracer:
            def runfunc(self, function, *arguments):
                return function(*arguments)

            def results(self):
                return TraceResult()

        finder = object()
        with (
            mock.patch.object(
                report_coverage.trace, "Trace", return_value=Tracer()),
            mock.patch.object(
                report_coverage, "_load_suite_under_trace",
                return_value=Suite()) as load,
            mock.patch.object(
                report_coverage.unittest, "TextTestRunner", Runner),
            mock.patch.object(
                report_coverage, "_MeasuredSourceFinder",
                return_value=finder),
        ):
            success, families, counts = report_coverage.run_traced_tests(
                stream=mock.Mock())
        self.assertFalse(success)
        self.assertEqual(load.call_count, len(report_coverage.FAMILY_MODULES) + 1)
        self.assertEqual(len(families), len(report_coverage.FAMILY_MODULES) + 1)
        self.assertTrue(all(family["tests"] == 2 for family in families))
        self.assertTrue(all(family["failures"] == 1 for family in families))
        self.assertTrue(all(family["skipped"] == 1 for family in families))
        self.assertEqual(counts, {("measured.py", 1): 1})
        self.assertNotIn(finder, sys.meta_path)

    def test_thresholds_reject_regression_and_unknown_area(self):
        report = {"areas": [{"name": "backend", "percent": 75.0}]}
        self.assertEqual(
            report_coverage.check_thresholds(report, {"backend": 74.0}), [])
        self.assertIn(
            "below",
            report_coverage.check_thresholds(
                report, {"backend": 76.0})[0])
        self.assertIn(
            "unknown",
            report_coverage.check_thresholds(report, {"missing": 1.0})[0])

    def test_threshold_parser_accepts_values_and_rejects_invalid_contracts(self):
        self.assertEqual(
            report_coverage.parse_thresholds(
                ["backend=100", "quality_tools=90.5"]),
            {"backend": 100.0, "quality_tools": 90.5},
        )
        for value in ("backend", "backend=invalid", "=50", "backend=-1",
                      "backend=101"):
            with self.subTest(value=value):
                with self.assertRaises(Exception):
                    report_coverage.parse_thresholds([value])

    def test_markdown_is_stable(self):
        report = {
            "areas": [{
                "name": "backend", "covered_lines": 3,
                "executable_lines": 4, "percent": 75.0,
                "files": [{
                    "path": "backend.py", "covered_lines": 3,
                    "executable_lines": 4, "percent": 75.0,
                    "missing_ranges": ["8"],
                }],
            }],
            "feature_families": [{
                "name": "emitter", "tests": 2, "failures": 0,
                "errors": 0, "skipped": 0, "passed": True,
            }],
        }
        markdown = report_coverage.render_markdown(report)
        self.assertIn("| backend | 3 | 4 | 75.00% |", markdown)
        self.assertIn("| `backend.py` | 3 | 4 | 75.00% | 8 |", markdown)
        self.assertIn("| emitter | 2 | 0 | 0 | 0 | yes |", markdown)

    def test_main_writes_reports_prints_stdout_and_fails_closed(self):
        report = {
            "schema_version": 2,
            "areas": [{
                "name": "backend", "covered_lines": 1,
                "executable_lines": 1, "percent": 100.0, "files": [],
            }],
            "feature_families": [],
            "total_tests": 0,
        }
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_output = root / "coverage.json"
            markdown_output = root / "coverage.md"
            with (
                mock.patch.object(sys, "argv", [
                    "report_coverage.py",
                    "--json-output", str(json_output),
                    "--markdown-output", str(markdown_output),
                    "--fail-under", "backend=100",
                ]),
                mock.patch.object(
                    report_coverage, "run_traced_tests",
                    return_value=(True, [], {})),
                mock.patch.object(
                    report_coverage, "build_report", return_value=report),
            ):
                report_coverage.main()
            self.assertEqual(json.loads(json_output.read_text()), report)
            self.assertIn("aHPy focused coverage", markdown_output.read_text())

        with (
            mock.patch.object(sys, "argv", ["report_coverage.py"]),
            mock.patch.object(
                report_coverage, "run_traced_tests",
                return_value=(True, [], {})),
            mock.patch.object(
                report_coverage, "build_report", return_value=report),
            mock.patch.object(sys, "stdout") as stdout,
        ):
            report_coverage.main()
        self.assertIn("aHPy focused coverage", stdout.write.call_args.args[0])

        with (
            mock.patch.object(sys, "argv", [
                "report_coverage.py", "--fail-under", "backend=101"]),
            mock.patch.object(sys, "stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            report_coverage.main()
        self.assertEqual(raised.exception.code, 2)

        with (
            mock.patch.object(sys, "argv", [
                "report_coverage.py", "--fail-under", "backend=100"]),
            mock.patch.object(
                report_coverage, "run_traced_tests",
                return_value=(False, [], {})),
            mock.patch.object(
                report_coverage, "build_report", return_value=report),
            mock.patch.object(sys, "stderr"),
            mock.patch.object(sys, "stdout"),
            self.assertRaises(SystemExit) as raised,
        ):
            report_coverage.main()
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
