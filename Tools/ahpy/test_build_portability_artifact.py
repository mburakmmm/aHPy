from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import build_portability_artifact as portability


class BuildPortabilityArtifactTest(unittest.TestCase):

    def test_file_sha256_hashes_complete_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.bin"
            payload = b"aHPy" * (300 * 1024)
            path.write_bytes(payload)
            digest = portability.file_sha256(path)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_build_artifact_copies_binaries_loaders_and_writes_manifest(self):
        environments = []
        setup_texts = []

        def fake_run(command, **options):
            environment = options["env"]
            environments.append(environment)
            if "--runtime-backend=hpy-universal" in command:
                generated = Path(command[command.index("-o") + 1])
                generated.write_text("generated Universal source\n")
                return
            setup_texts.append(Path(command[1]).read_text(encoding="utf8"))
            build_root = Path(command[command.index("--build-base") + 1])
            build_lib = build_root / "lib"
            build_lib.mkdir(parents=True)
            for module_name, _source in portability.SOURCES:
                (build_lib / (module_name + ".hpy0.so")).write_bytes(
                    ("binary-" + module_name).encode("ascii"))
                (build_lib / (module_name + ".py")).write_text(
                    "# loader for %s\n" % module_name)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "artifact"
            with (
                mock.patch.object(portability, "run", side_effect=fake_run),
                mock.patch.object(
                    portability, "verify_source_boundary") as verify_source,
                mock.patch.object(portability, "verify_binary_boundary"),
                mock.patch.object(
                    portability.subprocess,
                    "check_output",
                    return_value="CPython 3.11.15\n",
                ),
            ):
                portability.build_artifact("/tool/python", output)
            manifest = json.loads(
                (output / "artifact-manifest.json").read_text())

            expected_names = {
                "ahpy_minimal.hpy0.so",
                "ahpy_minimal.py",
                "constants_only.hpy0.so",
                "constants_only.py",
                "fibonacci.hpy0.so",
                "fibonacci.py",
                "bootstrap_answer.hpy0.so",
                "bootstrap_answer.py",
                "bootstrap_types.hpy0.so",
                "bootstrap_types.py",
                portability.SMOKE.name,
            }
            self.assertEqual(
                {entry["name"] for entry in manifest["files"]},
                expected_names,
            )
            for entry in manifest["files"]:
                artifact = output / entry["name"]
                self.assertEqual(entry["size"], artifact.stat().st_size)
                self.assertEqual(entry["sha256"],
                                 portability.file_sha256(artifact))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["builder"], "CPython 3.11.15")
        self.assertEqual(len(setup_texts), 1)
        self.assertIn(
            "Extension('constants_only', ['constants_only.c'])",
            setup_texts[0],
        )
        self.assertIn(
            "Extension('fibonacci', ['fibonacci.c'])",
            setup_texts[0],
        )
        self.assertIn(
            "Extension('bootstrap_answer', ['bootstrap_answer.c'])",
            setup_texts[0],
        )
        self.assertIn(
            "Extension('bootstrap_types', ['bootstrap_types.c'])",
            setup_texts[0],
        )
        self.assertIn(
            "Extension('ahpy_minimal', ['minimal_universal.c'])",
            setup_texts[0],
        )
        self.assertEqual(
            len(environments), len(portability.GENERATED_SOURCES) + 1)
        required_by_module = {
            call.args[0].stem: call.kwargs["required"]
            for call in verify_source.call_args_list
        }
        self.assertNotIn("HPyDef_METH", required_by_module["constants_only"])
        for module_name in ("fibonacci", "bootstrap_answer", "bootstrap_types"):
            self.assertIn("HPyDef_METH", required_by_module[module_name])
        for environment in environments:
            self.assertEqual(environment["SOURCE_DATE_EPOCH"], "946684800")
            self.assertEqual(environment["ZERO_AR_DATE"], "1")
            self.assertIn("-ffile-prefix-map=", environment["CFLAGS"])
            self.assertIn("-fdebug-prefix-map=", environment["CXXFLAGS"])

    def test_build_artifact_rejects_nonempty_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "artifact"
            output.mkdir()
            (output / "existing").touch()
            with self.assertRaisesRegex(RuntimeError, "not empty"):
                portability.build_artifact("python", output)

    def test_build_artifact_rejects_incomplete_or_split_build_outputs(self):
        binary_root = Path("/definitely/missing/ahpy-build")
        cases = (
            (([],), "expected 5 Universal binaries"),
            (([
                binary_root / "one" / "bootstrap_answer.hpy0.so",
                binary_root / "two" / "bootstrap_types.hpy0.so",
                binary_root / "three" / "ahpy_minimal.hpy0.so",
                binary_root / "four" / "constants_only.hpy0.so",
                binary_root / "five" / "fibonacci.hpy0.so",
            ],), "different build dirs"),
            (([
                binary_root / "bootstrap_answer.hpy0.so",
                binary_root / "bootstrap_types.hpy0.so",
                binary_root / "ahpy_minimal.hpy0.so",
                binary_root / "constants_only.hpy0.so",
                binary_root / "fibonacci.hpy0.so",
            ], []), "missing artifact file"),
        )
        for find_results, message in cases:
            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "artifact"
                with (
                    self.subTest(message=message),
                    mock.patch.object(portability, "run"),
                    mock.patch.object(portability, "verify_source_boundary"),
                    mock.patch.object(portability, "verify_binary_boundary"),
                    mock.patch.object(
                        portability, "find_universal_binaries",
                        side_effect=find_results,
                    ),
                    self.assertRaisesRegex(AssertionError, message),
                ):
                    portability.build_artifact("python", output)

    def test_main_accepts_an_existing_interpreter_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            output = Path(temp_dir) / "artifact"
            argv = [
                "build_portability_artifact.py",
                "--python", str(python),
                "--output", str(output),
            ]
            with (
                mock.patch("sys.argv", argv),
                mock.patch.object(portability, "build_artifact") as build,
                mock.patch("builtins.print"),
            ):
                portability.main()
        build.assert_called_once_with(
            os.path.abspath(python), output.absolute())

    def test_main_resolves_an_interpreter_from_path(self):
        argv = [
            "build_portability_artifact.py",
            "--python", "ahpy-python",
            "--output", "artifact",
        ]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                portability.shutil, "which", return_value="/tool/python"),
            mock.patch.object(portability, "build_artifact") as build,
            mock.patch("builtins.print"),
        ):
            portability.main()
        build.assert_called_once_with(
            "/tool/python", Path("artifact").absolute())

    def test_main_rejects_a_missing_interpreter(self):
        argv = [
            "build_portability_artifact.py",
            "--python", "missing-python",
            "--output", "artifact",
        ]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(portability.shutil, "which", return_value=None),
            mock.patch("sys.stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            portability.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
