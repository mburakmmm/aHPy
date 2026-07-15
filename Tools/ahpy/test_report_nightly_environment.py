from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

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

    def test_requested_interpreter_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match requested"):
            report_nightly_environment.collect_environment(
                "interpreter", "3.15-dev", distribution=_Distribution(),
                repository_commit="e" * 40, python_version="3.14.6")

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

    def test_write_report_creates_parent_and_canonical_json(self):
        report = {"schema_version": 1, "lane": "interpreter"}
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "report.json"
            report_nightly_environment.write_report(report, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf8")), report)
            self.assertTrue(output.read_text(encoding="utf8").endswith("\n"))


if __name__ == "__main__":
    unittest.main()
