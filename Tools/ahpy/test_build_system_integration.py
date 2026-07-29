import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import build_system_integration as integration


EXAMPLES = integration.EXAMPLES


class BuildSystemIntegrationDefinitionTest(unittest.TestCase):
    def test_cmake_example_consumes_only_generated_universal_contract(self):
        source = (EXAMPLES["cmake"][0] / "CMakeLists.txt").read_text(
            encoding="utf8")
        self.assertIn('include("${AHPY_CONFIG}")', source)
        self.assertIn('AHPY_ABI STREQUAL "universal"', source)
        self.assertIn("${AHPY_RUNTIME_SOURCES}", source)
        self.assertIn("${AHPY_RUNTIME_LIBRARY}", source)
        self.assertIn('SUFFIX "${AHPY_EXTENSION_SUFFIX}"', source)
        self.assertIn('"/EXPORT:${AHPY_INITIALIZER}"', source)

    def test_meson_example_consumes_only_generated_universal_contract(self):
        source = (EXAMPLES["meson"][0] / "meson.build").read_text(
            encoding="utf8")
        self.assertIn("subdir('ahpy_config')", source)
        self.assertIn("ahpy_abi != 'universal'", source)
        self.assertIn("ahpy_runtime_sources", source)
        self.assertIn("ahpy_runtime_library", source)
        self.assertIn("'vs_module_defs': files('exports.def')", source)

    def test_examples_do_not_commit_generated_contract_or_c(self):
        for example, module in EXAMPLES.values():
            self.assertFalse((example / (module + ".c")).exists())
            self.assertFalse((example / "ahpy_config").exists())

    def test_runtime_program_selects_normal_and_debug_modes(self):
        normal = integration._runtime_program(
            "demo", Path("/tmp/demo.hpy0.so"), False)
        debug = integration._runtime_program(
            "demo", Path("/tmp/demo.hpy0.so"), True)
        self.assertIn("universal.MODE_UNIVERSAL", normal)
        self.assertNotIn("LeakDetector", normal)
        self.assertIn("universal.MODE_DEBUG", debug)
        self.assertIn("detector.start()", debug)
        self.assertIn("detector.stop()", debug)

    def test_tool_prefers_adjacent_then_path_and_rejects_missing(self):
        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "bin" / "python"
            python.parent.mkdir()
            python.touch()
            adjacent = python.parent / (
                "cmake.exe" if os.name == "nt" else "cmake")
            adjacent.touch()
            self.assertEqual(integration._tool("cmake", str(python)),
                             str(adjacent))
            adjacent.unlink()
            with mock.patch.object(
                    integration.shutil, "which", return_value="/tool/cmake"):
                self.assertEqual(
                    integration._tool("cmake", str(python)), "/tool/cmake")
            with (
                mock.patch.object(
                    integration.shutil, "which", return_value=None),
                self.assertRaisesRegex(RuntimeError, "not installed"),
            ):
                integration._tool("cmake", str(python))

    def _contract(self, module_name):
        return {
            "module_name": module_name,
            "extension_suffix": ".hpy0.so",
            "abi": "universal",
            "hpy_version": "0.9.0",
            "runtime_mode": "static",
        }

    def test_prepare_writes_cmake_and_meson_contracts(self):
        for system, rendered in (
                ("cmake", "set(AHPY_ABI \"universal\")\n"),
                ("meson", "ahpy_abi = 'universal'\n")):
            with self.subTest(system=system), TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                module_name = EXAMPLES[system][1]
                contract = self._contract(module_name)
                with (
                    mock.patch.object(integration, "_run") as run,
                    mock.patch.object(integration, "verify_source_boundary"),
                    mock.patch.object(
                        integration, "probe_toolchain",
                        return_value={"python": "/tool/python"},
                    ),
                    mock.patch.object(
                        integration, "create_contract",
                        return_value=contract,
                    ),
                    mock.patch.object(
                        integration, "render_cmake",
                        return_value=rendered,
                    ),
                    mock.patch.object(
                        integration, "render_meson",
                        return_value=rendered,
                    ),
                ):
                    project, generated, result, config = integration._prepare(
                        system, "/tool/python", temp, {"ENV": "1"})
                self.assertEqual(result, contract)
                self.assertEqual(generated, project / (module_name + ".c"))
                self.assertEqual(config.read_text(), rendered)
                self.assertEqual(run.call_count, 1)

    def test_cmake_build_runs_configure_and_build(self):
        with TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            prepared = (
                temp / "project",
                temp / "generated.c",
                self._contract("demo"),
                temp / "config.cmake",
            )
            with (
                mock.patch.object(
                    integration, "_prepare", return_value=prepared),
                mock.patch.object(
                    integration, "_tool", return_value="/tool/cmake"),
                mock.patch.object(integration, "_run") as run,
            ):
                result = integration._build_cmake(
                    "/tool/python", temp, {"ENV": "1"})
            self.assertEqual(result, (prepared[1], prepared[2],
                                      temp / "cmake-build"))
            self.assertEqual(run.call_count, 2)
            self.assertIn("-DAHPY_CONFIG=%s" % prepared[3],
                          run.call_args_list[0].args[0])

    def test_meson_build_runs_setup_and_compile_with_python_path(self):
        with TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            prepared = (
                temp / "project",
                temp / "generated.c",
                self._contract("demo"),
                temp / "meson.build",
            )
            with (
                mock.patch.object(
                    integration, "_prepare", return_value=prepared),
                mock.patch.object(
                    integration, "_tool",
                    side_effect=("/tool/meson", "/tool/ninja"),
                ) as tool,
                mock.patch.object(integration, "_run") as run,
            ):
                result = integration._build_meson(
                    "/venv/bin/python", temp, {"ENV": "1"})
            self.assertEqual(result, (prepared[1], prepared[2],
                                      temp / "meson-build"))
            self.assertEqual(tool.call_count, 2)
            self.assertEqual(run.call_count, 2)
            meson_environment = run.call_args_list[0].kwargs["env"]
            self.assertTrue(meson_environment["PATH"].startswith(
                "/venv/bin" + os.pathsep))

    def _fake_build(self, system):
        def build(_python, temp, _environment):
            module_name = "ahpy_%s_example" % system
            generated = temp / (module_name + ".c")
            generated.write_text("generated\n")
            build_root = temp / (system + "-build")
            build_root.mkdir()
            (build_root / (module_name + ".hpy0.so")).write_bytes(b"binary")
            return generated, self._contract(module_name), build_root
        return build

    def test_build_and_run_audits_both_systems_and_writes_report(self):
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "build-systems.json"
            with (
                mock.patch.object(
                    integration, "probe_toolchain",
                    return_value={"python": "/tool/python"},
                ),
                mock.patch.object(
                    integration, "_build_cmake",
                    side_effect=self._fake_build("cmake"),
                ),
                mock.patch.object(
                    integration, "_build_meson",
                    side_effect=self._fake_build("meson"),
                ),
                mock.patch.object(integration, "verify_source_boundary"),
                mock.patch.object(integration, "verify_binary_boundary"),
                mock.patch.object(integration, "_run") as run,
            ):
                report = integration.build_and_run(
                    "python", report_path=output)
            self.assertEqual(
                [item["system"] for item in report["results"]],
                ["cmake", "meson"],
            )
            self.assertEqual(run.call_count, 4)
            programs = [call.args[0][2] for call in run.call_args_list]
            self.assertEqual(
                sum("MODE_DEBUG" in program for program in programs), 2)
            self.assertEqual(json.loads(output.read_text()), report)

    def test_build_and_run_rejects_unknown_system(self):
        with (
            mock.patch.object(
                integration, "probe_toolchain",
                return_value={"python": "/tool/python"},
            ),
            self.assertRaisesRegex(ValueError, "unknown build system"),
        ):
            integration.build_and_run("python", systems=("unknown",))

    def test_build_and_run_requires_exactly_one_artifact(self):
        def empty_build(_python, temp, _environment):
            generated = temp / "demo.c"
            build = temp / "build"
            build.mkdir()
            return generated, self._contract("demo"), build

        with (
            mock.patch.object(
                integration, "probe_toolchain",
                return_value={"python": "/tool/python"},
            ),
            mock.patch.object(
                integration, "_build_cmake", side_effect=empty_build),
            self.assertRaisesRegex(AssertionError, "produced 0"),
        ):
            integration.build_and_run("python", systems=("cmake",))

    def test_main_selects_all_or_one_build_system(self):
        for selection, expected in (
                ("all", ("cmake", "meson")),
                ("cmake", ("cmake",))):
            with self.subTest(selection=selection):
                argv = [
                    "build_system_integration.py",
                    "--python", "python",
                    "--system", selection,
                ]
                report = {
                    "results": [
                        {"system": system} for system in expected
                    ],
                }
                with (
                    mock.patch("sys.argv", argv),
                    mock.patch.object(
                        integration, "build_and_run",
                        return_value=report,
                    ) as build,
                    mock.patch("builtins.print"),
                ):
                    integration.main()
                build.assert_called_once_with("python", expected, None)


if __name__ == "__main__":
    unittest.main()
