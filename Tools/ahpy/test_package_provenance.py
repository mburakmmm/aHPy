from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ahpy_version import (
    AHPY_BUILD_FRONTEND_VERSION,
    AHPY_HPY_SUPPORTED_VERSION,
    CYTHON_BASE_COMMIT,
    provenance_project_urls,
    source_commit,
    validate_source_commit,
)


class PackageProvenanceTest(unittest.TestCase):
    def test_release_build_frontend_pin_matches_requirement(self):
        requirements = Path(
            "tests/ahpy/requirements-build-systems.txt"
        ).read_text(encoding="utf8").splitlines()
        self.assertIn(
            "build==%s" % AHPY_BUILD_FRONTEND_VERSION, requirements)

    def test_archive_revision_is_used_without_git_checkout(self):
        commit = "a" * 40
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".gitrev").write_text(
                commit + "\n", encoding="ascii")
            self.assertEqual(source_commit(temp_dir), commit)

    def test_git_checkout_ignores_stale_archive_revision(self):
        commit = "b" * 40
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.joinpath(".git").mkdir()
            root.joinpath(".gitrev").write_text(
                "a" * 40 + "\n", encoding="ascii")
            completed = subprocess.CompletedProcess(
                args=["git"], returncode=0, stdout=commit + "\n", stderr="")
            with patch("ahpy_version.subprocess.run", return_value=completed):
                self.assertEqual(source_commit(root), commit)

    def test_missing_archive_and_unreadable_git_head_fail_closed(self):
        with TemporaryDirectory() as temp_dir:
            completed = subprocess.CompletedProcess(
                args=["git"], returncode=128, stdout="", stderr="not a repo")
            with patch("ahpy_version.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "neither .gitrev"):
                    source_commit(temp_dir)

    def test_invalid_revision_fails_closed(self):
        for commit in ("", "abc", "A" * 40, "g" * 40):
            with self.subTest(commit=commit):
                with self.assertRaisesRegex(
                        RuntimeError, "full lowercase Git commit"):
                    validate_source_commit(commit)

    def test_standard_metadata_urls_freeze_all_compatibility_inputs(self):
        commit = "b" * 40
        urls = provenance_project_urls(commit)
        self.assertEqual(
            urls["aHPy source commit"],
            "https://github.com/mburakmmm/aHPy/commit/%s" % commit,
        )
        self.assertTrue(
            urls["Cython base commit"].endswith(CYTHON_BASE_COMMIT))
        self.assertIn(
            "HPy %s compatibility" % AHPY_HPY_SUPPORTED_VERSION, urls)
        self.assertIn("/blob/%s/" % commit, next(
            url for label, url in urls.items() if label.startswith("HPy ")))


if __name__ == "__main__":
    unittest.main()
