import hashlib
import io
import os
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import release_artifact_integration


class ReleaseArtifactDefinitionTest(unittest.TestCase):
    required_members = (
        "PKG-INFO",
        "setup.py",
        "pyproject.toml",
        "ahpy_version.py",
        "ahpy_build_backend.py",
        "ahpy_build_config.py",
        "Cython/Compiler/RuntimeAPI.py",
        "Tools/ahpy/release_artifact_integration.py",
        "Tools/ahpy/benchmark_hpy.py",
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

    def write_sdist(self, path, *, extra_members=(), metadata=None):
        prefix = "ahpy_compiler-test"
        if metadata is None:
            metadata = (
                "Metadata-Version: 2.4\n"
                "Name: %s\n"
                "Version: %s\n" % (
                    release_artifact_integration.AHPY_DISTRIBUTION,
                    release_artifact_integration.AHPY_VERSION,
                )
            )
        with tarfile.open(path, "w:gz") as archive:
            for relative in self.required_members:
                payload = metadata if relative == "PKG-INFO" else relative
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
        self.assertIn('"setuptools==80.9.0"', source)
        self.assertIn('"build_dependencies"', source)
        self.assertIn('environment["SOURCE_DATE_EPOCH"]', source)
        self.assertIn('environment["PYTHONHASHSEED"] = "0"', source)

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

    def test_cli_reports_the_validated_sdist(self):
        report = {"sdist": {"name": "ahpy_compiler-test.tar.gz"}}
        with patch.object(
                release_artifact_integration, "build_and_run",
                return_value=report) as build, patch.object(
                    sys, "argv", [
                        "release_artifact_integration.py",
                        "--python", "/chosen/python",
                        "--output", "/tmp/report.json",
                    ]), patch("builtins.print") as print_mock:
            release_artifact_integration.main()
        build.assert_called_once_with(
            "/chosen/python", Path("/tmp/report.json"))
        print_mock.assert_called_once_with(
            "aHPy clean release-artifact onboarding passed: %s" %
            report["sdist"]["name"])


if __name__ == "__main__":
    unittest.main()
