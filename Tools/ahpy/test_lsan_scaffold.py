from __future__ import annotations

import os
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import run_lsan_hpy
from run_lsan_hpy import (
    VALGRIND_ERROR_EXIT,
    _compile_positive_control,
    _run_valgrind_leak_check,
    _valgrind_command,
)


ROOT = Path(__file__).resolve().parents[2]
POSITIVE_CONTROL = ROOT / "tests" / "ahpy" / "lsan_positive_control.c"
RUN_LSAN = Path(__file__).resolve().parent / "run_lsan_hpy.py"
SUPPRESSION_TEMPLATE = Path(__file__).resolve().parent / "lsan.supp"


class LSanScaffoldTest(unittest.TestCase):
    def test_tool_lookup_delegates_to_path_resolution(self):
        with mock.patch.object(
            run_lsan_hpy.shutil, "which", return_value="/tools/valgrind"
        ) as which:
            self.assertEqual(
                run_lsan_hpy._tool_path("valgrind"), "/tools/valgrind"
            )
        which.assert_called_once_with("valgrind")

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

    @mock.patch("run_lsan_hpy.subprocess.run")
    def test_positive_control_compile_is_checked(self, run):
        output = Path("/tmp/ahpy-positive-control")
        _compile_positive_control("cc", output)
        run.assert_called_once_with(
            [
                "cc", "-O0", "-g", str(POSITIVE_CONTROL),
                "-o", str(output),
            ],
            check=True,
        )

    @mock.patch("run_lsan_hpy.subprocess.run")
    def test_valgrind_leak_check_captures_text_output(self, run):
        binary = Path("/tmp/ahpy-positive-control")
        suppression = Path("/tmp/reviewed.supp")
        expected = subprocess.CompletedProcess([], VALGRIND_ERROR_EXIT)
        run.return_value = expected
        result = _run_valgrind_leak_check(
            "valgrind", binary, suppression, Path("/tmp/ahpy-%p.log"))
        self.assertIs(result, expected)
        run.assert_called_once_with(
            _valgrind_command(
                "valgrind", suppression, Path("/tmp/ahpy-%p.log"))
            + [str(binary)],
            capture_output=True,
            text=True,
        )

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

    def test_main_rejects_macos(self):
        with (
            mock.patch.object(sys, "argv", ["run_lsan_hpy.py"]),
            mock.patch.object(run_lsan_hpy.sys, "platform", "darwin"),
            mock.patch.object(run_lsan_hpy, "_tool_path") as tool_path,
        ):
            self.assertEqual(run_lsan_hpy.main(), 2)
        tool_path.assert_not_called()

    def test_main_rejects_missing_valgrind(self):
        with (
            mock.patch.object(sys, "argv", ["run_lsan_hpy.py"]),
            mock.patch.object(run_lsan_hpy.sys, "platform", "linux"),
            mock.patch.object(
                run_lsan_hpy, "_tool_path", return_value=None),
        ):
            self.assertEqual(run_lsan_hpy.main(), 2)

    def test_main_rejects_missing_suppression_file(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-test-") as temp:
            root = Path(temp)
            with (
                mock.patch.object(sys, "argv", [
                    "run_lsan_hpy.py",
                    "--build-dir", str(root / "build"),
                    "--suppressions", str(root / "missing.supp"),
                ]),
                mock.patch.object(run_lsan_hpy.sys, "platform", "linux"),
                mock.patch.object(
                    run_lsan_hpy, "_tool_path",
                    return_value="/usr/bin/valgrind"),
            ):
                with self.assertRaisesRegex(
                        FileNotFoundError, "suppression file does not exist"):
                    run_lsan_hpy.main()

    def _run_mocked_main(
            self, root, leak_result, *, positive_control_only=True,
            generated_logs=0):
        suppression = root / "reviewed.supp"
        suppression.write_text("reviewed suppression set\n", encoding="utf8")
        build_dir = root / "build"
        build_dir.mkdir()
        for index in range(generated_logs):
            (build_dir / ("valgrind-generated-%d.log" % index)).write_text(
                "clean\n", encoding="utf8")
        argv = [
            "run_lsan_hpy.py",
            "--cc", "reviewed-cc",
            "--python", "reviewed-python",
            "--build-dir", str(build_dir),
            "--suppressions", str(suppression),
        ]
        if positive_control_only:
            argv.append("--positive-control-only")
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(run_lsan_hpy.sys, "platform", "linux"),
            mock.patch.object(
                run_lsan_hpy, "_tool_path",
                return_value="/usr/bin/valgrind"),
            mock.patch.object(
                run_lsan_hpy.subprocess,
                "check_output",
                side_effect=[
                    "Python 3.reviewed\n",
                    "reviewed-cc 1.0\nextra\n",
                    "valgrind-reviewed\n",
                ],
            ),
            mock.patch.object(
                run_lsan_hpy, "_compile_positive_control") as compile_control,
            mock.patch.object(
                run_lsan_hpy, "_run_valgrind_leak_check",
                return_value=leak_result),
            mock.patch.object(
                run_lsan_hpy, "build_and_run") as build_and_run,
            mock.patch.object(
                run_lsan_hpy.shutil, "which",
                side_effect=lambda executable: (
                    "/resolved/reviewed-python"
                    if executable == "reviewed-python"
                    else None
                )),
        ):
            result = run_lsan_hpy.main()
        return result, build_dir, compile_control, build_and_run

    def test_main_records_reviewed_positive_control_evidence(self):
        leak_result = subprocess.CompletedProcess(
            [], VALGRIND_ERROR_EXIT,
            stdout="definitely lost: 8 bytes\n", stderr="reviewed\n")
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-test-") as temp:
            root = Path(temp)
            result, build_dir, compile_control, build_and_run = (
                self._run_mocked_main(root, leak_result))
            self.assertEqual(result, 0)
            compile_control.assert_called_once_with(
                "reviewed-cc", build_dir / "lsan_positive_control")
            build_and_run.assert_not_called()
            environment = json.loads(
                (build_dir / "environment.json").read_text(encoding="utf8"))
            self.assertEqual(environment["python"], "Python 3.reviewed")
            self.assertEqual(
                environment["python_executable"],
                "/resolved/reviewed-python")
            self.assertEqual(environment["compiler"], "reviewed-cc 1.0")
            self.assertEqual(environment["valgrind"], "valgrind-reviewed")
            self.assertEqual(
                environment["expected_generated_runtime_logs"], 5)
            self.assertEqual(
                (build_dir / "valgrind-positive-control.log").read_text(
                    encoding="utf8"),
                "definitely lost: 8 bytes\nreviewed\n",
            )
            self.assertEqual(
                (build_dir / "lsan.supp").read_text(encoding="utf8"),
                "reviewed suppression set\n",
            )

    def test_main_requires_positive_control_exit_code(self):
        leak_result = subprocess.CompletedProcess(
            [], 0, stdout="definitely lost: 8 bytes\n", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-test-") as temp:
            with self.assertRaisesRegex(
                    RuntimeError, "positive-control leak was not detected"):
                self._run_mocked_main(Path(temp), leak_result)

    def test_main_requires_positive_control_marker(self):
        leak_result = subprocess.CompletedProcess(
            [], VALGRIND_ERROR_EXIT, stdout="no marker\n", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-test-") as temp:
            with self.assertRaisesRegex(
                    RuntimeError, "lacked a definite-leak marker"):
                self._run_mocked_main(Path(temp), leak_result)

    def test_main_runs_generated_corpus_with_reviewed_prefix(self):
        leak_result = subprocess.CompletedProcess(
            [], VALGRIND_ERROR_EXIT,
            stdout="definitely lost: 8 bytes\n", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-test-") as temp:
            result, build_dir, _, build_and_run = self._run_mocked_main(
                Path(temp), leak_result,
                positive_control_only=False,
                generated_logs=5,
            )
            self.assertEqual(result, 0)
            build_and_run.assert_called_once()
            python, = build_and_run.call_args.args
            self.assertEqual(python, "reviewed-python")
            runtime_prefix = build_and_run.call_args.kwargs["runtime_prefix"]
            self.assertIn("/usr/bin/valgrind", runtime_prefix)
            self.assertIn(
                "--suppressions=%s" % (build_dir / "lsan.supp").resolve(),
                runtime_prefix,
            )
            self.assertIn(
                "--log-file=%s" % (
                    build_dir / "valgrind-generated-%p.log").resolve(),
                runtime_prefix,
            )

    def test_main_rejects_incomplete_generated_log_set(self):
        leak_result = subprocess.CompletedProcess(
            [], VALGRIND_ERROR_EXIT,
            stdout="definitely lost: 8 bytes\n", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-lsan-test-") as temp:
            with self.assertRaisesRegex(
                    RuntimeError, "expected five.*found 4"):
                self._run_mocked_main(
                    Path(temp), leak_result,
                    positive_control_only=False,
                    generated_logs=4,
                )


if __name__ == "__main__":
    unittest.main()
