import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import release_recovery_drill as drill
from maintenance_policy import load_policy


class ReleaseRecoveryDrillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy()

    def test_real_drill_cherry_picks_test_without_expanding_support(self):
        report = drill.run_drill()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["category"], "correctness")
        self.assertEqual(report["release_branch"], "ahpy/3.2")
        self.assertEqual(report["topic_branch"], "codex/backport-correctness")
        self.assertTrue(report["source_commit_named"])
        self.assertEqual(report["changed_paths"], list(drill.CHANGED_PATHS))
        self.assertTrue(report["support_contract_unchanged"])
        self.assertEqual(report["recovery"], self.policy["recovery"])

    def test_report_validation_fails_closed_on_policy_drift(self):
        valid = drill.run_drill()
        mutations = []
        data = copy.deepcopy(valid)
        data.pop("status")
        mutations.append((data, "keys mismatch"))
        for field, value, message in (
                ("schema_version", 2, "schema mismatch"),
                ("status", "partial", "did not pass"),
                ("generated_at", "not-a-time", "generated_at is invalid"),
                ("generated_at", "2026-08-12", "needs a timezone"),
                ("source_commit", "short", "exact commit"),
                ("category", "feature", "not backportable"),
                ("release_branch", "release/3.2", "branch does not match"),
                ("topic_branch", "other/backport", "topic branch"),
                ("source_commit_named", False, "name its source"),
                ("regression_test", "tests/other.txt", "original regression"),
                ("support_contract_unchanged", False, "expand the support"),
                ("direct_push", True, "reviewed topic branch"),
                ("mandatory_matrix_required", False, "mandatory matrix")):
            data = copy.deepcopy(valid)
            data[field] = value
            mutations.append((data, message))
        data = copy.deepcopy(valid)
        data["recovery"]["standard_defect_action"] = "delete"
        mutations.append((data, "drifted"))
        for data, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(
                    drill.ReleaseRecoveryError, message):
                drill.validate_report(data, self.policy)

    def test_explicit_work_root_and_cli_outputs_are_reproducible_records(self):
        with TemporaryDirectory(prefix="ahpy-release-drill-test-") as temp_dir:
            root = Path(temp_dir)
            work = root / "work"
            report = drill.run_drill(work)
            self.assertTrue((work / "repository" / ".git").is_dir())
            drill.validate_report(report, self.policy)

            output = root / "nested" / "report.json"
            stdout = io.StringIO()
            with mock.patch.object(
                    drill, "run_drill", return_value=report), \
                    contextlib.redirect_stdout(stdout):
                self.assertEqual(drill.main([]), 0)
            self.assertEqual(json.loads(stdout.getvalue()), report)
            with mock.patch.object(drill, "run_drill", return_value=report):
                self.assertEqual(drill.main(["--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text()), report)

    def test_nonempty_root_missing_git_and_command_failure_are_actionable(self):
        with TemporaryDirectory(prefix="ahpy-release-drill-errors-") as temp_dir:
            root = Path(temp_dir)
            (root / "occupied").touch()
            with self.assertRaisesRegex(
                    drill.ReleaseRecoveryError, "must be empty"):
                drill.run_drill(root)
        with mock.patch.object(drill.shutil, "which", return_value=None):
            with self.assertRaisesRegex(
                    drill.ReleaseRecoveryError, "git executable"):
                drill.run_drill()

        for result, detail in (
                (SimpleNamespace(returncode=3, stdout="", stderr="failure"),
                 "failure"),
                (SimpleNamespace(returncode=4, stdout="stdout", stderr=""),
                 "stdout"),
                (SimpleNamespace(returncode=5, stdout="", stderr=""),
                 "no output")):
            with self.subTest(detail=detail), mock.patch.object(
                    drill.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(
                        drill.ReleaseRecoveryError, detail):
                    drill._run(["git", "status"], Path("/tmp"))

    def test_cli_reports_drill_errors(self):
        with mock.patch.object(
                drill, "run_drill",
                side_effect=drill.ReleaseRecoveryError("unsafe drill")), \
                mock.patch.object(drill.sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                drill.main([])


if __name__ == "__main__":
    unittest.main()
