from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import time
import unittest

import stress_parallel_hpy


class ParallelHPyStressTest(unittest.TestCase):
    def _run(self, commands, timeout=2.0):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = stress_parallel_hpy.run_round(
                commands, 1, root / "work", root / "logs", timeout,
                grace_seconds=0.2, poll_seconds=0.01,
                native_optimization="0", base_environment={},
            )
            # Materialise log evidence before TemporaryDirectory cleanup.
            for command in result["commands"]:
                command["stdout_tail"] = command["stdout"]["tail"]
                command["stderr_tail"] = command["stderr"]["tail"]
            return result

    def test_command_construction_is_deterministic_and_uses_selected_python(self):
        first = stress_parallel_hpy.build_commands("/chosen/python", 17)
        second = stress_parallel_hpy.build_commands("/chosen/python", 17)
        self.assertEqual(first, second)
        self.assertEqual(
            [command.name for command in first],
            ["fault", "generated", "setuptools", "fuzz"],
        )
        self.assertTrue(all(command.argv[0] == "/chosen/python" for command in first))
        self.assertEqual(first[-1].argv[-1], "17")

    def test_success_retains_separate_stdout_stderr_and_temp_root(self):
        command = stress_parallel_hpy.StressCommand("success", (
            sys.executable, "-c",
            "import os,sys; print(os.environ['TMPDIR']); print('kept-error', file=sys.stderr)",
        ))
        result = self._run((command,))
        child = result["commands"][0]
        self.assertTrue(result["passed"])
        self.assertEqual(child["status"], "passed")
        self.assertIn("success", child["stdout_tail"])
        self.assertIn("kept-error", child["stderr_tail"])
        self.assertEqual(len(child["stdout"]["sha256"]), 64)

    def test_nonzero_exit_is_reported_with_output(self):
        command = stress_parallel_hpy.StressCommand("failure", (
            sys.executable, "-c",
            "import sys; print('failure-evidence', file=sys.stderr); raise SystemExit(7)",
        ))
        result = self._run((command,))
        child = result["commands"][0]
        self.assertFalse(result["passed"])
        self.assertEqual(child["status"], "failed")
        self.assertEqual(child["returncode"], 7)
        self.assertIn("failure-evidence", child["stderr_tail"])

    def test_start_error_is_structured_and_retains_diagnostic(self):
        command = stress_parallel_hpy.StressCommand(
            "missing", ("/definitely/missing/ahpy-command",))
        result = self._run((command,))
        child = result["commands"][0]
        self.assertFalse(result["passed"])
        self.assertEqual(child["status"], "start-error")
        self.assertIsNone(child["returncode"])
        self.assertGreater(child["stderr"]["bytes"], 0)

    def test_timeout_terminates_process_group_and_retains_early_output(self):
        command = stress_parallel_hpy.StressCommand("timeout", (
            sys.executable, "-c",
            "import time; print('started', flush=True); time.sleep(60)",
        ))
        result = self._run((command,), timeout=0.1)
        child = result["commands"][0]
        self.assertFalse(result["passed"])
        self.assertEqual(child["status"], "timed-out")
        self.assertTrue(child["timed_out"])
        self.assertIn("started", child["stdout_tail"])

    def test_timeout_terminates_descendant_before_it_can_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "orphan-survived"
            descendant = (
                "import pathlib,time; time.sleep(0.5); "
                "pathlib.Path(%r).write_text('survived')" % str(marker)
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', %r]); "
                "print('descendant-started', flush=True); time.sleep(60)" %
                descendant
            )
            command = stress_parallel_hpy.StressCommand(
                "tree-timeout", (sys.executable, "-c", parent))
            result = self._run((command,), timeout=0.1)
            self.assertEqual(result["commands"][0]["status"], "timed-out")
            time.sleep(0.7)
            self.assertFalse(marker.exists(), "descendant escaped process-group cleanup")

    def test_duplicate_names_are_rejected_before_launch(self):
        command = stress_parallel_hpy.StressCommand(
            "same", (sys.executable, "-c", "pass"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "names must be unique"):
                stress_parallel_hpy.run_round(
                    (command, command), 1, root / "work", root / "logs", 1.0)

    def test_optimization_flags_preserve_existing_environment(self):
        environment = stress_parallel_hpy.child_environment(
            {"CFLAGS": "-Wall"}, "fault", 3, Path("/isolated"), "0")
        self.assertEqual(environment["AHPY_STRESS_ROUND"], "3")
        self.assertEqual(environment["TMPDIR"], "/isolated")
        self.assertTrue(environment["CFLAGS"].startswith("-Wall "))
        self.assertIn("-O0", environment["CFLAGS"])

    def test_run_stress_writes_versioned_multi_round_report(self):
        command = stress_parallel_hpy.StressCommand(
            "success", (sys.executable, "-c", "print('ok')"))
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.json"
            report = stress_parallel_hpy.run_stress(
                (command,), 2, 2.0, output,
                grace_seconds=0.2, poll_seconds=0.01,
                native_optimization="0", base_environment={},
            )
            stored = json.loads(output.read_text(encoding="utf8"))
        self.assertTrue(report["passed"])
        self.assertEqual(stored["schema_version"], 1)
        self.assertEqual(len(stored["round_results"]), 2)
        self.assertEqual(stored["configuration"]["expected_fault_cases"], 256)


if __name__ == "__main__":
    unittest.main()
