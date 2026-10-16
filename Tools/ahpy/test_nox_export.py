import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import nox_export


VALID_SOURCE = """\
def identity(value, /):
    return value

cdef class Box:
    def __cinit__(self, value, /):
        pass

    def identity(self, value, /):
        return value
"""


class NoxExportCommandTest(unittest.TestCase):
    def test_repository_fixture_is_reproduced_byte_for_byte(self):
        source = nox_export.ROOT / "tests" / "ahpy" / "nox_export_source.pyx"
        fixture = (
            nox_export.ROOT / "tests" / "ahpy" /
            "nox-export-analysis-v1.json"
        )
        analysis = nox_export.analyze_source(
            source, module_name="example.exports")
        self.assertEqual(
            nox_export.canonical_analysis_bytes(analysis),
            fixture.read_bytes(),
        )
        workflow = (
            nox_export.ROOT / ".github" / "workflows" /
            "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Validate compiler-owned NOX export analysis", workflow)
        self.assertIn("nox-export-analysis-v1.json", workflow)

    def setUp(self):
        self.temp_dir = TemporaryDirectory(prefix="ahpy-nox-export-test-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "sample.pyx"
        self.source.write_text(VALID_SOURCE, encoding="utf8")

    def test_analysis_is_compiler_owned_and_canonical(self):
        analysis = nox_export.analyze_source(
            self.source, module_name="example.sample")
        self.assertEqual(analysis["module"], {
            "name": "example.sample", "init_symbol": "HPyInit_sample"})
        self.assertEqual(
            [(item["kind"], item["name"]) for item in analysis["exports"]],
            [
                ("constructor", "Box"),
                ("method", "Box.identity"),
                ("module-function", "identity"),
            ],
        )
        rendered = nox_export.canonical_analysis_bytes(analysis)
        self.assertEqual(json.loads(rendered), analysis)
        self.assertTrue(rendered.endswith(b"\n"))

        implicit = nox_export.analyze_source(self.source)
        self.assertEqual(implicit["module"]["name"], "sample")

    def test_write_and_check_are_byte_exact(self):
        analysis = nox_export.analyze_source(self.source)
        output = self.root / "nested" / "exports.json"
        rendered = nox_export.write_analysis(analysis, output)
        self.assertEqual(output.read_bytes(), rendered)
        self.assertEqual(
            nox_export.write_analysis(analysis, output, check=True), rendered)

        output.write_text("{}\n", encoding="utf8")
        with self.assertRaisesRegex(
                nox_export.NoxExportCommandError, "stale or non-canonical"):
            nox_export.write_analysis(analysis, output, check=True)
        with self.assertRaisesRegex(
                nox_export.NoxExportCommandError, "cannot read"):
            nox_export.write_analysis(
                analysis, self.root / "missing.json", check=True)

    def test_missing_and_rejected_sources_leave_no_analysis(self):
        with self.assertRaisesRegex(
                nox_export.NoxExportCommandError, "source does not exist"):
            nox_export.analyze_source(self.root / "missing.pyx")

        rejected = self.root / "rejected.pyx"
        rejected.write_text(
            "def value(argument=1):\n    return argument\n",
            encoding="utf8",
        )
        with mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaisesRegex(
                nox_export.NoxExportCommandError, "compiler rejected"):
            nox_export.analyze_source(rejected)

        with mock.patch.object(
                nox_export.Main, "compile",
                return_value=mock.Mock(num_errors=0, nox_export_analysis=None)):
            with self.assertRaisesRegex(
                    nox_export.NoxExportCommandError, "returned no"):
                nox_export.analyze_source(self.source)

    def test_cli_stdout_output_check_and_errors(self):
        stdout = mock.Mock()
        stdout.buffer = io.BytesIO()
        with mock.patch.object(sys, "stdout", stdout):
            self.assertEqual(nox_export.main([str(self.source)]), 0)
        self.assertEqual(
            json.loads(stdout.buffer.getvalue())["module"]["name"], "sample")

        output = self.root / "exports.json"
        self.assertEqual(nox_export.main([
            str(self.source), "--module-name", "pkg.sample",
            "--output", str(output),
        ]), 0)
        self.assertEqual(nox_export.main([
            str(self.source), "--module-name", "pkg.sample",
            "--output", str(output), "--check",
        ]), 0)

        with self.assertRaises(SystemExit), mock.patch.object(
                sys, "stderr", io.StringIO()):
            nox_export.main([str(self.source), "--check"])
        with self.assertRaises(SystemExit), mock.patch.object(
                sys, "stderr", io.StringIO()):
            nox_export.main([str(self.root / "missing.pyx")])


if __name__ == "__main__":
    unittest.main()
