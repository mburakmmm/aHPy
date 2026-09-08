import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

import portability_smoke


class PortabilitySmokeTest(unittest.TestCase):
    def test_manifest_verification_rejects_changed_binary(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "demo.hpy0.so"
            binary.write_bytes(b"binary")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            manifest = {
                "builder": "CPython 3.11",
                "files": [{
                    "name": binary.name,
                    "size": binary.stat().st_size,
                    "sha256": digest,
                }],
            }
            (root / "artifact-manifest.json").write_text(
                json.dumps(manifest), encoding="utf8")
            self.assertEqual(
                portability_smoke.verify_manifest(root), manifest)
            binary.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "size mismatch"):
                portability_smoke.verify_manifest(root)

    def test_manifest_verification_rejects_unsafe_missing_and_changed_members(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            manifest_path = root / "artifact-manifest.json"
            cases = (
                (
                    {"name": "../escape", "size": 0, "sha256": ""},
                    "unsafe portability artifact member",
                ),
                (
                    {"name": "missing.hpy0.so", "size": 0, "sha256": ""},
                    "missing portability artifact member",
                ),
            )
            for record, message in cases:
                with self.subTest(message=message):
                    manifest_path.write_text(
                        json.dumps({"builder": "test", "files": [record]}),
                        encoding="utf8",
                    )
                    with self.assertRaisesRegex(RuntimeError, message):
                        portability_smoke.verify_manifest(root)

            binary = root / "demo.hpy0.so"
            binary.write_bytes(b"binary")
            manifest_path.write_text(
                json.dumps({
                    "builder": "test",
                    "files": [{
                        "name": binary.name,
                        "size": binary.stat().st_size,
                        "sha256": "0" * 64,
                    }],
                }),
                encoding="utf8",
            )
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                portability_smoke.verify_manifest(root)

    def test_native_directory_excludes_cpython_loader_stubs(self):
        with TemporaryDirectory() as source_temp, TemporaryDirectory() as dest_temp:
            source = Path(source_temp)
            destination = Path(dest_temp)
            (source / "demo.hpy0.so").write_bytes(b"binary")
            (source / "demo.py").write_text("raise AssertionError\n")
            manifest = {
                "files": [
                    {"name": "demo.hpy0.so"},
                    {"name": "demo.py"},
                ],
            }
            self.assertEqual(
                portability_smoke.prepare_native_directory(
                    source, manifest, destination),
                ["demo.hpy0.so"],
            )
            self.assertTrue((destination / "demo.hpy0.so").is_file())
            self.assertFalse((destination / "demo.py").exists())

    def test_native_directory_requires_a_universal_binary(self):
        with TemporaryDirectory() as source_temp, TemporaryDirectory() as dest_temp:
            source = Path(source_temp)
            destination = Path(dest_temp)
            (source / "demo.py").write_text("# loader\n", encoding="utf8")
            with self.assertRaisesRegex(
                    RuntimeError, "contains no Universal binaries"):
                portability_smoke.prepare_native_directory(
                    source,
                    {"files": [{"name": "demo.py"}]},
                    destination,
                )

    @mock.patch.object(portability_smoke.importlib.util, "find_spec")
    def test_loader_detection_fails_closed_to_native(self, find_spec):
        find_spec.side_effect = ModuleNotFoundError("hpy")
        self.assertFalse(portability_smoke.has_python_hpy_loader())
        find_spec.side_effect = None
        find_spec.return_value = object()
        self.assertTrue(portability_smoke.has_python_hpy_loader())

    def test_artifact_path_replaces_script_and_duplicate_entries(self):
        artifact = Path("/tmp/portable-artifact")
        script_dir = str(Path(portability_smoke.__file__).resolve().parent)
        with mock.patch.object(
                portability_smoke.sys, "path",
                [script_dir, str(artifact), "/retained"]):
            portability_smoke._activate_artifact_path(artifact)
            self.assertEqual(
                portability_smoke.sys.path,
                [str(artifact.resolve()), "/retained"],
            )

    def test_all_portability_stages_execute_semantic_oracles(self):
        minimal = ModuleType("ahpy_minimal")
        minimal.answer = lambda: 42
        minimal.return_none = lambda: None
        minimal.make_pair = lambda: [1, 2]
        minimal.keyword_count = lambda *args, **kwargs: len(kwargs)

        constants = ModuleType("constants_only")
        constants.VALUE = 47
        constants.NAME = "sabit"

        fibonacci = ModuleType("fibonacci")
        fibonacci.fib = lambda n: 0 if n == 0 else 55

        answer = ModuleType("bootstrap_answer")
        answer.return_none = lambda: None
        answer.return_big_integer = (
            lambda: 1234567890123456789012345678901234567890)
        answer.make_list = lambda: [1, None, 2]
        answer.make_dict = lambda: {"one": 1, 2: [None, {"nested": True}]}
        answer.default_values = lambda required: [required, 2, (3, None)]
        answer.identity = lambda value: value

        types = ModuleType("bootstrap_types")

        class Marker:
            pass

        class Box:
            value = None

            def owner(self):
                return self

            def identity(self, value):
                return value

        class Initialized:
            def __init__(self, value):
                self.value = value

        types.Marker = Marker
        types.make_marker = Marker
        types.make_box = Box
        types.Initialized = Initialized
        with (
            mock.patch.dict(
                sys.modules,
                {
                    "ahpy_minimal": minimal,
                    "constants_only": constants,
                    "fibonacci": fibonacci,
                    "bootstrap_answer": answer,
                    "bootstrap_types": types,
                },
            ),
            mock.patch.object(portability_smoke, "_activate_artifact_path"),
        ):
            for stage in portability_smoke.STAGES:
                with self.subTest(stage=stage):
                    self.assertIsNone(
                        portability_smoke.run_stage(stage, Path("/artifact")))
            with self.assertRaisesRegex(ValueError, "unknown portability stage"):
                portability_smoke.run_stage("unknown", Path("/artifact"))

    def test_execute_stages_records_output_and_rejects_exit_or_signal(self):
        success = SimpleNamespace(
            stdout="child stdout\n", stderr="child stderr\n", returncode=0)
        with (
            mock.patch.object(
                portability_smoke.subprocess, "run",
                return_value=success) as run,
            mock.patch("builtins.print") as printed,
        ):
            records = portability_smoke.execute_stages(
                Path("/artifact"), "python-stub")
        self.assertEqual(run.call_count, len(portability_smoke.STAGES))
        self.assertEqual(
            [record["name"] for record in records],
            list(portability_smoke.STAGES),
        )
        self.assertEqual({record["status"] for record in records}, {"passed"})
        self.assertTrue(any(
            call.args[:1] == ("child stdout\n",)
            for call in printed.call_args_list
        ))

        for returncode, detail in ((3, "exit 3"), (-9, "signal 9")):
            with (
                self.subTest(returncode=returncode),
                mock.patch.object(
                    portability_smoke.subprocess,
                    "run",
                    return_value=SimpleNamespace(
                        stdout="", stderr="", returncode=returncode),
                ) as failed_run,
                mock.patch("builtins.print"),
                self.assertRaisesRegex(
                    portability_smoke.PortabilityStageError, detail) as raised,
            ):
                portability_smoke.execute_stages(
                    Path("/artifact"), "native")
            first_command = failed_run.call_args.args[0]
            self.assertEqual(
                first_command[first_command.index("--stage") + 1],
                "import-minimal",
            )
            record = raised.exception.records[0]
            self.assertEqual(record["status"], "failed")
            if returncode < 0:
                self.assertEqual(record["termination"], "signal")
                self.assertEqual(record["signal"], -returncode)
            else:
                self.assertEqual(record["termination"], "exit")
                self.assertEqual(record["exit_code"], returncode)

    def test_write_report_creates_parent_and_canonical_json(self):
        with TemporaryDirectory() as temp:
            report_path = Path(temp) / "nested" / "result.json"
            portability_smoke.write_report(
                report_path, {"status": "passed", "schema_version": 1})
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf8")),
                {"schema_version": 1, "status": "passed"},
            )
            self.assertTrue(report_path.read_text(encoding="utf8").endswith("\n"))

    def test_capture_native_backtrace_is_bounded_and_structured(self):
        stdout = (
            "Program received signal SIGSEGV, Segmentation fault.\n"
            "#0  0x1 in first_frame ()\n"
            "#1  0x2 in second_frame ()\n"
        )
        with (
            mock.patch.object(
                portability_smoke.shutil, "which", return_value="/usr/bin/gdb"),
            mock.patch.object(
                portability_smoke.subprocess, "run",
                side_effect=[
                    SimpleNamespace(
                        returncode=0, stdout="GNU gdb 15.0\n", stderr=""),
                    SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
                ]) as run,
        ):
            evidence = portability_smoke.capture_native_backtrace(
                Path("/artifact"), "fibonacci-semantics")
        self.assertEqual(evidence["status"], "captured")
        self.assertEqual(evidence["tool_version"], "GNU gdb 15.0")
        self.assertEqual(evidence["signal"], "SIGSEGV")
        self.assertEqual(evidence["frame_count"], 2)
        self.assertFalse(evidence["stdout_truncated"])
        command = run.call_args_list[1].args[0]
        self.assertEqual(command[0], "/usr/bin/gdb")
        self.assertIn("set debuginfod enabled off", command)
        self.assertEqual(command[command.index("--stage") + 1],
                         "fibonacci-semantics")
        self.assertEqual(run.call_args_list[1].kwargs["timeout"], 120)
        self.assertEqual(run.call_args_list[1].kwargs["env"]["LC_ALL"], "C")

        with mock.patch.object(
                portability_smoke.shutil, "which", return_value=None):
            unavailable = portability_smoke.capture_native_backtrace(
                Path("/artifact"), "fibonacci-semantics")
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertIn("not found", unavailable["reason"])

    def test_capture_native_backtrace_reports_timeout(self):
        failure = portability_smoke.subprocess.TimeoutExpired(
            ["gdb"], 120, output=b"partial", stderr=b"diagnostic")
        with (
            mock.patch.object(
                portability_smoke.shutil, "which", return_value="/usr/bin/gdb"),
            mock.patch.object(
                portability_smoke.subprocess, "run", side_effect=[
                    SimpleNamespace(
                        returncode=0, stdout="GNU gdb 15.0\n", stderr=""),
                    failure,
                ]),
        ):
            evidence = portability_smoke.capture_native_backtrace(
                Path("/artifact"), "fibonacci-semantics")
        self.assertEqual(evidence["status"], "timeout")
        self.assertEqual(evidence["stdout"], "partial")
        self.assertEqual(evidence["stderr"], "diagnostic")

        with (
            mock.patch.object(
                portability_smoke.shutil, "which", return_value="/usr/bin/gdb"),
            mock.patch.object(
                portability_smoke.subprocess, "run", side_effect=[
                    SimpleNamespace(
                        returncode=0, stdout="GNU gdb 15.0\n", stderr=""),
                    OSError("cannot execute debugger"),
                ]),
        ):
            evidence = portability_smoke.capture_native_backtrace(
                Path("/artifact"), "fibonacci-semantics")
        self.assertEqual(evidence["status"], "error")
        self.assertIn("cannot execute debugger", evidence["reason"])

    def test_backtrace_output_bound_is_enforced_for_text_and_bytes(self):
        limit = portability_smoke.BACKTRACE_MAX_CHARS
        exact, exact_truncated = portability_smoke._bounded_output("x" * limit)
        oversized, oversized_truncated = portability_smoke._bounded_output(
            b"y" * (limit + 1))
        invalid, invalid_truncated = portability_smoke._bounded_output(
            b"valid\xff")

        self.assertEqual(len(exact), limit)
        self.assertFalse(exact_truncated)
        self.assertEqual(len(oversized), limit)
        self.assertTrue(oversized_truncated)
        self.assertEqual(invalid, "valid\ufffd")
        self.assertFalse(invalid_truncated)

    def test_main_dispatches_one_requested_stage(self):
        with (
            mock.patch.object(sys, "argv", [
                "portability_smoke.py",
                "--artifact-dir", "/artifact",
                "--stage", "import-answer",
            ]),
            mock.patch.object(
                portability_smoke, "run_stage") as run_stage,
        ):
            self.assertEqual(portability_smoke.main(), 0)
        run_stage.assert_called_once_with(
            "import-answer", Path("/artifact").resolve())

    def test_main_runs_python_stub_and_native_loader_paths(self):
        manifest = {"builder": "CPython 3.11", "files": []}
        with (
            mock.patch.object(
                sys, "argv",
                ["portability_smoke.py", "--artifact-dir", "/artifact"]),
            mock.patch.object(
                portability_smoke, "verify_manifest",
                return_value=manifest),
            mock.patch.object(
                portability_smoke, "_sha256", return_value="a" * 64),
            mock.patch.object(
                portability_smoke, "has_python_hpy_loader",
                return_value=True),
            mock.patch.object(
                portability_smoke, "execute_stages") as execute,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(portability_smoke.main(), 0)
        execute.assert_called_once_with(
            Path("/artifact").resolve(), "python-stub")

        with (
            mock.patch.object(
                sys, "argv",
                ["portability_smoke.py", "--artifact-dir", "/artifact"]),
            mock.patch.object(
                portability_smoke, "verify_manifest",
                return_value=manifest),
            mock.patch.object(
                portability_smoke, "_sha256", return_value="a" * 64),
            mock.patch.object(
                portability_smoke, "has_python_hpy_loader",
                return_value=False),
            mock.patch.object(
                portability_smoke, "prepare_native_directory",
                return_value=["demo.hpy0.so"]) as prepare,
            mock.patch.object(
                portability_smoke, "execute_stages") as execute,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(portability_smoke.main(), 0)
        self.assertEqual(prepare.call_args.args[:2], (
            Path("/artifact").resolve(), manifest))
        self.assertEqual(execute.call_args.args[1], "native")

    def test_main_defaults_to_the_script_artifact_directory(self):
        manifest = {"builder": "CPython 3.11", "files": []}
        with (
            mock.patch.object(sys, "argv", ["portability_smoke.py"]),
            mock.patch.object(
                portability_smoke, "verify_manifest", return_value=manifest
            ) as verify,
            mock.patch.object(
                portability_smoke, "_sha256", return_value="a" * 64),
            mock.patch.object(
                portability_smoke, "has_python_hpy_loader", return_value=True
            ),
            mock.patch.object(portability_smoke, "execute_stages"),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(portability_smoke.main(), 0)
        verify.assert_called_once_with(
            Path(portability_smoke.__file__).resolve().parent
        )

    def test_main_writes_passed_and_failed_evidence(self):
        manifest = {
            "builder": "CPython 3.11",
            "files": [{"name": "demo.hpy0.so", "sha256": "b" * 64}],
        }
        passed_stages = [{"name": "import-minimal", "status": "passed"}]
        with TemporaryDirectory() as temp:
            report_path = Path(temp) / "passed.json"
            argv = [
                "portability_smoke.py",
                "--artifact-dir", temp,
                "--report", str(report_path),
                "--capture-native-backtrace",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    portability_smoke, "verify_manifest", return_value=manifest),
                mock.patch.object(
                    portability_smoke, "_sha256", return_value="c" * 64),
                mock.patch.object(
                    portability_smoke, "has_python_hpy_loader", return_value=True),
                mock.patch.object(
                    portability_smoke, "execute_stages",
                    return_value=passed_stages),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(portability_smoke.main(), 0)
            report = json.loads(report_path.read_text(encoding="utf8"))
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["artifact_manifest_sha256"], "c" * 64)
            self.assertEqual(report["artifact_files"], manifest["files"])
            self.assertEqual(report["stages"], passed_stages)
            self.assertTrue(report["provenance"]["hpy_universal_loader"])
            self.assertEqual(
                report["provenance"]["extension_suffixes"],
                list(portability_smoke.importlib.machinery.EXTENSION_SUFFIXES),
            )

            failed_report = Path(temp) / "stage-failed.json"
            failed_records = [{
                "name": "import-minimal",
                "status": "failed",
                "termination": "signal",
                "signal": 11,
            }]
            argv[4] = str(failed_report)
            failure = portability_smoke.PortabilityStageError(
                "minimal signal", failed_records)
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    portability_smoke, "verify_manifest", return_value=manifest),
                mock.patch.object(
                    portability_smoke, "_sha256", return_value="c" * 64),
                mock.patch.object(
                    portability_smoke, "has_python_hpy_loader", return_value=True),
                mock.patch.object(
                    portability_smoke, "execute_stages", side_effect=failure),
                mock.patch.object(
                    portability_smoke, "capture_native_backtrace",
                    return_value={"status": "captured"}) as capture,
                mock.patch("builtins.print"),
                self.assertRaises(portability_smoke.PortabilityStageError),
            ):
                portability_smoke.main()
            report = json.loads(failed_report.read_text(encoding="utf8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["stages"], failed_records)
            self.assertEqual(
                report["failure"]["kind"], "PortabilityStageError")
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(
                report["native_backtrace"], {"status": "captured"})
            capture.assert_called_once_with(
                Path(temp).resolve(), "import-minimal")

            backtrace_error_report = Path(temp) / "backtrace-error.json"
            argv[4] = str(backtrace_error_report)
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    portability_smoke, "verify_manifest", return_value=manifest),
                mock.patch.object(
                    portability_smoke, "_sha256", return_value="c" * 64),
                mock.patch.object(
                    portability_smoke, "has_python_hpy_loader", return_value=True),
                mock.patch.object(
                    portability_smoke, "execute_stages", side_effect=failure),
                mock.patch.object(
                    portability_smoke, "capture_native_backtrace",
                    side_effect=RuntimeError("debugger wrapper failed")),
                mock.patch("builtins.print"),
                self.assertRaises(portability_smoke.PortabilityStageError),
            ):
                portability_smoke.main()
            report = json.loads(
                backtrace_error_report.read_text(encoding="utf8"))
            self.assertEqual(report["native_backtrace"]["status"], "error")
            self.assertIn(
                "debugger wrapper failed",
                report["native_backtrace"]["reason"],
            )

            exit_report = Path(temp) / "stage-exited.json"
            argv[4] = str(exit_report)
            exit_records = [{
                "name": "import-minimal",
                "status": "failed",
                "termination": "exit",
                "exit_code": 1,
            }]
            exit_failure = portability_smoke.PortabilityStageError(
                "minimal exit", exit_records)
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    portability_smoke, "verify_manifest", return_value=manifest),
                mock.patch.object(
                    portability_smoke, "_sha256", return_value="c" * 64),
                mock.patch.object(
                    portability_smoke, "has_python_hpy_loader", return_value=True),
                mock.patch.object(
                    portability_smoke, "execute_stages", side_effect=exit_failure),
                mock.patch.object(
                    portability_smoke, "capture_native_backtrace") as capture,
                mock.patch("builtins.print"),
                self.assertRaises(portability_smoke.PortabilityStageError),
            ):
                portability_smoke.main()
            report = json.loads(exit_report.read_text(encoding="utf8"))
            self.assertNotIn("native_backtrace", report)
            capture.assert_not_called()

            manifest_report = Path(temp) / "manifest-failed.json"
            argv[4] = str(manifest_report)
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    portability_smoke, "verify_manifest",
                    side_effect=RuntimeError("bad manifest")),
                self.assertRaisesRegex(RuntimeError, "bad manifest"),
            ):
                portability_smoke.main()
            report = json.loads(manifest_report.read_text(encoding="utf8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failure"]["kind"], "RuntimeError")

if __name__ == "__main__":
    unittest.main()
