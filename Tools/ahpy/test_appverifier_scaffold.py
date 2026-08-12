from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import appverifier_runtime_wrapper
import run_appverifier_hpy
from appverifier_runtime_wrapper import (
    EXPORT_FAILURE,
    RUNTIME_TIMEOUT,
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
    _validate_settings,
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
        with mock.patch.object(
            run_appverifier_hpy.shutil,
            "which",
            return_value=r"C:\tools\appverif.exe",
        ):
            candidates = _candidate_paths("appverif.exe", {"PATH": "tools"})
        self.assertEqual(candidates, [Path(r"C:\tools\appverif.exe").resolve()])

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

    def _run_runtime_wrapper(
            self, root, child_result, export_result, *,
            create_xml=True, pythonpath=None):
        target = root / "verified-python.exe"
        appverif = root / "appverif.exe"
        probe = root / "probe"
        evidence = root / "evidence"
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            if len(calls) == 1:
                if isinstance(child_result, BaseException):
                    raise child_result
                return child_result
            if create_xml:
                xml_argument = next(
                    argument for argument in command
                    if str(argument).startswith("To="))
                Path(str(xml_argument).split("=", 1)[1]).write_text(
                    "<log/>", encoding="utf8")
            return export_result

        environment = {}
        if pythonpath is not None:
            environment["PYTHONPATH"] = pythonpath
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", [
                "appverifier_runtime_wrapper.py",
                "--target", str(target),
                "--appverif", str(appverif),
                "--probe-dir", str(probe),
                "--evidence-dir", str(evidence),
                "--",
                "original-python.exe",
                "runtime_check.py",
                "--mode", "debug",
            ]),
            mock.patch.dict(
                appverifier_runtime_wrapper.os.environ,
                environment,
                clear=True,
            ),
            mock.patch.object(
                appverifier_runtime_wrapper.os, "getpid",
                return_value=1234),
            mock.patch.object(
                appverifier_runtime_wrapper.uuid, "uuid4",
                return_value=SimpleNamespace(hex="reviewed")),
            mock.patch.object(
                appverifier_runtime_wrapper.subprocess, "run",
                side_effect=run),
            mock.patch.object(
                appverifier_runtime_wrapper.sys, "stdout", stdout),
            mock.patch.object(
                appverifier_runtime_wrapper.sys, "stderr", stderr),
        ):
            returncode = appverifier_runtime_wrapper.main()
        record = json.loads(
            (evidence / "runtime-1234-reviewed.json").read_text(
                encoding="utf8"))
        return returncode, evidence, record, calls, stdout.getvalue(), stderr.getvalue()

    def test_runtime_wrapper_records_successful_verified_process(self):
        child = subprocess.CompletedProcess(
            [], 0, stdout="runtime stdout\n", stderr="runtime stderr\n")
        export = subprocess.CompletedProcess(
            [], 0, stdout="exported\n", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-wrapper-") as temp:
            root = Path(temp)
            (
                returncode, evidence, record, calls, stdout, stderr,
            ) = self._run_runtime_wrapper(
                root, child, export, pythonpath="existing-path")
            self.assertEqual(returncode, 0)
            self.assertEqual(
                record["command"],
                [
                    str(root / "verified-python.exe"),
                    "runtime_check.py",
                    "--mode",
                    "debug",
                ],
            )
            self.assertEqual(record["returncode"], 0)
            self.assertEqual(record["export_returncode"], 0)
            self.assertEqual(record["export_stdout"], "exported\n")
            self.assertEqual(record["token"], "1234-reviewed")
            self.assertTrue(Path(record["xml"]).is_file())
            self.assertEqual(
                (evidence / "runtime-1234-reviewed.stdout").read_text(
                    encoding="utf8"),
                "runtime stdout\n",
            )
            self.assertEqual(
                (evidence / "runtime-1234-reviewed.stderr").read_text(
                    encoding="utf8"),
                "runtime stderr\n",
            )
            self.assertEqual(stdout, "runtime stdout\n")
            self.assertEqual(stderr, "runtime stderr\n")
            child_environment = calls[0][1]["env"]
            self.assertEqual(
                child_environment["AHPY_APPVERIFIER_TOKEN"],
                "1234-reviewed",
            )
            self.assertEqual(
                child_environment["AHPY_APPVERIFIER_MARKER_DIR"],
                str(evidence / "markers"),
            )
            self.assertEqual(
                child_environment["AHPY_APPVERIFIER_REQUIRE"], "1")
            self.assertEqual(
                child_environment["PYTHONPATH"],
                os.pathsep.join([str(root / "probe"), "existing-path"]),
            )
            self.assertEqual(calls[0][1]["timeout"], RUNTIME_TIMEOUT)
            self.assertEqual(calls[1][1]["timeout"], 120)

    def test_runtime_wrapper_preserves_child_failure(self):
        child = subprocess.CompletedProcess(
            [], 7, stdout="", stderr="child failed\n")
        export = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-wrapper-") as temp:
            returncode, _, record, calls, _, stderr = (
                self._run_runtime_wrapper(
                    Path(temp), child, export, pythonpath=None))
            self.assertEqual(returncode, 7)
            self.assertEqual(record["returncode"], 7)
            self.assertEqual(stderr, "child failed\n")
            self.assertEqual(
                calls[0][1]["env"]["PYTHONPATH"],
                str(Path(temp) / "probe"),
            )

    def test_runtime_wrapper_converts_timeout_to_evidence(self):
        timeout = subprocess.TimeoutExpired(
            ["verified-python.exe"], RUNTIME_TIMEOUT,
            output=b"partial\xff", stderr=b"stalled\xff")
        export = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-wrapper-") as temp:
            returncode, evidence, record, _, stdout, stderr = (
                self._run_runtime_wrapper(Path(temp), timeout, export))
            self.assertEqual(returncode, 124)
            self.assertEqual(record["returncode"], 124)
            self.assertEqual(stdout, "partial\ufffd")
            self.assertIn("stalled\ufffd", stderr)
            self.assertIn(
                "verified runtime exceeded %d seconds" % RUNTIME_TIMEOUT,
                stderr,
            )
            self.assertEqual(
                (evidence / "runtime-1234-reviewed.stderr").read_text(
                    encoding="utf8"),
                stderr,
            )

    def test_runtime_wrapper_requires_successful_xml_export(self):
        child = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        cases = (
            (
                subprocess.CompletedProcess(
                    [], 9, stdout="", stderr="export failed\n"),
                True,
            ),
            (subprocess.CompletedProcess([], 0, stdout="", stderr=""), False),
        )
        for export, create_xml in cases:
            with self.subTest(
                    export_returncode=export.returncode,
                    create_xml=create_xml):
                with tempfile.TemporaryDirectory(
                        prefix="ahpy-appverif-wrapper-") as temp:
                    returncode, _, record, _, _, stderr = (
                        self._run_runtime_wrapper(
                            Path(temp), child, export,
                            create_xml=create_xml))
                    self.assertEqual(returncode, EXPORT_FAILURE)
                    self.assertEqual(
                        record["export_returncode"], export.returncode)
                    self.assertIn(
                        "AppVerifier did not export", stderr)

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

    def test_hosted_settings_shape_proves_full_page_heap(self):
        target = "ahpy_target.exe"
        appverif = (
            "Settings for ahpy_target.exe:\n"
            "Test [Heaps] enabled.\n"
            "    Full = true\n"
        )
        gflags = (
            "path: SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
            "Image File Execution Options\n"
            "    ahpy_target.exe: page heap enabled with flags (full traces)\n"
        )
        _validate_settings(target, appverif, gflags)
        with self.assertRaisesRegex(RuntimeError, "AppVerifier query"):
            _validate_settings(target, appverif.replace("true", "false"), gflags)
        with self.assertRaisesRegex(RuntimeError, "GFlags enable output"):
            _validate_settings(target, appverif, "No application enabled")

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

    def test_tool_location_requires_an_existing_candidate(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-tools-") as temp:
            root = Path(temp)
            missing = root / "missing.exe"
            present = root / "present.exe"
            present.touch()
            with mock.patch.object(
                    run_appverifier_hpy, "_candidate_paths",
                    return_value=[missing, present]):
                self.assertEqual(
                    run_appverifier_hpy._locate_tool("appverif.exe"),
                    present,
                )
            with (
                mock.patch.object(
                    run_appverifier_hpy, "_candidate_paths",
                    return_value=[missing]),
                self.assertRaisesRegex(
                    FileNotFoundError, "requires appverif.exe"),
            ):
                run_appverifier_hpy._locate_tool("appverif.exe")
            with (
                mock.patch.object(
                    run_appverifier_hpy, "_candidate_paths", return_value=[]
                ),
                self.assertRaisesRegex(
                    FileNotFoundError, "no Windows SDK locations"
                ),
            ):
                run_appverifier_hpy._locate_tool("gflags.exe")

    def test_runner_delegates_to_captured_checked_subprocess(self):
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(
                run_appverifier_hpy.subprocess, "run",
                return_value=completed) as run:
            result = run_appverifier_hpy._run(
                [Path("/tool/appverif.exe"), "-query"],
                environment={"A": "1"},
                cwd=Path("/tmp"),
                check=False,
                timeout=9,
            )
        self.assertIs(result, completed)
        run.assert_called_once_with(
            ["/tool/appverif.exe", "-query"],
            env={"A": "1"},
            cwd=Path("/tmp"),
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=9,
        )

    def test_target_configuration_records_queries_and_cleanup(self):
        outputs = (
            SimpleNamespace(stdout="", stderr="", returncode=0),
            SimpleNamespace(stdout="", stderr="", returncode=0),
            SimpleNamespace(stdout="", stderr="", returncode=0),
            SimpleNamespace(stdout="", stderr="", returncode=0),
            SimpleNamespace(
                stdout="target.exe page heap enabled\n", stderr="",
                returncode=0),
            SimpleNamespace(
                stdout=(
                    "Settings for target.exe:\n"
                    "Test [Heaps] enabled.\nFull = true\n"),
                stderr="",
                returncode=0,
            ),
            SimpleNamespace(stdout="page heap query\n", stderr="", returncode=0),
        )
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-config-") as temp:
            evidence = Path(temp)
            with mock.patch.object(
                    run_appverifier_hpy, "_run",
                    side_effect=outputs) as run:
                run_appverifier_hpy._configure_target(
                    Path("appverif.exe"),
                    Path("gflags.exe"),
                    "target.exe",
                    evidence,
                )
            self.assertEqual(run.call_count, 7)
            self.assertIn(
                "page heap enabled",
                (evidence / "target.exe-gflags-enable.txt").read_text(),
            )
            self.assertIn(
                "Test [Heaps] enabled",
                (evidence / "target.exe-appverif-query.txt").read_text(),
            )
            self.assertEqual(
                (evidence / "target.exe-gflags-query.txt").read_text(),
                "page heap query\n",
            )

        cleanup_results = (
            SimpleNamespace(stdout="disabled", stderr="", returncode=0),
            SimpleNamespace(stdout="", stderr="deleted", returncode=3),
        )
        with mock.patch.object(
                run_appverifier_hpy, "_run",
                side_effect=cleanup_results):
            cleanup = run_appverifier_hpy._cleanup_target(
                Path("appverif.exe"), Path("gflags.exe"), "target.exe")
        self.assertEqual([record["returncode"] for record in cleanup], [0, 3])
        self.assertEqual(cleanup[0]["stdout"], "disabled")
        self.assertEqual(cleanup[1]["stderr"], "deleted")

    def test_positive_control_compile_requires_msvc(self):
        with (
            mock.patch.object(
                run_appverifier_hpy.shutil, "which",
                return_value=None),
            self.assertRaisesRegex(RuntimeError, "does not expose cl.exe"),
        ):
            run_appverifier_hpy._compile_positive_control(
                Path("control.c"), Path("/tmp/control.exe"), {"PATH": ""})

        with (
            mock.patch.object(
                run_appverifier_hpy.shutil, "which",
                return_value="/tool/cl.exe"),
            mock.patch.object(run_appverifier_hpy, "_run") as run,
        ):
            run_appverifier_hpy._compile_positive_control(
                Path("control.c"), Path("/tmp/control.exe"), {"PATH": "tool"})
        run.assert_called_once_with(
            [
                "/tool/cl.exe", "/nologo", "/Od", "/Zi", "control.c",
                "/Fe:/tmp/control.exe",
            ],
            environment={"PATH": "tool"},
            cwd=Path("/tmp"),
        )

    def test_sitecustomize_requires_active_verifier_injection(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-probe-") as temp:
            probe = Path(temp) / "probe"
            run_appverifier_hpy._write_sitecustomize(probe)
            source = (probe / "sitecustomize.py").read_text(encoding="utf8")
        self.assertIn('modules = ("verifier.dll"', source)
        self.assertIn("AHPY_APPVERIFIER_TOKEN", source)
        self.assertIn("loaded_verifier_modules", source)
        self.assertIn("injection is not active", source)

    def test_raw_log_copy_rejects_missing_target_logs(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-raw-") as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "unrelated.exe.1.dat").write_bytes(b"unrelated")
            with self.assertRaisesRegex(
                    RuntimeError, "no target-specific raw logs"):
                _copy_raw_logs(
                    root / "destination",
                    ["target.exe"],
                    source=source,
                )

    def _run_mocked_appverifier_main(
            self, root, *, positive_returncode=1, positive_has_error=True,
            runtime_count=EXPECTED_RUNTIME_PROCESSES, dirty_runtime=False,
            cleanup_returncode=0):
        python = root / "python.exe"
        python.touch()
        build_dir = root / "build"
        appverif = root / "appverif.exe"
        gflags = root / "gflags.exe"
        appverif.touch()
        gflags.touch()
        build_calls = []

        def copy2(source, destination):
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path(source).read_bytes())
            return str(destination)

        def run(command, **options):
            command = list(command)
            if "-export" in command:
                xml_argument = next(
                    item for item in command if str(item).startswith("To="))
                Path(str(xml_argument).split("=", 1)[1]).write_text(
                    (
                        "<log><entry Severity='Error'/></log>"
                        if positive_has_error
                        else "<log/>"
                    ),
                    encoding="utf8",
                )
                return SimpleNamespace(
                    stdout="", stderr="", returncode=0)
            return SimpleNamespace(
                stdout="positive stdout\n",
                stderr="positive stderr\n",
                returncode=positive_returncode,
            )

        def build(python_executable, runtime_prefix):
            build_calls.append((python_executable, runtime_prefix))
            runtime = build_dir / "runtime"
            markers = runtime / "markers"
            markers.mkdir(parents=True, exist_ok=True)
            for index in range(runtime_count):
                (runtime / ("runtime-%d.json" % index)).write_text(
                    "{}\n", encoding="utf8")
                (runtime / ("runtime-%d.xml" % index)).write_text(
                    (
                        "<log><entry Severity='Error'/></log>"
                        if dirty_runtime and index == 0
                        else "<log/>"
                    ),
                    encoding="utf8",
                )
                (markers / ("%d.json" % index)).write_text(
                    "{}\n", encoding="utf8")

        cleanup_record = {
            "command": ["cleanup"],
            "returncode": cleanup_returncode,
            "stdout": "",
            "stderr": "",
        }
        fake_os = SimpleNamespace(name="nt", getpid=lambda: 4321)
        fake_platform = SimpleNamespace(
            architecture=lambda: ("64bit", ""),
            machine=lambda: "AMD64",
            platform=lambda: "Windows-reviewed",
        )
        fake_ctypes = SimpleNamespace(
            windll=SimpleNamespace(
                shell32=SimpleNamespace(IsUserAnAdmin=lambda: 1)))
        argv = [
            "run_appverifier_hpy.py",
            "--python", str(python),
            "--build-dir", str(build_dir),
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(run_appverifier_hpy, "os", fake_os),
            mock.patch.object(run_appverifier_hpy, "platform", fake_platform),
            mock.patch.object(run_appverifier_hpy, "ctypes", fake_ctypes),
            mock.patch.object(
                run_appverifier_hpy.shutil, "which",
                return_value=str(python)),
            mock.patch.object(
                run_appverifier_hpy.shutil, "copy2",
                side_effect=copy2),
            mock.patch.object(
                run_appverifier_hpy, "_candidate_paths",
                side_effect=lambda name: [
                    appverif if name == "appverif.exe" else gflags]),
            mock.patch.object(
                run_appverifier_hpy, "_locate_tool",
                side_effect=[appverif, gflags]),
            mock.patch.object(
                run_appverifier_hpy, "discover_msvc_environment",
                return_value={"PATH": "reviewed"}),
            mock.patch.object(run_appverifier_hpy, "_write_sitecustomize"),
            mock.patch.object(
                run_appverifier_hpy, "_compile_positive_control"),
            mock.patch.object(run_appverifier_hpy, "_configure_target"),
            mock.patch.object(
                run_appverifier_hpy, "_run", side_effect=run),
            mock.patch.object(
                run_appverifier_hpy, "build_and_run", side_effect=build),
            mock.patch.object(
                run_appverifier_hpy, "_copy_raw_logs", return_value=[]),
            mock.patch.object(
                run_appverifier_hpy, "_cleanup_target",
                return_value=[cleanup_record]),
            mock.patch("builtins.print"),
        ):
            result = run_appverifier_hpy.main()
        return result, build_dir, build_calls

    def test_main_records_clean_windows_appverifier_evidence(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-main-") as temp:
            root = Path(temp)
            result, build_dir, build_calls = (
                self._run_mocked_appverifier_main(root))
            self.assertEqual(result, 0)
            self.assertEqual(len(build_calls), 1)
            self.assertEqual(
                build_calls[0][0], str((root / "python.exe").resolve()))
            runtime_prefix = build_calls[0][1]
            self.assertIn(str(RUNTIME_WRAPPER), runtime_prefix)
            self.assertEqual(runtime_prefix[-1], "--")
            environment = json.loads(
                (build_dir / "environment.json").read_text(encoding="utf8"))
            self.assertEqual(
                environment["expected_runtime_processes"],
                EXPECTED_RUNTIME_PROCESSES,
            )
            self.assertEqual(
                environment["diagnostic_scope"],
                "heap-corruption; not a native leak gate",
            )
            counts = json.loads(
                (build_dir / "runtime-counts.json").read_text(
                    encoding="utf8"))
            self.assertEqual(
                set(counts.values()), {EXPECTED_RUNTIME_PROCESSES})
            self.assertFalse(
                (root / "ahpy_appverifier_python_4321.exe").exists())
            cleanup = json.loads(
                (build_dir / "cleanup.json").read_text(encoding="utf8"))
            self.assertEqual(len(cleanup), 2)

    def test_main_validates_windows_host_and_selected_interpreter(self):
        with (
            mock.patch.object(
                run_appverifier_hpy, "os", SimpleNamespace(name="posix")
            ),
            mock.patch.object(sys, "argv", ["run_appverifier_hpy.py"]),
            mock.patch.object(sys, "stderr", io.StringIO()),
        ):
            self.assertEqual(run_appverifier_hpy.main(), 2)

        with (
            mock.patch.object(
                run_appverifier_hpy, "os", SimpleNamespace(name="nt")
            ),
            mock.patch.object(
                run_appverifier_hpy.platform, "architecture",
                return_value=("32bit", ""),
            ),
            mock.patch.object(sys, "argv", ["run_appverifier_hpy.py"]),
            self.assertRaisesRegex(RuntimeError, "64-bit Python"),
        ):
            run_appverifier_hpy.main()

        with (
            mock.patch.object(
                run_appverifier_hpy, "os", SimpleNamespace(name="nt")
            ),
            mock.patch.object(
                run_appverifier_hpy.platform, "architecture",
                return_value=("64bit", ""),
            ),
            mock.patch.object(
                run_appverifier_hpy.ctypes, "windll",
                SimpleNamespace(
                    shell32=SimpleNamespace(IsUserAnAdmin=lambda: 0)
                ),
                create=True,
            ),
            mock.patch.object(sys, "argv", ["run_appverifier_hpy.py"]),
            self.assertRaisesRegex(RuntimeError, "admin user"),
        ):
            run_appverifier_hpy.main()

        with (
            mock.patch.object(
                run_appverifier_hpy, "os", SimpleNamespace(name="nt")
            ),
            mock.patch.object(
                run_appverifier_hpy.platform, "architecture",
                return_value=("64bit", ""),
            ),
            mock.patch.object(
                run_appverifier_hpy.ctypes, "windll",
                SimpleNamespace(
                    shell32=SimpleNamespace(IsUserAnAdmin=lambda: 1)
                ),
                create=True,
            ),
            mock.patch.object(
                run_appverifier_hpy.shutil, "which", return_value=None
            ),
            mock.patch.object(sys, "argv", [
                "run_appverifier_hpy.py", "--python",
                "/definitely/missing/ahpy-python.exe",
            ]),
            self.assertRaisesRegex(FileNotFoundError, "does not exist"),
        ):
            run_appverifier_hpy.main()

    def test_main_tolerates_target_cleanup_race(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-appverif-main-") as temp:
            with mock.patch.object(Path, "unlink", side_effect=FileNotFoundError):
                result, _build_dir, _build_calls = (
                    self._run_mocked_appverifier_main(Path(temp))
                )
        self.assertEqual(result, 0)

    def test_main_rejects_failed_appverifier_evidence(self):
        cases = (
            (
                {"positive_returncode": 0},
                "positive control was not detected",
            ),
            (
                {"positive_has_error": False},
                "positive control produced no AppVerifier error",
            ),
            (
                {"runtime_count": EXPECTED_RUNTIME_PROCESSES - 1},
                "expected five verified runtime",
            ),
            (
                {"dirty_runtime": True},
                "AppVerifier reported runtime errors",
            ),
            (
                {"cleanup_returncode": 3},
                "cleanup failed",
            ),
        )
        for options, message in cases:
            with self.subTest(options=options):
                with tempfile.TemporaryDirectory(
                        prefix="ahpy-appverif-main-") as temp:
                    with self.assertRaisesRegex(RuntimeError, message):
                        self._run_mocked_appverifier_main(
                            Path(temp), **options)

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
