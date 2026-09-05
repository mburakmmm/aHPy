from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import report_nightly_environment


class _Distribution:
    def __init__(self, version="0.9.0", direct_url=None):
        self.version = version
        self.direct_url = direct_url

    def read_text(self, name):
        if name != "direct_url.json" or self.direct_url is None:
            return None
        return json.dumps(self.direct_url)


class NightlyEnvironmentReportTest(unittest.TestCase):
    def test_branch_tip_requires_and_records_full_resolved_commit(self):
        commit = "a" * 40
        distribution = _Distribution(
            "0.9.1.dev200",
            {"url": "https://github.com/hpyproject/hpy.git",
             "vcs_info": {"vcs": "git", "requested_revision": "master",
                          "commit_id": commit}},
        )
        report = report_nightly_environment.collect_environment(
            "hpy", "3.11", require_hpy_vcs=True,
            expected_hpy_url="https://github.com/hpyproject/hpy.git",
            expected_hpy_ref="master", distribution=distribution,
            repository_commit="b" * 40, python_version="3.11.15")
        self.assertEqual(report["hpy"]["vcs_commit"], commit)
        self.assertEqual(report["support_status"],
                         "allowed-failure-early-warning")

    def test_branch_tip_rejects_missing_or_short_commit(self):
        for direct_url in (None, {"vcs_info": {"commit_id": "abc"}}):
            with self.subTest(direct_url=direct_url):
                with self.assertRaisesRegex(ValueError, "full VCS commit"):
                    report_nightly_environment.collect_environment(
                        "hpy", "3.11", require_hpy_vcs=True,
                        expected_hpy_url="https://github.com/hpyproject/hpy.git",
                        expected_hpy_ref="master",
                        distribution=_Distribution(direct_url=direct_url),
                        repository_commit="b" * 40, python_version="3.11.15")

    def test_release_lane_allows_absent_direct_url(self):
        report = report_nightly_environment.collect_environment(
            "interpreter", "3.15-dev", distribution=_Distribution(),
            repository_commit="c" * 40, python_version="3.15.0b1")
        self.assertIsNone(report["hpy"]["direct_url"])
        self.assertIsNone(report["hpy"]["vcs_commit"])

    def test_invalid_direct_url_json_is_rejected(self):
        distribution = _Distribution()
        distribution.read_text = lambda name: "not-json"
        with self.assertRaisesRegex(ValueError, "direct_url.json is invalid"):
            report_nightly_environment.collect_environment(
                "interpreter", "3.15-dev", distribution=distribution,
                repository_commit="d" * 40, python_version="3.15.0b1")

    def test_direct_url_and_vcs_metadata_require_expected_shapes(self):
        distribution = _Distribution()
        distribution.read_text = lambda name: "[]"
        with self.assertRaisesRegex(ValueError, "must be an object"):
            report_nightly_environment._distribution_direct_url(distribution)
        self.assertIsNone(
            report_nightly_environment._vcs_commit({"vcs_info": "invalid"}))
        self.assertIsNone(report_nightly_environment._vcs_commit({
            "vcs_info": {"commit_id": 123},
        }))

    def test_repository_commit_is_checked_and_must_be_full(self):
        with mock.patch.object(
                report_nightly_environment.subprocess, "run",
                return_value=mock.Mock(stdout="a" * 40 + "\n")) as run:
            self.assertEqual(
                report_nightly_environment._repository_commit(Path("/repo")),
                "a" * 40,
            )
        run.assert_called_once_with(
            ["git", "rev-parse", "HEAD"], cwd=Path("/repo"),
            check=True, capture_output=True, text=True)
        with (
            mock.patch.object(
                report_nightly_environment.subprocess, "run",
                return_value=mock.Mock(stdout="short\n")),
            self.assertRaisesRegex(ValueError, "full Git commit"),
        ):
            report_nightly_environment._repository_commit(Path("/repo"))

    def test_requested_interpreter_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match requested"):
            report_nightly_environment.collect_environment(
                "interpreter", "3.15-dev", distribution=_Distribution(),
                repository_commit="e" * 40, python_version="3.14.6")

    def test_requested_interpreter_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must use X.Y"):
            report_nightly_environment._validate_requested_python(
                "latest", "3.15.0")

    def test_branch_tip_rejects_wrong_repository_or_ref(self):
        direct_url = {
            "url": "https://example.invalid/fork.git",
            "vcs_info": {
                "requested_revision": "other",
                "commit_id": "a" * 40,
            },
        }
        with self.assertRaisesRegex(ValueError, "URL"):
            report_nightly_environment.collect_environment(
                "hpy", "3.11", require_hpy_vcs=True,
                expected_hpy_url="https://github.com/hpyproject/hpy.git",
                expected_hpy_ref="master",
                distribution=_Distribution(direct_url=direct_url),
                repository_commit="f" * 40, python_version="3.11.15")

        correct_url = {
            "url": "https://github.com/hpyproject/hpy.git",
            "vcs_info": {
                "requested_revision": "other",
                "commit_id": "a" * 40,
            },
        }
        with self.assertRaisesRegex(ValueError, "ref"):
            report_nightly_environment.collect_environment(
                "hpy", "3.11", require_hpy_vcs=True,
                expected_hpy_url="https://github.com/hpyproject/hpy.git",
                expected_hpy_ref="master",
                distribution=_Distribution(direct_url=correct_url),
                repository_commit="f" * 40, python_version="3.11.15")

    def test_collection_validates_lane_source_contract_and_default_providers(self):
        with self.assertRaisesRegex(ValueError, "lane must be"):
            report_nightly_environment.collect_environment(
                "unknown", "3.11", distribution=_Distribution(),
                repository_commit="a" * 40, python_version="3.11.15")

        direct_url = {
            "url": "https://github.com/hpyproject/hpy.git",
            "vcs_info": {
                "requested_revision": "master",
                "commit_id": "a" * 40,
            },
        }
        with self.assertRaisesRegex(ValueError, "requires expected URL and ref"):
            report_nightly_environment.collect_environment(
                "hpy", "3.11", require_hpy_vcs=True,
                distribution=_Distribution(direct_url=direct_url),
                repository_commit="b" * 40, python_version="3.11.15")

        distribution = _Distribution("0.9.0")
        with (
            mock.patch.object(
                report_nightly_environment.importlib.metadata,
                "distribution", return_value=distribution) as selected,
            mock.patch.object(
                report_nightly_environment, "_repository_commit",
                return_value="c" * 40) as repository,
        ):
            report = report_nightly_environment.collect_environment(
                "interpreter", "3.11", python_version="3.11.15")
        selected.assert_called_once_with("hpy")
        repository.assert_called_once_with()
        self.assertEqual(report["ahpy"]["commit"], "c" * 40)
        self.assertEqual(report["hpy"]["version"], "0.9.0")

    def test_write_report_creates_parent_and_canonical_json(self):
        report = {"schema_version": 1, "lane": "interpreter"}
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "report.json"
            report_nightly_environment.write_report(report, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf8")), report)
            self.assertTrue(output.read_text(encoding="utf8").endswith("\n"))

    def test_main_writes_selected_lane_and_reports_validation_errors(self):
        report = {
            "lane": "interpreter",
            "python": {"version": "3.15.0b1"},
            "hpy": {"version": "0.9.0", "vcs_commit": None},
        }
        argv = [
            "report_nightly_environment.py",
            "--lane", "interpreter",
            "--requested-python", "3.15-dev",
            "--output", "nightly.json",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                report_nightly_environment, "collect_environment",
                return_value=report) as collect,
            mock.patch.object(
                report_nightly_environment, "write_report") as write,
            mock.patch("builtins.print") as printed,
        ):
            report_nightly_environment.main()
        collect.assert_called_once_with(
            "interpreter", "3.15-dev", require_hpy_vcs=False,
            expected_hpy_url=None, expected_hpy_ref=None)
        write.assert_called_once_with(report, Path("nightly.json"))
        self.assertIn("commit=release", printed.call_args.args[0])

        for error in (
                ValueError("invalid nightly evidence"),
                subprocess.CalledProcessError(1, ["git"]),
                report_nightly_environment.importlib.metadata.PackageNotFoundError(
                    "hpy")):
            with (
                self.subTest(error=type(error).__name__),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    report_nightly_environment, "collect_environment",
                    side_effect=error),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                report_nightly_environment.main()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
