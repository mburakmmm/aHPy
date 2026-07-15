from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import report_coverage


class CoverageReportTest(unittest.TestCase):
    def test_executable_lines_include_nested_code(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(
                "value = 1\n"
                "def function():\n"
                "    return value\n",
                encoding="utf8",
            )
            lines = report_coverage.executable_lines(path)
        self.assertTrue({1, 2, 3}.issubset(lines))

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
        self.assertEqual(areas["quality_tools"]["executable_lines"], 1)

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
            }],
            "feature_families": [{
                "name": "emitter", "tests": 2, "failures": 0,
                "errors": 0, "skipped": 0, "passed": True,
            }],
        }
        markdown = report_coverage.render_markdown(report)
        self.assertIn("| backend | 3 | 4 | 75.00% |", markdown)
        self.assertIn("| emitter | 2 | 0 | 0 | 0 | yes |", markdown)


if __name__ == "__main__":
    unittest.main()
