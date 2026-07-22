from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from appverifier_runtime_wrapper import (
    _child_command,
    _export_command,
    _timeout_text,
)
from run_appverifier_hpy import (
    EXPECTED_RUNTIME_PROCESSES,
    POSITIVE_CONTROL,
    RUNTIME_WRAPPER,
    _appverif_export_command,
    _candidate_paths,
    _copy_raw_logs,
    _xml_errors,
    _xml_severities,
)


ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve().parent / "run_appverifier_hpy.py"


class AppVerifierScaffoldTest(unittest.TestCase):
    def test_scaffold_files_and_positive_control_exist(self):
        for path in (POSITIVE_CONTROL, RUNTIME_WRAPPER, RUNNER):
            self.assertTrue(path.is_file(), path)
        source = POSITIVE_CONTROL.read_text(encoding="utf8")
        self.assertIn("HeapAlloc", source)
        self.assertIn("buffer[16]", source)
        self.assertIn("HeapFree", source)

    def test_known_windows_sdk_tool_locations_are_searched(self):
        environment = {
            "PATH": "",
            "WINDIR": r"C:\Windows",
            "ProgramFiles(x86)": r"C:\Program Files (x86)",
        }
        appverif = [str(path).lower() for path in
                    _candidate_paths("appverif.exe", environment)]
        gflags = [str(path).lower() for path in
                  _candidate_paths("gflags.exe", environment)]
        self.assertTrue(any("system32" in path for path in appverif))
        self.assertTrue(any("app certification kit" in path
                            for path in appverif))
        self.assertTrue(any("debuggers" in path for path in gflags))

    def test_runtime_wrapper_replaces_original_python_only(self):
        command = _child_command(
            Path("verified.exe"),
            ["--", "python.exe", "check.py", "--mode", "debug"],
        )
        self.assertEqual(
            command,
            ["verified.exe", "check.py", "--mode", "debug"],
        )
        with self.assertRaises(ValueError):
            _child_command(Path("verified.exe"), ["python.exe"])
        self.assertEqual(_timeout_text(b"timeout\xff"), "timeout\ufffd")
        self.assertEqual(_timeout_text(None), "")

    def test_export_commands_use_target_name_and_xml_path(self):
        expected = [
            "appverif.exe", "-export", "log", "-for", "target.exe",
            "-with", "To=evidence.xml",
        ]
        self.assertEqual(
            _export_command(
                Path("appverif.exe"), "target.exe", Path("evidence.xml")),
            expected,
        )
        self.assertEqual(
            _appverif_export_command(
                Path("appverif.exe"), "target.exe", Path("evidence.xml")),
            expected,
        )

    def test_xml_parser_distinguishes_errors_from_warnings(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-xml-") as temp:
            xml = Path(temp) / "log.xml"
            xml.write_text(
                "<log><logEntry Severity='Warning'/>"
                "<logEntry Severity='Error'/></log>",
                encoding="utf8",
            )
            self.assertEqual(_xml_severities(xml), ["warning", "error"])
            self.assertEqual(_xml_errors(xml), ["error"])

    def test_raw_log_copy_is_limited_to_configured_targets(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-raw-") as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            wanted = source / "ahpy_target.exe.123.dat"
            unrelated = source / "unrelated.exe.456.dat"
            wanted.write_bytes(b"wanted")
            unrelated.write_bytes(b"unrelated")
            copied = _copy_raw_logs(
                destination, ["ahpy_target.exe"], source=source)
            self.assertEqual(copied, [destination / wanted.name])
            self.assertEqual(copied[0].read_bytes(), b"wanted")
            self.assertFalse((destination / unrelated.name).exists())

    def test_runner_enforces_injection_five_processes_and_cleanup(self):
        source = RUNNER.read_text(encoding="utf8")
        self.assertEqual(EXPECTED_RUNTIME_PROCESSES, 5)
        self.assertIn("build_and_run(str(python)", source)
        self.assertIn('"verifier.dll" not in loaded', source)
        self.assertIn('"/p", "/enable", target_name, "/full"', source)
        self.assertIn('"/p", "/disable", target_name', source)
        self.assertIn('"-delete", "settings"', source)
        self.assertIn("positive control produced no AppVerifier error", source)
        self.assertIn("preflight.json", source)
        self.assertIn(
            "Application Verifier produced no target-specific raw logs",
            source,
        )
        self.assertNotIn("check=False)\n        build_and_run", source)

    @unittest.skipUnless(os.name == "nt", "AppVerifier requires Windows")
    def test_selected_environment_is_windows(self):
        self.assertEqual(os.name, "nt")


if __name__ == "__main__":
    unittest.main()
