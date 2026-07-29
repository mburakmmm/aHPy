import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import build_system_config as config
from test_direct_build import _probe


create_contract = config.create_contract
render_cmake = config.render_cmake
render_meson = config.render_meson


class BuildSystemConfigTest(unittest.TestCase):
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
