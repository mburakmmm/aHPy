import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

from ahpy_version import (
    AHPY_DISTRIBUTION,
    AHPY_VERSION,
    provenance_project_urls,
    source_commit,
)
import pep517_integration as integration
from pep517_integration import EXAMPLE, _copy_frontend_source, _frontend_metadata


HOOK_ENTRY_POINTS = (
    "[cython.runtime_backend_build_hooks]\n"
    "hpy-universal = "
    "ahpy_hpy_compat:install_hpy_universal_loader_compat\n"
)


class Pep517IntegrationDefinitionTest(unittest.TestCase):
    def test_example_pins_ahpy_frontend_not_upstream_cython(self):
        pyproject = (EXAMPLE / "pyproject.toml").read_text(encoding="utf8")
        setup = (EXAMPLE / "setup.py").read_text(encoding="utf8")
        self.assertIn(
            '"%s==%s"' % (AHPY_DISTRIBUTION, AHPY_VERSION), pyproject)
        self.assertNotIn('"aHPy==', pyproject)
        self.assertNotIn('"Cython', pyproject)
        self.assertIn('build-backend = "ahpy_build_backend"', pyproject)
        self.assertIn('runtime_backend="hpy-universal"', setup)
        self.assertIn("hpy_ext_modules=extensions", setup)
        integration = Path(__file__).with_name(
            "pep517_integration.py").read_text(encoding="utf8")
        self.assertIn('isolated_environment["PIP_NO_INDEX"] = "1"', integration)
        self.assertIn('"hpy==0.9.0", "setuptools==83.0.0"', integration)
        dependency_materialization = integration.split(
            '"hpy==0.9.0"', 1)[0].rsplit("[", 1)[-1]
        self.assertNotIn("--no-build-isolation", dependency_materialization)

    def test_clean_frontend_source_is_self_contained_and_excludes_junk(self):
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "frontend"
            _copy_frontend_source(destination)
            for relative in (
                "pyproject.toml",
                ".gitrev",
                "ahpy_build_backend.py",
                "ahpy_build_config.py",
                "ahpy_hpy_compat.py",
                "Cython/Compiler/RuntimeAPI.py",
                "Tools/ahpy/release_artifact_integration.py",
                "tests/ahpy/requirements-hpy09.txt",
                "docs/ahpy/onboarding.md",
                "examples/ahpy_pep517/pyproject.toml",
                "CONTRIBUTING.md",
                "SECURITY.md",
            ):
                self.assertTrue((destination / relative).is_file(), relative)
            self.assertFalse(any(
                path.name == ".DS_Store" or path.suffix in {".pyc", ".so", ".pyd"}
                for path in destination.rglob("*")
            ))

    def test_frontend_wheel_metadata_and_required_modules(self):
        with TemporaryDirectory() as temp_dir:
            wheel = Path(temp_dir) / "frontend.whl"
            metadata = (
                "Metadata-Version: 2.4\nName: %s\nVersion: %s\n%s" %
                (
                    AHPY_DISTRIBUTION,
                    AHPY_VERSION,
                    "".join(
                        "Project-URL: %s, %s\n" % item
                        for item in provenance_project_urls(
                            source_commit()).items()
                    ),
                )
            )
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
                archive.writestr(
                    "ahpy_compiler.dist-info/entry_points.txt",
                    HOOK_ENTRY_POINTS,
                )
                archive.writestr("ahpy_build_backend.py", "")
                archive.writestr("ahpy_build_config.py", "")
                archive.writestr("ahpy_hpy_compat.py", "")
                archive.writestr("ahpy_version.py", "")
                archive.writestr("Cython/__init__.py", "")
            _frontend_metadata(wheel)

            wrong = Path(temp_dir) / "wrong.whl"
            with zipfile.ZipFile(wrong, "w") as archive:
                archive.writestr(
                    "wrong.dist-info/METADATA",
                    "Metadata-Version: 2.4\nName: Cython\nVersion: 0\n",
                )
                archive.writestr(
                    "wrong.dist-info/entry_points.txt", HOOK_ENTRY_POINTS)
            with self.assertRaisesRegex(AssertionError, "not the aHPy"):
                _frontend_metadata(wrong)

            incomplete = Path(temp_dir) / "incomplete.whl"
            with zipfile.ZipFile(incomplete, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
                archive.writestr(
                    "ahpy_compiler.dist-info/entry_points.txt",
                    HOOK_ENTRY_POINTS,
                )
            with self.assertRaisesRegex(AssertionError, "missing ahpy_build"):
                _frontend_metadata(incomplete)

            no_cython = Path(temp_dir) / "no-cython.whl"
            with zipfile.ZipFile(no_cython, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
                archive.writestr(
                    "ahpy_compiler.dist-info/entry_points.txt",
                    HOOK_ENTRY_POINTS,
                )
                archive.writestr("ahpy_build_backend.py", "")
                archive.writestr("ahpy_build_config.py", "")
                archive.writestr("ahpy_hpy_compat.py", "")
                archive.writestr("ahpy_version.py", "")
            with self.assertRaisesRegex(AssertionError, "missing the Cython"):
                _frontend_metadata(no_cython)

            no_hook = Path(temp_dir) / "no-hook.whl"
            with zipfile.ZipFile(no_hook, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
                archive.writestr(
                    "ahpy_compiler.dist-info/entry_points.txt",
                    "[console_scripts]\ncython = Cython.Compiler.Main:main\n",
                )
                archive.writestr("ahpy_build_backend.py", "")
                archive.writestr("ahpy_build_config.py", "")
                archive.writestr("ahpy_hpy_compat.py", "")
                archive.writestr("ahpy_version.py", "")
                archive.writestr("Cython/__init__.py", "")
            with self.assertRaisesRegex(AssertionError, "build hook"):
                _frontend_metadata(no_hook)

            no_entry_points = Path(temp_dir) / "no-entry-points.whl"
            with zipfile.ZipFile(no_entry_points, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
            with self.assertRaisesRegex(AssertionError, "one entry_points"):
                _frontend_metadata(no_entry_points)

    def test_frontend_wheel_metadata_rejects_version_and_provenance_drift(self):
        commit = "1" * 40
        base_metadata = (
            "Metadata-Version: 2.4\nName: %s\nVersion: %s\n%s" %
            (
                AHPY_DISTRIBUTION,
                AHPY_VERSION,
                "".join(
                    "Project-URL: %s, %s\n" % item
                    for item in provenance_project_urls(commit).items()
                ),
            )
        )
        required = (
            "ahpy_build_backend.py",
            "ahpy_build_config.py",
            "ahpy_hpy_compat.py",
            "ahpy_version.py",
            "Cython/__init__.py",
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name, metadata, message in (
                (
                    "wrong-version.whl",
                    base_metadata.replace(
                        "Version: %s" % AHPY_VERSION, "Version: 0"),
                    "wrong aHPy version",
                ),
                (
                    "wrong-provenance.whl",
                    base_metadata.replace(
                        next(iter(provenance_project_urls(commit).values())),
                        "https://example.invalid/drift",
                    ),
                    "lacks exact provenance",
                ),
            ):
                wheel = root / name
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr(
                        "ahpy_compiler.dist-info/METADATA", metadata)
                    archive.writestr(
                        "ahpy_compiler.dist-info/entry_points.txt",
                        HOOK_ENTRY_POINTS,
                    )
                    for member in required:
                        archive.writestr(member, "")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(AssertionError, message):
                        _frontend_metadata(wheel, expected_commit=commit)

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
            if command[1:4] != ["-m", "pip", "wheel"]:
                return
            wheel_dir = Path(command[command.index("--wheel-dir") + 1])
            if any("frontend-source" in argument for argument in command):
                (wheel_dir / "ahpy_compiler-0-py3-none-any.whl").write_bytes(
                    b"frontend")
            elif "hpy==0.9.0" in command:
                for name in (
                        "hpy-0.9.0-py3-none-any.whl",
                        "setuptools-83.0.0-py3-none-any.whl"):
                    (wheel_dir / name).write_bytes(name.encode("ascii"))
            else:
                project = Path(command[-1])
                (project / "ahpy_pep517_example.c").write_text(
                    "generated Universal C\n", encoding="utf8")
                wheel = (
                    wheel_dir /
                    "ahpy_pep517_example-0-cp311-cp311-any.whl"
                )
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr(
                        "ahpy_pep517_example.hpy0.so", b"binary")
                    archive.writestr(
                        "ahpy_pep517_example.py", "# loader\n")
                    archive.writestr(
                        "ahpy_pep517_example-0.dist-info/WHEEL",
                        "Wheel-Version: 1.0\n"
                        "Tag: cp311-cp311-any\n",
                    )

        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            output = Path(temp_dir) / "evidence" / "pep517.json"
            with (
                mock.patch.object(
                    integration, "_copy_frontend_source",
                    side_effect=copy_frontend,
                ),
                mock.patch.object(integration, "run", side_effect=fake_run),
                mock.patch.object(integration, "_frontend_metadata"),
                mock.patch.object(integration, "verify_binary_boundary"),
                mock.patch.object(integration, "verify_source_boundary"),
                mock.patch.dict(
                    integration.os.environ,
                    {"PYTHONPATH": "untrusted", "HPY": "trace"},
                    clear=True,
                ),
            ):
                report = integration.build_and_run(str(python), output)
            self.assertEqual(json.loads(output.read_text()), report)

        self.assertEqual(report["schema_version"], 1)
        self.assertTrue(report["build_isolation"])
        self.assertEqual(report["runtime_modes"], ["normal", "debug"])
        self.assertEqual(
            report["example_wheel"]["hpy_binary"],
            "ahpy_pep517_example.hpy0.so",
        )
        self.assertEqual(
            report["example_wheel"]["tags"], ["cp311-cp311-any"])
        self.assertEqual(len(report["build_dependencies"]), 2)
        self.assertEqual(len(calls), 6)
        first_environment = calls[0][1]["env"]
        self.assertNotIn("PYTHONPATH", first_environment)
        self.assertNotIn("HPY", first_environment)
        self.assertEqual(first_environment["NO_CYTHON_COMPILE"], "true")
        isolated_environment = calls[2][1]["env"]
        self.assertNotIn("NO_CYTHON_COMPILE", isolated_environment)
        self.assertEqual(isolated_environment["PIP_NO_INDEX"], "1")
        self.assertIn("wheelhouse", isolated_environment["PIP_FIND_LINKS"])
        runtime_calls = [call for call, _ in calls if "-c" in call]
        self.assertEqual(len(runtime_calls), 2)
        self.assertNotIn("HPY", calls[4][1]["env"])
        self.assertEqual(calls[5][1]["env"]["HPY"], "debug")

    def test_build_and_run_rejects_missing_interpreter(self):
        with (
            mock.patch.object(integration.shutil, "which", return_value=None),
            self.assertRaisesRegex(ValueError, "interpreter not found"),
        ):
            integration.build_and_run("missing-python")

    def test_build_and_run_rejects_dependency_wheel_drift(self):
        def copy_frontend(destination):
            destination.mkdir()

        def fake_run(command, **options):
            if command[1:4] != ["-m", "pip", "wheel"]:
                return
            wheel_dir = Path(command[command.index("--wheel-dir") + 1])
            if any("frontend-source" in argument for argument in command):
                (wheel_dir / "ahpy_compiler-0-py3-none-any.whl").write_bytes(
                    b"frontend")
            elif "hpy==0.9.0" in command:
                (wheel_dir / "hpy-0.9.0-py3-none-any.whl").write_bytes(b"hpy")

        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            with (
                mock.patch.object(
                    integration, "_copy_frontend_source",
                    side_effect=copy_frontend),
                mock.patch.object(integration, "run", side_effect=fake_run),
                mock.patch.object(integration, "_frontend_metadata"),
                self.assertRaisesRegex(
                    AssertionError, "exactly HPy and setuptools"),
            ):
                integration.build_and_run(str(python))

    def test_build_and_run_rejects_frontend_and_example_artifact_drift(self):
        cases = (
            ("frontend", "expected one aHPy frontend wheel"),
            ("hpy", "lacks exact HPy"),
            ("setuptools", "lacks exact setuptools"),
            ("example", "expected one PEP 517 example wheel"),
            ("members", "lacks .hpy0 binary/stub"),
        )
        for failure, message in cases:
            def copy_frontend(destination):
                destination.mkdir()

            def fake_run(command, **options):
                if command[1:4] != ["-m", "pip", "wheel"]:
                    return
                wheel_dir = Path(command[command.index("--wheel-dir") + 1])
                if any("frontend-source" in argument for argument in command):
                    if failure != "frontend":
                        (wheel_dir / "ahpy_compiler-0-py3-none-any.whl").touch()
                    return
                if "hpy==0.9.0" in command:
                    names = {
                        "hpy": (
                            "setuptools-83.0.0-py3-none-any.whl",
                            "unrelated-1-py3-none-any.whl",
                        ),
                        "setuptools": (
                            "hpy-0.9.0-py3-none-any.whl",
                            "unrelated-1-py3-none-any.whl",
                        ),
                    }.get(failure, (
                        "hpy-0.9.0-py3-none-any.whl",
                        "setuptools-83.0.0-py3-none-any.whl",
                    ))
                    for name in names:
                        (wheel_dir / name).touch()
                    return
                if failure == "example":
                    return
                wheel = wheel_dir / "ahpy_pep517_example-0-any.whl"
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr("ahpy_pep517_example.hpy0.so", b"binary")
                    archive.writestr(
                        "ahpy_pep517_example-0.dist-info/WHEEL",
                        "Wheel-Version: 1.0\nTag: py3-none-any\n",
                    )

            with self.subTest(failure=failure), TemporaryDirectory() as temp_dir:
                python = Path(temp_dir) / "python"
                python.touch()
                with (
                    mock.patch.object(
                        integration, "_copy_frontend_source",
                        side_effect=copy_frontend,
                    ),
                    mock.patch.object(integration, "run", side_effect=fake_run),
                    mock.patch.object(integration, "_frontend_metadata"),
                    self.assertRaisesRegex(AssertionError, message),
                ):
                    integration.build_and_run(str(python))

    def test_main_reports_built_wheel(self):
        argv = [
            "pep517_integration.py",
            "--python", "python",
            "--output", "report.json",
        ]
        report = {"example_wheel": {"name": "example.whl"}}
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                integration, "build_and_run", return_value=report) as build,
            mock.patch("builtins.print") as printed,
        ):
            integration.main()
        build.assert_called_once_with("python", Path("report.json"))
        printed.assert_called_once_with(
            "aHPy isolated PEP 517 build passed: example.whl")


if __name__ == "__main__":
    unittest.main()
