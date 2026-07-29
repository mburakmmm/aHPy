import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

from ahpy_version import AHPY_DISTRIBUTION, AHPY_VERSION
import scikit_build_integration as integration


EXAMPLE = integration.EXAMPLE


class ScikitBuildDefinitionTest(unittest.TestCase):
    def test_isolated_project_pins_frontend_and_universal_generation(self):
        pyproject = (EXAMPLE / "pyproject.toml").read_text(encoding="utf8")
        cmake = (EXAMPLE / "CMakeLists.txt").read_text(encoding="utf8")
        self.assertIn(
            '"%s==%s"' % (AHPY_DISTRIBUTION, AHPY_VERSION), pyproject)
        self.assertIn('"scikit-build-core==1.0.3"', pyproject)
        self.assertIn('"cmake==4.3.4"', pyproject)
        self.assertIn('"ninja==1.13.0"', pyproject)
        self.assertIn("--runtime-backend=hpy-universal", cmake)
        self.assertIn("configure_ahpy.py", cmake)
        self.assertIn("${AHPY_EXTENSION_SUFFIX}", cmake)
        self.assertNotIn('"Cython', pyproject)
        integration = Path(__file__).with_name(
            "scikit_build_integration.py").read_text(encoding="utf8")
        self.assertIn('"setuptools==80.9.0"', integration)
        self.assertIn('isolated["PIP_NO_INDEX"] = "1"', integration)
        dependency_materialization = integration.split(
            '"hpy==0.9.0"', 1)[0].rsplit("[", 1)[-1]
        self.assertNotIn("--no-build-isolation", dependency_materialization)

    def test_loader_uses_public_hpy_load_and_runtime_mode(self):
        loader = (EXAMPLE / "ahpy_scikit_build_example.py").read_text(
            encoding="utf8")
        self.assertIn("_universal.load", loader)
        self.assertIn("MODE_DEBUG", loader)
        self.assertNotIn("_load_bootstrap", loader)

    def test_run_delegates_to_checked_subprocess(self):
        with mock.patch.object(integration.subprocess, "run") as run:
            integration._run(["python", "-V"], cwd=Path("/tmp"), env={"A": "1"})
        run.assert_called_once_with(
            ["python", "-V"], cwd=Path("/tmp"), env={"A": "1"}, check=True)

    def test_runtime_program_selects_normal_and_debug_leak_checks(self):
        normal = integration._runtime_program(False)
        debug = integration._runtime_program(True)
        self.assertNotIn("LeakDetector", normal)
        self.assertIn("assert module.answer() == 42", normal)
        self.assertIn("LeakDetector", debug)
        self.assertIn("detector.start()", debug)
        self.assertIn("detector.stop()", debug)

    def test_build_and_run_materializes_isolated_wheel_and_report(self):
        calls = []

        def copy_frontend(destination):
            destination.mkdir()

        def fake_run(command, **options):
            calls.append((command, options))
            if command[1:4] == ["-m", "pip", "wheel"]:
                wheel_dir = Path(command[command.index("--wheel-dir") + 1])
                if any("frontend-source" in argument for argument in command):
                    (wheel_dir / "ahpy_compiler-0-py3-none-any.whl").write_bytes(
                        b"frontend")
                elif "hpy==0.9.0" in command:
                    for name in (
                            "hpy-0.9.0-py3-none-any.whl",
                            "scikit_build_core-1.0.3-py3-none-any.whl",
                            "cmake-4.3.4-py3-none-any.whl",
                            "ninja-1.13.0-py3-none-any.whl",
                            "setuptools-80.9.0-py3-none-any.whl"):
                        (wheel_dir / name).write_bytes(name.encode("ascii"))
                else:
                    project = Path(command[-1])
                    (project / (integration.MODULE + ".c")).write_text(
                        "generated Universal C\n")
                    wheel = (
                        wheel_dir /
                        "ahpy_scikit_build_example-0-cp311-cp311-any.whl"
                    )
                    with zipfile.ZipFile(wheel, "w") as archive:
                        archive.writestr(
                            integration.MODULE + ".hpy0.so", b"binary")
                        archive.writestr(
                            integration.MODULE + ".py", "# loader\n")
                        archive.writestr(
                            "ahpy_scikit_build_example-0.dist-info/WHEEL",
                            "Wheel-Version: 1.0\n"
                            "Tag: cp311-cp311-any\n",
                        )

        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            output = Path(temp_dir) / "evidence" / "scikit-build.json"
            with (
                mock.patch.object(
                    integration, "_copy_frontend_source",
                    side_effect=copy_frontend,
                ),
                mock.patch.object(integration, "_run", side_effect=fake_run),
                mock.patch.object(integration, "_frontend_metadata"),
                mock.patch.object(integration, "verify_binary_boundary"),
                mock.patch.object(integration, "verify_source_boundary"),
            ):
                report = integration.build_and_run(str(python), output)
            self.assertEqual(json.loads(output.read_text()), report)

        self.assertEqual(report["schema_version"], 1)
        self.assertTrue(report["build_isolation"])
        self.assertEqual(report["runtime_modes"], ["normal", "debug"])
        self.assertEqual(
            report["wheel"]["hpy_binary"],
            integration.MODULE + ".hpy0.so",
        )
        self.assertEqual(report["wheel"]["tags"], ["cp311-cp311-any"])
        self.assertEqual(len(report["build_dependencies"]), 5)
        self.assertEqual(len(calls), 6)
        runtime_calls = [call for call, _options in calls if "-c" in call]
        self.assertEqual(len(runtime_calls), 2)

    def test_build_and_run_rejects_missing_interpreter(self):
        with (
            mock.patch.object(integration.shutil, "which", return_value=None),
            self.assertRaisesRegex(ValueError, "interpreter not found"),
        ):
            integration.build_and_run("missing-python")

    def test_main_reports_built_wheel(self):
        argv = [
            "scikit_build_integration.py",
            "--python", "python",
            "--output", "report.json",
        ]
        report = {"wheel": {"name": "example.whl"}}
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                integration, "build_and_run", return_value=report) as build,
            mock.patch("builtins.print") as printed,
        ):
            integration.main()
        build.assert_called_once_with("python", Path("report.json"))
        printed.assert_called_once_with(
            "aHPy scikit-build-core integration passed: example.whl")


if __name__ == "__main__":
    unittest.main()
