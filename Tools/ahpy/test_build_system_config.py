import io
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import build_system_config as config
from test_direct_build import _probe


contract_config = sys.modules["ahpy_build_config"]
create_contract = config.create_contract
render_cmake = config.render_cmake
render_meson = config.render_meson


class BuildSystemConfigTest(unittest.TestCase):
    def test_python_resolution_and_probe_fail_closed(self):
        with TemporaryDirectory() as temp:
            interpreter = Path(temp) / "python"
            interpreter.touch()
            self.assertEqual(
                contract_config.resolve_python(str(interpreter)),
                os.path.abspath(interpreter),
            )

        with mock.patch.object(
            contract_config.shutil, "which", return_value="/tools/python"
        ):
            self.assertEqual(
                contract_config.resolve_python("python"), "/tools/python")
        with mock.patch.object(contract_config.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "interpreter not found"):
                contract_config.resolve_python("missing-python")

        cases = (
            (mock.Mock(returncode=1, stdout="", stderr="no HPy"),
             "cannot describe its HPy toolchain"),
            (mock.Mock(returncode=0, stdout="not-json", stderr=""),
             "invalid HPy toolchain probe JSON"),
        )
        for result, message in cases:
            with (
                self.subTest(message=message),
                mock.patch.object(
                    contract_config, "resolve_python", return_value="/python"
                ),
                mock.patch.object(
                    contract_config.subprocess, "run", return_value=result
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, message):
                    contract_config.probe_toolchain("python")

        with (
            mock.patch.object(
                contract_config, "resolve_python", return_value="/python"
            ),
            mock.patch.object(
                contract_config.subprocess,
                "run",
                return_value=mock.Mock(
                    returncode=0,
                    stdout='{"python": "ignored", "abi": "universal"}',
                    stderr="",
                ),
            ) as run,
        ):
            probe = contract_config.probe_toolchain("python")
        self.assertEqual(probe["python"], "/python")
        self.assertEqual(probe["abi"], "universal")
        self.assertEqual(run.call_args.args[0][:2], ["/python", "-c"])

    def test_static_contract_and_renderers_preserve_universal_boundary(self):
        with TemporaryDirectory() as temp:
            probe = _probe(root=temp)
            Path(probe["forbid_python_h"]).mkdir(parents=True)
            Path(probe["include_dirs"][0]).mkdir(parents=True)
            contract = create_contract(probe, "demo", "static")
        self.assertEqual(contract["abi"], "universal")
        self.assertEqual(contract["initializer"], "HPyInit_demo")
        self.assertEqual(contract["definitions"], ["HPY", "HPY_ABI_UNIVERSAL"])
        self.assertEqual(contract["runtime_mode"], "static")
        self.assertLess(
            contract["include_dirs"].index(probe["forbid_python_h"]),
            contract["include_dirs"].index(probe["include_dirs"][0]))
        cmake = render_cmake(contract)
        meson = render_meson(contract)
        self.assertIn('set(AHPY_ABI "universal")', cmake)
        self.assertIn('set(AHPY_EXTENSION_SUFFIX ".hpy0.so")', cmake)
        self.assertIn("ahpy_abi = 'universal'", meson)
        self.assertIn("ahpy_name_suffix = 'hpy0.so'", meson)

    def test_windows_and_source_runtime_contracts(self):
        with TemporaryDirectory() as temp:
            probe = _probe("nt", temp)
            Path(probe["forbid_python_h"]).mkdir(parents=True)
            Path(probe["include_dirs"][0]).mkdir(parents=True)
            contract = create_contract(probe, "demo", "sources")
        self.assertTrue(contract["is_windows"])
        self.assertEqual(contract["name_suffix"], "hpy0.pyd")
        self.assertEqual(contract["runtime_library"], "")
        self.assertEqual(contract["runtime_sources"], probe["runtime_sources"])
        self.assertIn("ahpy_windows = true", render_meson(contract))

    def test_invalid_module_fails_before_rendering(self):
        with TemporaryDirectory() as temp:
            probe = _probe(root=temp)
            with self.assertRaisesRegex(ValueError, "plain C identifier"):
                create_contract(probe, "bad.name")

    def test_runtime_and_include_validation_fail_closed(self):
        with TemporaryDirectory() as temp:
            probe = _probe(root=temp)
            cases = (
                ("invalid", probe, "runtime must be"),
                ("auto", {**probe, "extension_suffix": ".cpython.so"},
                 "non-Universal suffix"),
                ("static", {**probe, "static_libraries": []},
                 "requires exactly one library"),
                ("static", {**probe, "static_libraries": ["one", "two"]},
                 "requires exactly one library"),
                ("sources", {**probe, "runtime_sources": ["missing.c"]},
                 "runtime input does not exist"),
            )
            for runtime, candidate, message in cases:
                with self.subTest(runtime=runtime, message=message):
                    with self.assertRaisesRegex((ValueError, RuntimeError), message):
                        contract_config.select_universal_runtime(
                            candidate, runtime
                        )

            Path(probe["forbid_python_h"]).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "include directory"):
                create_contract(probe, "demo", "static")

    def test_renderers_reject_unsafe_contract_values_and_escape_quotes(self):
        with TemporaryDirectory() as temp:
            probe = _probe(root=temp)
            Path(probe["forbid_python_h"]).mkdir(parents=True)
            Path(probe["include_dirs"][0]).mkdir(parents=True)
            contract = create_contract(probe, "demo", "static")

        for unsafe in ("bad\npath", "bad\rpath", "bad;path"):
            with self.subTest(renderer="cmake", unsafe=repr(unsafe)):
                candidate = {**contract, "runtime_library": unsafe}
                with self.assertRaisesRegex(ValueError, "unsupported characters"):
                    render_cmake(candidate)
        for unsafe in ("bad\npath", "bad\rpath"):
            with self.subTest(renderer="meson", unsafe=repr(unsafe)):
                candidate = {**contract, "runtime_library": unsafe}
                with self.assertRaisesRegex(ValueError, "newline"):
                    render_meson(candidate)

        quoted = {**contract, "runtime_library": 'a\\b"c'}
        self.assertIn('"a/b\\"c"', render_cmake(quoted))
        quoted = {**contract, "runtime_library": "a\\b'c"}
        self.assertIn("'a\\\\b\\'c'", render_meson(quoted))

    def test_cli_renders_every_supported_format_to_stdout(self):
        contract = {"abi": "universal"}
        cases = (
            ("json", '{\n  "abi": "universal"\n}\n'),
            ("cmake", "cmake-contract\n"),
            ("meson", "meson-contract\n"),
        )
        for output_format, expected in cases:
            with self.subTest(output_format=output_format):
                argv = [
                    "build_system_config.py",
                    "--python", "python",
                    "--module", "demo",
                    "--runtime", "static",
                    "--format", output_format,
                ]
                stdout = io.StringIO()
                with (
                    mock.patch("sys.argv", argv),
                    mock.patch.object(
                        config, "probe_toolchain", return_value={"probe": True}
                    ) as probe,
                    mock.patch.object(
                        config, "create_contract", return_value=contract
                    ) as create,
                    mock.patch.object(
                        config, "render_cmake", return_value="cmake-contract\n"
                    ),
                    mock.patch.object(
                        config, "render_meson", return_value="meson-contract\n"
                    ),
                    mock.patch.object(config.sys, "stdout", stdout),
                ):
                    config.main()
                probe.assert_called_once_with("python")
                create.assert_called_once_with(
                    {"probe": True}, "demo", "static")
                self.assertEqual(stdout.getvalue(), expected)

    def test_cli_creates_parent_and_writes_selected_output(self):
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "contract.cmake"
            argv = [
                "build_system_config.py",
                "--module", "demo",
                "--format", "cmake",
                "--output", str(output),
            ]
            with (
                mock.patch("sys.argv", argv),
                mock.patch.object(
                    config, "probe_toolchain", return_value={"probe": True}),
                mock.patch.object(
                    config, "create_contract",
                    return_value={"abi": "universal"}),
                mock.patch.object(
                    config, "render_cmake", return_value="cmake-contract\n"),
            ):
                config.main()
            self.assertEqual(output.read_text(), "cmake-contract\n")


if __name__ == "__main__":
    unittest.main()
