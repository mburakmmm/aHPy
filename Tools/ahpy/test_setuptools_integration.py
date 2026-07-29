import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

import setuptools_integration as integration


EXTERNAL_HEADER = integration.EXTERNAL_HEADER
EXTERNAL_SOURCE = integration.EXTERNAL_SOURCE
SETUP = integration.SETUP
SOURCE = integration.SOURCE


class SetuptoolsIntegrationDefinitionTest(unittest.TestCase):
    def test_example_selects_backend_and_hpy_extension_lane(self):
        self.assertIn('runtime_backend="hpy-universal"', SETUP)
        self.assertIn("hpy_ext_modules=extensions", SETUP)
        self.assertIn("cdef class Box", SOURCE)
        self.assertIn('cdef extern from "ahpy_external.h"', SOURCE)
        self.assertIn("ahpy_external_nogil_probe() noexcept nogil", SOURCE)
        self.assertIn(
            "ahpy_external_nogil_advance(long long amount) noexcept nogil",
            SOURCE,
        )
        self.assertIn("def external_nogil_ordered(amount, /)", SOURCE)
        self.assertIn("def external_nogil_result(amount, /)", SOURCE)
        self.assertIn("def external_nogil_targets(obj, mapping, /)", SOURCE)
        self.assertIn("nogil_stored_result = 0", SOURCE)
        self.assertIn("mapping[1:2] = ahpy_external_nogil_advance(4)", SOURCE)
        self.assertIn(
            "ahpy_external_errno_advance(long long amount) except -1 nogil",
            SOURCE,
        )
        self.assertIn("ahpy_external_missing_errno() except -1 nogil", SOURCE)
        self.assertIn("ahpy_external_nogil_probe_calls()", SOURCE)
        self.assertIn("ahpy_external_nogil_probe(void)", EXTERNAL_SOURCE)
        self.assertIn(
            "ahpy_external_nogil_advance(long long amount)",
            EXTERNAL_SOURCE,
        )
        self.assertIn("errno = EDOM", EXTERNAL_SOURCE)
        self.assertIn("ahpy_external_missing_errno(void)", EXTERNAL_SOURCE)
        self.assertIn("ahpy_external.c", SETUP)
        self.assertNotIn("Python.h", EXTERNAL_HEADER + EXTERNAL_SOURCE)
        compile(SETUP, "<ahpy-setuptools-setup>", "exec")

    def test_runtime_program_selects_normal_and_debug_leak_checks(self):
        normal = integration._runtime_program(False)
        debug = integration._runtime_program(True)
        self.assertNotIn("LeakDetector", normal)
        self.assertIn("assert module.answer() == 42", normal)
        self.assertIn("LeakDetector", debug)
        self.assertIn("detector.start()", debug)
        self.assertIn("detector.stop()", debug)

    def test_build_and_run_audits_tree_wheel_and_installed_runtime(self):
        calls = []
        binary_box = {}

        def fake_run(command, **options):
            calls.append((command, options))
            if "--build-base" in command:
                temp = Path(options["cwd"])
                (temp / (integration.MODULE_NAME + ".c")).write_text(
                    "generated Universal C\n")
                build_root = Path(command[command.index("--build-base") + 1])
                build_lib = build_root / "lib"
                build_lib.mkdir(parents=True)
                binary = build_lib / (
                    integration.MODULE_NAME + ".hpy0.so")
                binary.write_bytes(b"binary")
                binary_box["path"] = binary
            elif "bdist_wheel" in command:
                dist = Path(command[command.index("--dist-dir") + 1])
                dist.mkdir()
                wheel = dist / "ahpy_setuptools_example-0-py3-none-any.whl"
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr(
                        integration.MODULE_NAME + ".hpy0.so", b"binary")
                    archive.writestr(
                        integration.MODULE_NAME + ".py", "# loader\n")
                    archive.writestr(
                        "ahpy_setuptools_example-0.dist-info/WHEEL",
                        "Wheel-Version: 1.0\n"
                        "Tag: py3-none-any\n",
                    )

        def require_binary(_root, _module_name):
            return binary_box["path"]

        with (
            mock.patch.object(integration, "run", side_effect=fake_run),
            mock.patch.object(integration, "verify_source_boundary"),
            mock.patch.object(integration, "verify_binary_boundary"),
            mock.patch.object(
                integration, "require_universal_binary",
                side_effect=require_binary,
            ),
        ):
            result = integration.build_and_run("/tool/python")

        self.assertEqual(
            result,
            {
                "wheel": "ahpy_setuptools_example-0-py3-none-any.whl",
                "tags": ["py3-none-any"],
            },
        )
        self.assertEqual(len(calls), 7)
        runtime_calls = [
            (command, options)
            for command, options in calls
            if len(command) > 1 and command[1] == "-c"
        ]
        self.assertEqual(len(runtime_calls), 4)
        self.assertNotIn("HPY", runtime_calls[0][1]["env"])
        self.assertEqual(runtime_calls[1][1]["env"]["HPY"], "trace")
        self.assertEqual(runtime_calls[2][1]["env"]["HPY"], "debug")
        self.assertNotIn("HPY", runtime_calls[3][1]["env"])

    def test_main_accepts_an_existing_interpreter_path(self):
        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            argv = ["setuptools_integration.py", "--python", str(python)]
            with (
                mock.patch("sys.argv", argv),
                mock.patch.object(
                    integration, "build_and_run",
                    return_value={"wheel": "example.whl", "tags": ["tag"]},
                ) as build,
                mock.patch("builtins.print"),
            ):
                integration.main()
        build.assert_called_once_with(os.path.abspath(python))

    def test_main_resolves_an_interpreter_from_path(self):
        argv = ["setuptools_integration.py", "--python", "ahpy-python"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                integration.shutil, "which", return_value="/tool/python"),
            mock.patch.object(
                integration, "build_and_run",
                return_value={"wheel": "example.whl", "tags": ["tag"]},
            ) as build,
            mock.patch("builtins.print"),
        ):
            integration.main()
        build.assert_called_once_with("/tool/python")

    def test_main_rejects_a_missing_interpreter(self):
        argv = ["setuptools_integration.py", "--python", "missing-python"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(integration.shutil, "which", return_value=None),
            mock.patch("sys.stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            integration.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
