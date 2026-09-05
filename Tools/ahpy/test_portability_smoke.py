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
            failed_records = [{"name": "import-minimal", "status": "failed"}]
            argv[-1] = str(failed_report)
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
                mock.patch("builtins.print"),
                self.assertRaises(portability_smoke.PortabilityStageError),
            ):
                portability_smoke.main()
            report = json.loads(failed_report.read_text(encoding="utf8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["stages"], failed_records)
            self.assertEqual(
                report["failure"]["kind"], "PortabilityStageError")

            manifest_report = Path(temp) / "manifest-failed.json"
            argv[-1] = str(manifest_report)
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
