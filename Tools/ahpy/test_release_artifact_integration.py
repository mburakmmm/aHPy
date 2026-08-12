import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import release_artifact_integration


class ReleaseArtifactDefinitionTest(unittest.TestCase):
    source_commit = "a" * 40
    required_members = (
        "PKG-INFO",
        ".gitrev",
        "setup.py",
        "pyproject.toml",
        "ahpy_version.py",
        "ahpy_build_backend.py",
        "ahpy_build_config.py",
        "ahpy_hpy_compat.py",
        "Cython/Compiler/RuntimeAPI.py",
        "Tools/ahpy/release_artifact_integration.py",
        "Tools/ahpy/release_evidence.py",
        "Tools/ahpy/benchmark_hpy.py",
        "Tools/ahpy/calibrate_performance_budgets.py",
        "tests/ahpy/benchmark_generated.pyx",
        "tests/ahpy/benchmark_reference.c",
        "tests/ahpy/benchmark_external.c",
        "tests/ahpy/benchmark_external.h",
        "tests/ahpy/performance-budgets.toml",
        "docs/ahpy/onboarding.md",
        "examples/ahpy_pep517/pyproject.toml",
        "pyximport/__init__.py",
        "LICENSE.txt",
        "CONTRIBUTING.md",
        "SECURITY.md",
    )

    def write_sdist(
            self, path, *, extra_members=(), metadata=None, revision=None):
        prefix = "ahpy_compiler-test"
        revision = self.source_commit if revision is None else revision
        if metadata is None:
            metadata = (
                "Metadata-Version: 2.4\n"
                "Name: %s\n"
                "Version: %s\n%s" % (
                    release_artifact_integration.AHPY_DISTRIBUTION,
                    release_artifact_integration.AHPY_VERSION,
                    "".join(
                        "Project-URL: %s, %s\n" % item
                        for item in
                        release_artifact_integration.provenance_project_urls(
                            self.source_commit).items()
                    ),
                )
            )
        with tarfile.open(path, "w:gz") as archive:
            for relative in self.required_members:
                if relative == "PKG-INFO":
                    payload = metadata
                elif relative == ".gitrev":
                    payload = revision + "\n"
                else:
                    payload = relative
                data = payload.encode("utf8")
                member = tarfile.TarInfo("%s/%s" % (prefix, relative))
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            for member, payload in extra_members:
                data = payload.encode("utf8")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))

    def test_gate_requires_clean_sdist_offline_venv_and_reinstall(self):
        source = Path(release_artifact_integration.__file__).read_text(
            encoding="utf8")
        self.assertIn('"--sdist", "--no-isolation"', source)
        self.assertIn('isolated["PIP_NO_INDEX"] = "1"', source)
        self.assertIn('python, "-m", "venv"', source)
        self.assertIn('"pip", "uninstall", "-y"', source)
        self.assertIn("_assert_frontend(clean_python, False, temp)", source)
        self.assertIn("_runtime_program(True)", source)
        self.assertIn('"setuptools==83.0.0"', source)
        self.assertIn('"build_dependencies"', source)
        self.assertIn('"schema_version": 2', source)
        self.assertIn("write_release_bundle(", source)
        self.assertIn('environment["SOURCE_DATE_EPOCH"]', source)
        self.assertIn('environment["PYTHONHASHSEED"] = "0"', source)
        dependency_materialization = source.split(
            'python, "-m", "pip", "wheel"', 1)[1].split(
                "], env=environment)", 1)[0]
        self.assertNotIn(
            "--no-build-isolation", dependency_materialization)

    def test_run_delegates_to_checked_subprocess(self):
        with patch.object(
                release_artifact_integration.subprocess, "run") as run:
            release_artifact_integration._run(
                ["python", "-V"], cwd=Path("/tmp"), env={"A": "1"})
        run.assert_called_once_with(
            ["python", "-V"], cwd=Path("/tmp"), env={"A": "1"}, check=True)

    def test_sdist_verifier_rejects_links_and_native_binaries(self):
        source = Path(release_artifact_integration.__file__).read_text(
            encoding="utf8")
        self.assertIn("member.issym() or member.islnk()", source)
        self.assertIn('".so", ".pyd", ".pyc"', source)
        self.assertIn('".." in path.parts', source)

    def test_sdist_verifier_accepts_expected_safe_archive(self):
        with TemporaryDirectory() as temp_dir:
            sdist = Path(temp_dir) / "valid.tar.gz"
            self.write_sdist(sdist)

            self.assertEqual(
                len(self.required_members),
                release_artifact_integration.verify_sdist(sdist),
            )

    def test_sdist_verifier_rejects_invalid_source_revision(self):
        with TemporaryDirectory() as temp_dir:
            sdist = Path(temp_dir) / "invalid-revision.tar.gz"
            self.write_sdist(sdist, revision="not-a-full-commit")
            with self.assertRaisesRegex(RuntimeError, "full lowercase Git"):
                release_artifact_integration.verify_sdist(sdist)

    def test_sdist_verifier_rejects_unsafe_or_binary_members(self):
        cases = (
            tarfile.TarInfo("../escape"),
            tarfile.TarInfo("ahpy_compiler-test/native.so"),
        )
        with TemporaryDirectory() as temp_dir:
            for index, member in enumerate(cases):
                with self.subTest(member=member.name):
                    sdist = Path(temp_dir) / ("unsafe-%d.tar.gz" % index)
                    self.write_sdist(sdist, extra_members=((member, "x"),))
                    with self.assertRaisesRegex(
                            AssertionError, "unsafe|forbidden"):
                        release_artifact_integration.verify_sdist(sdist)

    def test_sdist_verifier_rejects_links_and_wrong_identity(self):
        with TemporaryDirectory() as temp_dir:
            link_sdist = Path(temp_dir) / "link.tar.gz"
            link = tarfile.TarInfo("ahpy_compiler-test/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "LICENSE.txt"
            self.write_sdist(link_sdist, extra_members=((link, ""),))
            with self.assertRaisesRegex(AssertionError, "must not contain links"):
                release_artifact_integration.verify_sdist(link_sdist)

            identity_sdist = Path(temp_dir) / "identity.tar.gz"
            self.write_sdist(
                identity_sdist,
                metadata="Metadata-Version: 2.4\nName: Cython\nVersion: 0\n",
            )
            with self.assertRaisesRegex(AssertionError, "distribution name"):
                release_artifact_integration.verify_sdist(identity_sdist)

            version_sdist = Path(temp_dir) / "version.tar.gz"
            self.write_sdist(
                version_sdist,
                metadata=(
                    "Metadata-Version: 2.4\nName: %s\nVersion: 0\n" %
                    release_artifact_integration.AHPY_DISTRIBUTION
                ),
            )
            with self.assertRaisesRegex(AssertionError, "wrong version"):
                release_artifact_integration.verify_sdist(version_sdist)

            provenance_sdist = Path(temp_dir) / "provenance.tar.gz"
            self.write_sdist(
                provenance_sdist,
                metadata=(
                    "Metadata-Version: 2.4\nName: %s\nVersion: %s\n" % (
                        release_artifact_integration.AHPY_DISTRIBUTION,
                        release_artifact_integration.AHPY_VERSION,
                    )
                ),
            )
            with self.assertRaisesRegex(AssertionError, "exact provenance"):
                release_artifact_integration.verify_sdist(provenance_sdist)

    def test_sdist_verifier_rejects_missing_required_member(self):
        with TemporaryDirectory() as temp_dir:
            sdist = Path(temp_dir) / "missing.tar.gz"
            original = self.required_members
            try:
                self.required_members = original[:-1]
                self.write_sdist(sdist)
            finally:
                self.required_members = original
            with self.assertRaisesRegex(AssertionError, "lacks required member"):
                release_artifact_integration.verify_sdist(sdist)

    def test_venv_python_and_frontend_checks_are_root_isolated(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            relative = (Path("Scripts/python.exe") if os.name == "nt"
                        else Path("bin/python"))
            executable = root / relative
            executable.parent.mkdir(parents=True)
            executable.touch()
            self.assertEqual(
                str(executable),
                release_artifact_integration._venv_python(root),
            )

            clean_cwd = root / "clean-cwd"
            clean_cwd.mkdir()
            with patch.object(release_artifact_integration, "_run") as run:
                release_artifact_integration._assert_frontend(
                    str(executable), False, clean_cwd)
            command = run.call_args.args[0]
            self.assertEqual([str(executable), "-c"], command[:2])
            self.assertIn("aHPy compiler survived uninstall", command[2])
            self.assertEqual(clean_cwd, run.call_args.kwargs["cwd"])

            with patch.object(release_artifact_integration, "_run") as run:
                release_artifact_integration._assert_frontend(
                    str(executable), True, clean_cwd)
            command = run.call_args.args[0]
            self.assertIn("HPY_UNIVERSAL_BACKEND", command[2])
            self.assertIn("ahpy_build_backend, ahpy_build_config", command[2])
            self.assertIn("ahpy_hpy_compat", command[2])
            self.assertEqual(clean_cwd, run.call_args.kwargs["cwd"])

    def test_venv_python_rejects_incomplete_environment(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(AssertionError, "venv did not create"):
                release_artifact_integration._venv_python(temp_dir)

    def test_sha256_and_missing_interpreter_fail_closed(self):
        with TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "artifact"
            artifact.write_bytes(b"aHPy release artifact")
            self.assertEqual(
                hashlib.sha256(b"aHPy release artifact").hexdigest(),
                release_artifact_integration._sha256(artifact),
            )
        with patch.object(
                release_artifact_integration.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "interpreter not found"):
                release_artifact_integration.build_and_run("missing-python")

    def test_build_provenance_records_pinned_environment(self):
        selected = {
            "python": "3.11.15",
            "python_implementation": "CPython",
            "python_executable": "/tool/python",
            "platform": "reviewed-platform",
            "compiler": "reviewed-cc",
            "build_frontend_version": "1.3.0",
            "installed_hpy": (
                release_artifact_integration.AHPY_HPY_SUPPORTED_VERSION),
            "installed_setuptools": (
                release_artifact_integration.AHPY_SETUPTOOLS_VERSION),
        }
        completed = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(selected), stderr="")
        with (
            patch.object(
                release_artifact_integration.subprocess, "run",
                return_value=completed) as run,
            patch.object(
                release_artifact_integration, "source_commit",
                return_value=self.source_commit),
        ):
            provenance = release_artifact_integration._build_provenance(
                "/tool/python")
        run.assert_called_once()
        self.assertEqual(provenance["source_commit"], self.source_commit)
        self.assertEqual(
            provenance["cython_base_commit"],
            release_artifact_integration.CYTHON_BASE_COMMIT,
        )
        self.assertEqual(
            provenance["source_date_epoch"],
            int(release_artifact_integration.SOURCE_DATE_EPOCH),
        )
        self.assertEqual(provenance["build_frontend"], "build")

    def test_build_provenance_rejects_dependency_version_drift(self):
        selected = {
            "installed_hpy": "0.0",
            "installed_setuptools": (
                release_artifact_integration.AHPY_SETUPTOOLS_VERSION),
        }
        completed = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(selected), stderr="")
        with (
            patch.object(
                release_artifact_integration.subprocess, "run",
                return_value=completed),
            self.assertRaisesRegex(
                AssertionError, "release provenance requires installed_hpy"),
        ):
            release_artifact_integration._build_provenance("/tool/python")

    def test_build_and_run_rejects_nonempty_bundle_directory(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            python = root / "python"
            python.touch()
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "existing").touch()
            with self.assertRaisesRegex(
                    ValueError, "bundle directory must be empty"):
                release_artifact_integration.build_and_run(
                    str(python), bundle_dir=bundle)

    def test_build_and_run_rejects_release_artifact_cardinality_drift(self):
        cases = (
            ("sdist", "expected one clean aHPy sdist"),
            ("dependency-count", "expected exact HPy and setuptools wheels"),
            ("hpy", "lacks exact HPy"),
            ("setuptools", "lacks exact setuptools"),
            ("frontend", "expected one frontend wheel"),
            ("example", "onboarding did not produce"),
        )
        for failure, message in cases:
            def copy_frontend(destination):
                destination.mkdir()

            def fake_run(command, **options):
                if command[1:4] == ["-m", "build", "--sdist"]:
                    if failure != "sdist":
                        output = Path(command[command.index("--outdir") + 1])
                        (output / "ahpy_compiler-0.tar.gz").touch()
                    return
                if command[1:4] == ["-m", "pip", "wheel"]:
                    wheel_dir = Path(command[command.index("--wheel-dir") + 1])
                    if "hpy==0.9.0" in command:
                        names = {
                            "dependency-count": (
                                "hpy-0.9.0-py3-none-any.whl",
                            ),
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
                    elif str(command[-1]).endswith(".tar.gz"):
                        if failure != "frontend":
                            (wheel_dir / "ahpy_compiler-0-any.whl").touch()
                    return
                if command[1:3] == ["-m", "venv"]:
                    venv = Path(command[-1])
                    relative = (
                        Path("Scripts/python.exe")
                        if os.name == "nt" else Path("bin/python")
                    )
                    executable = venv / relative
                    executable.parent.mkdir(parents=True)
                    executable.touch()

            with self.subTest(failure=failure), TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                python = root / "python"
                python.touch()
                with (
                    patch.object(
                        release_artifact_integration, "_copy_frontend_source",
                        side_effect=copy_frontend,
                    ),
                    patch.object(
                        release_artifact_integration, "_run",
                        side_effect=fake_run,
                    ),
                    patch.object(
                        release_artifact_integration, "normalize_sdist",
                        side_effect=lambda path: path,
                    ),
                    patch.object(
                        release_artifact_integration, "verify_sdist",
                        return_value=1,
                    ),
                    patch.object(
                        release_artifact_integration, "_frontend_metadata"
                    ),
                    patch.object(
                        release_artifact_integration, "_assert_frontend"
                    ),
                    self.assertRaisesRegex(AssertionError, message),
                ):
                    release_artifact_integration.build_and_run(str(python))

    def test_build_and_run_proves_offline_reinstall_and_bundle(self):
        calls = []
        frontend_checks = []

        def copy_frontend(destination):
            destination.mkdir()

        def fake_run(command, **options):
            calls.append((command, options))
            if command[1:4] == ["-m", "build", "--sdist"]:
                output = Path(command[command.index("--outdir") + 1])
                (output / "ahpy_compiler-0.tar.gz").write_bytes(b"sdist")
                return
            if command[1:4] == ["-m", "pip", "wheel"]:
                wheel_dir = Path(command[command.index("--wheel-dir") + 1])
                if "hpy==0.9.0" in command:
                    for name in (
                            "hpy-0.9.0-py3-none-any.whl",
                            "setuptools-83.0.0-py3-none-any.whl"):
                        (wheel_dir / name).write_bytes(name.encode("ascii"))
                elif str(command[-1]).endswith(".tar.gz"):
                    (wheel_dir / "ahpy_compiler-0-py3-none-any.whl").write_bytes(
                        b"frontend")
                elif "onboarding-project" in str(command[-1]):
                    (
                        wheel_dir /
                        "ahpy_pep517_example-0-py3-none-any.whl"
                    ).write_bytes(b"example")
                return
            if command[1:3] == ["-m", "venv"]:
                venv = Path(command[-1])
                relative = (
                    Path("Scripts/python.exe")
                    if os.name == "nt"
                    else Path("bin/python")
                )
                executable = venv / relative
                executable.parent.mkdir(parents=True)
                executable.touch()

        def assert_frontend(python, present, cwd):
            frontend_checks.append((python, present, cwd))

        provenance = {
            "source_commit": self.source_commit,
            "cython_base_commit": (
                release_artifact_integration.CYTHON_BASE_COMMIT),
        }
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            python = root / "python"
            python.touch()
            output = root / "evidence" / "release.json"
            bundle = root / "bundle"
            with (
                patch.object(
                    release_artifact_integration, "_copy_frontend_source",
                    side_effect=copy_frontend),
                patch.object(
                    release_artifact_integration, "_run",
                    side_effect=fake_run),
                patch.object(
                    release_artifact_integration, "normalize_sdist",
                    side_effect=lambda path: path),
                patch.object(
                    release_artifact_integration, "verify_sdist",
                    return_value=25),
                patch.object(
                    release_artifact_integration, "_frontend_metadata"),
                patch.object(
                    release_artifact_integration, "_assert_frontend",
                    side_effect=assert_frontend),
                patch.object(
                    release_artifact_integration, "_build_provenance",
                    return_value=provenance),
                patch.object(
                    release_artifact_integration,
                    "write_release_bundle") as write_bundle,
                patch.dict(
                    release_artifact_integration.os.environ,
                    {"PYTHONPATH": "untrusted", "HPY": "trace"},
                    clear=True,
                ),
            ):
                report = release_artifact_integration.build_and_run(
                    str(python), output, bundle)
            self.assertEqual(json.loads(output.read_text()), report)

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["provenance"], provenance)
        self.assertEqual(report["sdist"]["members"], 25)
        self.assertTrue(report["offline_install"])
        self.assertTrue(report["frontend_uninstall_reinstall"])
        self.assertTrue(report["example_uninstall_reinstall"])
        self.assertEqual(
            report["runtime_modes"],
            ["normal", "debug", "normal-after-reinstall"],
        )
        self.assertEqual(len(report["build_dependencies"]), 2)
        self.assertEqual(
            [present for _, present, _ in frontend_checks],
            [True, False, True],
        )
        self.assertGreaterEqual(len(calls), 15)
        initial_environment = calls[0][1]["env"]
        self.assertNotIn("PYTHONPATH", initial_environment)
        self.assertNotIn("HPY", initial_environment)
        self.assertEqual(initial_environment["PYTHONHASHSEED"], "0")
        self.assertEqual(
            initial_environment["SOURCE_DATE_EPOCH"],
            release_artifact_integration.SOURCE_DATE_EPOCH,
        )
        isolated_environment = calls[2][1]["env"]
        self.assertEqual(isolated_environment["PIP_NO_INDEX"], "1")
        self.assertIn("wheelhouse", isolated_environment["PIP_FIND_LINKS"])
        write_bundle.assert_called_once()
        bundle_report = write_bundle.call_args.args[1]
        bundle_artifacts = write_bundle.call_args.args[2]
        self.assertIs(bundle_report, report)
        self.assertEqual(len(bundle_artifacts), 5)

    def test_cli_reports_the_validated_sdist(self):
        report = {"sdist": {"name": "ahpy_compiler-test.tar.gz"}}
        with patch.object(
                release_artifact_integration, "build_and_run",
                return_value=report) as build, patch.object(
                    sys, "argv", [
                        "release_artifact_integration.py",
                        "--python", "/chosen/python",
                        "--output", "/tmp/report.json",
                        "--bundle-dir", "/tmp/release-bundle",
                    ]), patch("builtins.print") as print_mock:
            release_artifact_integration.main()
        build.assert_called_once_with(
            "/chosen/python",
            Path("/tmp/report.json"),
            Path("/tmp/release-bundle"),
        )
        print_mock.assert_called_once_with(
            "aHPy clean release-artifact onboarding passed: %s" %
            report["sdist"]["name"])


if __name__ == "__main__":
    unittest.main()
