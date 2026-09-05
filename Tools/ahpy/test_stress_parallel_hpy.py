from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

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

        default = stress_parallel_hpy.child_environment(
            {}, "generated", 1, Path("/isolated"), "default")
        self.assertNotIn("CFLAGS", default)
        self.assertNotIn("CXXFLAGS", default)

    def test_windows_optimization_and_process_group_flags(self):
        fake_os = SimpleNamespace(name="nt")
        with (
            mock.patch.object(stress_parallel_hpy, "os", fake_os),
            mock.patch.object(
                stress_parallel_hpy.subprocess,
                "CREATE_NEW_PROCESS_GROUP", 512, create=True),
        ):
            environment = stress_parallel_hpy.child_environment(
                {}, "fault", 2, Path("C:/temp"), "2")
            kwargs = stress_parallel_hpy._popen_group_kwargs()
        self.assertEqual(environment["CFLAGS"], "/O2")
        self.assertEqual(environment["CXXFLAGS"], "/O2")
        self.assertEqual(kwargs, {"creationflags": 512})

    def test_process_group_termination_covers_platform_failure_paths(self):
        exited = mock.Mock()
        exited.poll.return_value = 0
        self.assertFalse(stress_parallel_hpy.terminate_process_group(exited))

        windows = mock.Mock(name="windows-process", pid=41)
        windows.poll.side_effect = (None, None)
        with (
            mock.patch.object(
                stress_parallel_hpy.os, "name", "nt"
            ),
            mock.patch.object(
                stress_parallel_hpy.subprocess, "run"
            ) as taskkill,
            mock.patch.object(
                stress_parallel_hpy, "_wait_until_exit", return_value=None
            ),
        ):
            self.assertTrue(
                stress_parallel_hpy.terminate_process_group(
                    windows, grace_seconds=0, poll_seconds=0
                )
            )
        self.assertEqual(taskkill.call_args.args[0][:2], ["taskkill", "/PID"])
        windows.kill.assert_called_once_with()

        wait_timeout = mock.Mock(name="wait-timeout", pid=42)
        wait_timeout.poll.side_effect = (None, 0)
        wait_timeout.wait.side_effect = (
            stress_parallel_hpy.subprocess.TimeoutExpired("wait", 0.1),
            0,
        )
        with (
            mock.patch.object(stress_parallel_hpy.os, "name", "nt"),
            mock.patch.object(stress_parallel_hpy.subprocess, "run"),
            mock.patch.object(
                stress_parallel_hpy, "_wait_until_exit", return_value=0
            ),
        ):
            self.assertTrue(
                stress_parallel_hpy.terminate_process_group(
                    wait_timeout, grace_seconds=0, poll_seconds=0
                )
            )
        wait_timeout.kill.assert_called_once_with()
        self.assertEqual(wait_timeout.wait.call_count, 2)

        missing_group = mock.Mock(name="missing-group", pid=43)
        missing_group.poll.return_value = None
        with mock.patch.object(
            stress_parallel_hpy.os, "getpgid", side_effect=ProcessLookupError
        ):
            self.assertFalse(
                stress_parallel_hpy.terminate_process_group(missing_group)
            )

        disappeared = mock.Mock(name="disappeared", pid=44)
        disappeared.poll.return_value = None
        with (
            mock.patch.object(stress_parallel_hpy.os, "getpgid", return_value=7),
            mock.patch.object(
                stress_parallel_hpy.os, "killpg", side_effect=ProcessLookupError
            ),
        ):
            self.assertFalse(
                stress_parallel_hpy.terminate_process_group(disappeared)
            )

        kill_race = mock.Mock(name="kill-race", pid=45)
        kill_race.poll.side_effect = (None, None)
        with (
            mock.patch.object(stress_parallel_hpy.os, "getpgid", return_value=8),
            mock.patch.object(
                stress_parallel_hpy.os, "killpg",
                side_effect=(None, ProcessLookupError()),
            ) as killpg,
            mock.patch.object(
                stress_parallel_hpy, "_wait_until_exit", return_value=None
            ),
        ):
            self.assertTrue(
                stress_parallel_hpy.terminate_process_group(
                    kill_race, grace_seconds=0, poll_seconds=0
                )
            )
        self.assertEqual(killpg.call_count, 2)

    def test_file_evidence_handles_missing_files_and_bounded_tail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "log"
            missing = stress_parallel_hpy._file_evidence(path)
            self.assertEqual(missing["bytes"], 0)
            self.assertEqual(missing["tail"], "")
            path.write_bytes(b"prefix-" + b"x" * 20)
            evidence = stress_parallel_hpy._file_evidence(path, tail_bytes=5)
        self.assertEqual(evidence["bytes"], 27)
        self.assertEqual(evidence["tail"], "xxxxx")
        self.assertEqual(len(evidence["sha256"]), 64)

    def test_round_validation_and_exception_cleanup_are_fail_closed(self):
        command = stress_parallel_hpy.StressCommand(
            "one", (sys.executable, "-c", "pass"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for timeout, grace, poll, message in (
                    (0, 1, 0.1, "timeout_seconds"),
                    (1, -1, 0.1, "grace_seconds"),
                    (1, 0, 0, "poll_seconds")):
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ValueError, message):
                        stress_parallel_hpy.run_round(
                            (command,), 1, root / (message + "-work"),
                            root / (message + "-logs"), timeout,
                            grace_seconds=grace, poll_seconds=poll)

            process = mock.Mock(pid=123, returncode=-15)
            process.poll.return_value = None
            with (
                mock.patch.object(
                    stress_parallel_hpy.subprocess, "Popen",
                    return_value=process),
                mock.patch.object(
                    stress_parallel_hpy.time, "monotonic",
                    side_effect=[1.0, KeyboardInterrupt()]),
                mock.patch.object(
                    stress_parallel_hpy,
                    "terminate_process_group") as terminate,
                self.assertRaises(KeyboardInterrupt),
            ):
                stress_parallel_hpy.run_round(
                    (command,), 1, root / "interrupt-work",
                    root / "interrupt-logs", 10,
                    grace_seconds=0, poll_seconds=0.1,
                    base_environment={})
            terminate.assert_called_once_with(
                process, grace_seconds=0, poll_seconds=0.1)

    def test_resolve_python_and_main_status_contract(self):
        parser = mock.Mock()
        command = stress_parallel_hpy.StressCommand(
            "one", (sys.executable, "-c", "pass"))
        with tempfile.TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            self.assertEqual(
                stress_parallel_hpy._resolve_python(parser, str(python)),
                os.path.abspath(python),
            )
        with mock.patch.object(
                stress_parallel_hpy.shutil, "which",
                return_value="/tool/python"):
            self.assertEqual(
                stress_parallel_hpy._resolve_python(
                    parser, "reviewed-python"),
                "/tool/python",
            )
        with mock.patch.object(
                stress_parallel_hpy.shutil, "which", return_value=None):
            stress_parallel_hpy._resolve_python(parser, "missing-python")
        parser.error.assert_called_once()

        reports = (
            ({
                "passed": True,
                "configuration": {"expected_fault_cases": 0},
                "round_results": [{
                    "round": 1,
                    "commands": [{
                        "name": "fault", "status": "passed",
                        "duration_seconds": 0.1,
                    }],
                }],
            }, False),
            ({
                "passed": False,
                "configuration": {"expected_fault_cases": 0},
                "round_results": [],
            }, True),
        )
        for report, fails in reports:
            argv = [
                "stress_parallel_hpy.py", "--python", "/tool/python",
                "--rounds", "1", "--fuzz-cases", "2",
                "--output", "stress.json",
            ]
            context = self.assertRaises(SystemExit) if fails else nullcontext()
            with (
                self.subTest(fails=fails),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    stress_parallel_hpy, "_resolve_python",
                    return_value="/tool/python"),
                mock.patch.object(
                    stress_parallel_hpy, "run_stress",
                    return_value=report) as run,
                mock.patch("builtins.print"),
                context,
            ):
                stress_parallel_hpy.main()
            run.assert_called_once()

        with (
            mock.patch.object(sys, "argv", [
                "stress_parallel_hpy.py", "--fuzz-cases", "0"]),
            mock.patch.object(sys, "stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            stress_parallel_hpy.main()
        self.assertEqual(raised.exception.code, 2)

        with self.assertRaisesRegex(ValueError, "rounds must be positive"):
            stress_parallel_hpy.run_stress(
                (command,), 0, 1, Path("unused.json"))

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
        self.assertEqual(stored["configuration"]["expected_fault_cases"], 0)

    def test_run_stress_derives_fault_count_and_rejects_stale_output(self):
        valid = stress_parallel_hpy.StressCommand(
            "fault", (sys.executable, "-c", "print(" + repr(
                "Generated Universal HPy module: 17 isolated "
                "API/allocation fault injection cases passed") + ")"))
        malformed = stress_parallel_hpy.StressCommand(
            "fault", (sys.executable, "-c", "print('stale count')"))
        failed = stress_parallel_hpy.StressCommand(
            "fault", (sys.executable, "-c", "raise SystemExit(3)"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = stress_parallel_hpy.run_stress(
                (valid,), 2, 2.0, root / "valid.json",
                grace_seconds=0.2, poll_seconds=0.01,
                native_optimization="0", base_environment={},
            )
            rejected = stress_parallel_hpy.run_stress(
                (malformed,), 1, 2.0, root / "malformed.json",
                grace_seconds=0.2, poll_seconds=0.01,
                native_optimization="0", base_environment={},
            )
            failed_report = stress_parallel_hpy.run_stress(
                (failed,), 1, 2.0, root / "failed.json",
                grace_seconds=0.2, poll_seconds=0.01,
                native_optimization="0", base_environment={},
            )
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["configuration"]["fault_case_counts"], [17, 17])
        self.assertEqual(
            report["configuration"]["expected_fault_cases"], 34)
        self.assertFalse(rejected["passed"])
        self.assertEqual(
            rejected["configuration"]["expected_fault_cases"], 0)
        self.assertFalse(failed_report["passed"])
        self.assertEqual(
            failed_report["configuration"]["fault_case_counts"], [])


if __name__ == "__main__":
    unittest.main()
