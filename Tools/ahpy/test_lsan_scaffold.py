from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from run_lsan_hpy import VALGRIND_ERROR_EXIT, _valgrind_command


ROOT = Path(__file__).resolve().parents[2]
POSITIVE_CONTROL = ROOT / "tests" / "ahpy" / "lsan_positive_control.c"
RUN_LSAN = Path(__file__).resolve().parent / "run_lsan_hpy.py"
SUPPRESSION_TEMPLATE = Path(__file__).resolve().parent / "lsan.supp"


class LSanScaffoldTest(unittest.TestCase):
    def test_scaffold_files_exist(self):
        for path in (POSITIVE_CONTROL, RUN_LSAN, SUPPRESSION_TEMPLATE):
            self.assertTrue(path.is_file(), path)

    def test_suppression_template_is_versioned_and_empty(self):
        text = SUPPRESSION_TEMPLATE.read_text(encoding="utf8")
        self.assertIn("suppression template", text)
        self.assertNotRegex(text, r"(?m)^\s*leak:")

    def test_valgrind_command_fails_only_on_definite_leaks(self):
        command = _valgrind_command(
            "/usr/bin/valgrind",
            Path("/tmp/reviewed.supp"),
            log_pattern=Path("/tmp/ahpy-%p.log"),
        )
        self.assertIn(
            "--error-exitcode=%d" % VALGRIND_ERROR_EXIT, command)
        self.assertIn("--show-leak-kinds=definite", command)
        self.assertIn("--errors-for-leak-kinds=definite", command)
        self.assertIn("--suppressions=/tmp/reviewed.supp", command)
        self.assertIn("--log-file=/tmp/ahpy-%p.log", command)

    def test_positive_control_binary_leaks_under_valgrind_when_available(self):
        valgrind = shutil.which("valgrind")
        if valgrind is None or sys.platform == "darwin":
            self.skipTest("valgrind scaffold requires Linux valgrind")
        cc = os.environ.get("CC", "gcc")
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-positive-") as temp:
            binary = Path(temp) / "lsan_positive_control"
            subprocess.run(
                [cc, "-O0", "-g", str(POSITIVE_CONTROL), "-o", str(binary)],
                check=True,
            )
            result = subprocess.run(
                [
                    valgrind,
                    "--error-exitcode=%d" % VALGRIND_ERROR_EXIT,
                    "--leak-check=full",
                    "--show-leak-kinds=definite",
                    "--errors-for-leak-kinds=definite",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, VALGRIND_ERROR_EXIT, combined)
            self.assertIn("definitely lost", combined)

    def test_run_lsan_script_enforces_generated_corpus(self):
        text = RUN_LSAN.read_text(encoding="utf8")
        self.assertIn("build_and_run(args.python", text)
        self.assertNotIn("check=False", text)
        self.assertIn("expected five Valgrind runtime logs", text)


if __name__ == "__main__":
    unittest.main()
