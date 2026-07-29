from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from ahpy_version import (
    AHPY_DISTRIBUTION,
    AHPY_VERSION,
    provenance_project_urls,
    source_commit,
)
from pep517_integration import EXAMPLE, _copy_frontend_source, _frontend_metadata


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
        self.assertIn('"hpy==0.9.0", "setuptools==80.9.0"', integration)
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
                archive.writestr("ahpy_build_backend.py", "")
                archive.writestr("ahpy_build_config.py", "")
                archive.writestr("ahpy_version.py", "")
                archive.writestr("Cython/__init__.py", "")
            _frontend_metadata(wheel)

            wrong = Path(temp_dir) / "wrong.whl"
            with zipfile.ZipFile(wrong, "w") as archive:
                archive.writestr(
                    "wrong.dist-info/METADATA",
                    "Metadata-Version: 2.4\nName: Cython\nVersion: 0\n",
                )
            with self.assertRaisesRegex(AssertionError, "not the aHPy"):
                _frontend_metadata(wrong)

            incomplete = Path(temp_dir) / "incomplete.whl"
            with zipfile.ZipFile(incomplete, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
            with self.assertRaisesRegex(AssertionError, "missing ahpy_build"):
                _frontend_metadata(incomplete)

            no_cython = Path(temp_dir) / "no-cython.whl"
            with zipfile.ZipFile(no_cython, "w") as archive:
                archive.writestr(
                    "ahpy_compiler.dist-info/METADATA", metadata)
                archive.writestr("ahpy_build_backend.py", "")
                archive.writestr("ahpy_build_config.py", "")
                archive.writestr("ahpy_version.py", "")
            with self.assertRaisesRegex(AssertionError, "missing the Cython"):
                _frontend_metadata(no_cython)


if __name__ == "__main__":
    unittest.main()
