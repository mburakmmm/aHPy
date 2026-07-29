from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import trace
import unittest

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
                "    ...\n",
                encoding="utf8",
            )
            lines = report_coverage.executable_lines(path)
        self.assertTrue({1, 2, 3}.issubset(lines))
        self.assertIn(4, lines)
        self.assertNotIn(5, lines)
        self.assertNotIn(6, lines)
        self.assertNotIn(7, lines)
        self.assertNotIn(8, lines)

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


if __name__ == "__main__":
    unittest.main()
