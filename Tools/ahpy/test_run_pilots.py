import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import run_pilots
from pilot_matrix import load_manifest
from run_pilots import PilotRunError


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "tests" / "ahpy" / "pilots.toml"


class RunPilotsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest(MANIFEST_PATH)
        cls.pilot = cls.manifest.pilots[0]

    def _checkout(self, root, pilot=None):
        pilot = pilot or self.pilot
        checkout = root / pilot.id
        (checkout / ".git").mkdir(parents=True)
        for path in (pilot.license_file, *pilot.source_paths):
            target = checkout / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture\n", encoding="utf8")
        return checkout

    def test_run_reports_command_failures_with_stderr_or_stdout(self):
        failed = mock.Mock(returncode=3, stdout="stdout detail", stderr="")
        with mock.patch.object(run_pilots.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(PilotRunError, "stdout detail"):
                run_pilots._run(["git", "status"])
        failed.stderr = "stderr detail"
        with mock.patch.object(run_pilots.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(PilotRunError, "stderr detail"):
                run_pilots._run(["git", "status"])
        passed = mock.Mock(returncode=0, stdout="  success output  ", stderr="")
        with mock.patch.object(run_pilots.subprocess, "run", return_value=passed):
            self.assertEqual(run_pilots._run(["git", "status"]), "success output")
        with mock.patch.object(run_pilots, "_run", return_value="head") as run:
            self.assertEqual(run_pilots._git("/checkout", "rev-parse", "HEAD"),
                             "head")
        run.assert_called_once_with(
            ["git", "-C", "/checkout", "rev-parse", "HEAD"])

    def test_verify_checkout_records_exact_clean_provenance(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-checkout-") as temp:
            checkout = self._checkout(Path(temp))
            answers = [self.pilot.commit, self.pilot.repository, ""]
            with mock.patch.object(run_pilots, "_git", side_effect=answers):
                evidence = run_pilots.verify_checkout(self.pilot, checkout)
        self.assertEqual(evidence["head"], self.pilot.commit)
        self.assertTrue(evidence["pristine"])
        self.assertEqual(evidence["source_paths"], list(self.pilot.source_paths))

    def test_verify_checkout_rejects_each_provenance_failure(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-checkout-") as temp:
            root = Path(temp)
            with self.assertRaisesRegex(PilotRunError, "not a Git worktree"):
                run_pilots.verify_checkout(self.pilot, root / "missing")
            checkout = self._checkout(root)
            cases = (
                (["0" * 40], "does not match"),
                ([self.pilot.commit, "https://example.invalid/repo.git"],
                 "origin"),
                ([self.pilot.commit, self.pilot.repository, " M source.pyx"],
                 "checkout is dirty"),
            )
            for answers, message in cases:
                with self.subTest(message=message), mock.patch.object(
                        run_pilots, "_git", side_effect=answers):
                    with self.assertRaisesRegex(PilotRunError, message):
                        run_pilots.verify_checkout(self.pilot, checkout)

            (checkout / self.pilot.source_paths[0]).unlink()
            answers = [self.pilot.commit, self.pilot.repository, ""]
            with mock.patch.object(run_pilots, "_git", side_effect=answers):
                with self.assertRaisesRegex(PilotRunError, "is missing"):
                    run_pilots.verify_checkout(self.pilot, checkout)

    def test_checkout_reuses_verified_tree_and_creates_exact_detached_tree(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-root-") as temp:
            root = Path(temp)
            existing = root / self.pilot.id
            existing.mkdir()
            evidence = {"head": self.pilot.commit}
            with mock.patch.object(
                    run_pilots, "verify_checkout", return_value=evidence) as verify:
                checkout, actual = run_pilots.checkout_pilot(self.pilot, root)
            self.assertEqual(checkout, existing)
            self.assertEqual(actual, evidence)
            verify.assert_called_once_with(self.pilot, existing)

        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-root-") as temp:
            root = Path(temp)
            checkout = root / self.pilot.id

            def create_on_init(command, cwd=None):
                if command[:3] == ["git", "init", "--quiet"]:
                    (checkout / ".git").mkdir(parents=True)
                return ""

            with mock.patch.object(run_pilots, "_run", side_effect=create_on_init), \
                    mock.patch.object(run_pilots, "_git", return_value=""), \
                    mock.patch.object(
                        run_pilots, "verify_checkout", return_value=evidence):
                actual_checkout, actual = run_pilots.checkout_pilot(
                    self.pilot, root)
            self.assertEqual(actual_checkout, checkout)
            self.assertEqual(actual, evidence)

    def test_failed_checkout_removes_partial_directory(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-root-") as temp:
            root = Path(temp)
            checkout = root / self.pilot.id

            def create_on_init(command, cwd=None):
                (checkout / ".git").mkdir(parents=True, exist_ok=True)
                return ""

            with mock.patch.object(run_pilots, "_run", side_effect=create_on_init), \
                    mock.patch.object(
                        run_pilots, "_git", side_effect=PilotRunError("fetch failed")):
                with self.assertRaisesRegex(PilotRunError, "fetch failed"):
                    run_pilots.checkout_pilot(self.pilot, root)
            self.assertFalse(checkout.exists())

    def test_scan_pilot_compares_status_and_required_actions(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-scan-") as temp:
            checkout = self._checkout(Path(temp))
            scan = {
                "summary": {
                    "total": 1, "compatible": 0,
                    "rejected": 1, "compiler-error": 0,
                },
                "sources": [{
                    "diagnostics": [
                        {"action": {"id": action_id}}
                        for action_id in self.pilot.expected_action_ids
                    ],
                }],
            }
            with mock.patch.object(run_pilots, "scan_sources", return_value=scan):
                report = run_pilots.scan_pilot(self.pilot, checkout)
            self.assertTrue(report["expectation_met"])
            self.assertEqual(report["observed"]["status"], "rejected")
            self.assertEqual(report["missing_action_ids"], [])

            scan["sources"][0]["diagnostics"] = []
            with mock.patch.object(run_pilots, "scan_sources", return_value=scan):
                report = run_pilots.scan_pilot(self.pilot, checkout)
            self.assertFalse(report["expectation_met"])
            self.assertEqual(
                report["missing_action_ids"],
                list(self.pilot.expected_action_ids),
            )

            scan["summary"] = {
                "total": 1, "compatible": 0,
                "rejected": 0, "compiler-error": 1,
            }
            with mock.patch.object(run_pilots, "scan_sources", return_value=scan):
                report = run_pilots.scan_pilot(self.pilot, checkout)
            self.assertEqual(report["observed"]["status"], "compiler-error")

        compatible = {
            "summary": {"compiler-error": 0, "rejected": 0},
        }
        self.assertEqual(run_pilots._observed_status(compatible), "compatible")

    def test_blocked_pilot_requires_exact_source_located_diagnostics(self):
        pilot = self.manifest.pilots[-1]
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-blocked-") as temp:
            checkout = self._checkout(Path(temp), pilot=pilot)
            source = checkout / pilot.source_paths[0]
            scan = {
                "summary": {
                    "total": 1, "compatible": 0,
                    "rejected": 1, "compiler-error": 0,
                },
                "sources": [{
                    "diagnostics": [
                        {
                            "path": str(source),
                            "line": line,
                            "column": 1,
                            "action": {"id": "numpy-c-api"},
                        }
                        for line in (37, 38)
                    ],
                }],
            }
            with mock.patch.object(run_pilots, "scan_sources", return_value=scan):
                report = run_pilots.scan_pilot(pilot, checkout)
            self.assertTrue(report["expectation_met"])
            self.assertEqual(report["missing_diagnostics"], [])
            self.assertEqual(
                report["observed"]["diagnostics"],
                list(pilot.expected_diagnostics))

            scan["sources"][0]["diagnostics"][0]["column"] = 2
            with mock.patch.object(run_pilots, "scan_sources", return_value=scan):
                report = run_pilots.scan_pilot(pilot, checkout)
            self.assertFalse(report["expectation_met"])
            self.assertEqual(
                report["missing_diagnostics"],
                [pilot.expected_diagnostics[0]])

    def test_diagnostic_key_ignores_unlocated_or_external_findings(self):
        checkout = Path("/tmp/pilot")
        self.assertIsNone(run_pilots._diagnostic_key(checkout, {}))
        self.assertIsNone(run_pilots._diagnostic_key(checkout, {
            "path": "/tmp/elsewhere/source.pyx",
            "line": 1,
            "column": 1,
            "action": {"id": "numpy-c-api"},
        }))
        self.assertIsNone(run_pilots._diagnostic_key(checkout, {
            "path": "/tmp/pilot/source.pyx",
            "line": None,
            "column": None,
            "action": {},
        }))

    def test_scan_pilot_requires_a_selected_cython_source(self):
        pilot = self.pilot.__class__(
            **{**self.pilot.__dict__, "source_paths": ("native.c",)})
        with self.assertRaisesRegex(PilotRunError, "no Python/Cython source"):
            run_pilots.scan_pilot(pilot, Path("/unused"))

    def test_run_matrix_requires_action_and_aggregates_expectations(self):
        with self.assertRaisesRegex(PilotRunError, "select --checkout"):
            run_pilots.run_matrix(self.manifest, "/tmp/unused")
        evidence = {"head": "pinned"}
        scans = iter([
            {"expectation_met": True},
            {"expectation_met": True},
            {"expectation_met": False},
            {"expectation_met": True},
        ])
        with mock.patch.object(
                run_pilots, "verify_checkout", return_value=evidence), \
                mock.patch.object(
                    run_pilots, "scan_pilot", side_effect=lambda *a, **k: next(scans)):
            report = run_pilots.run_matrix(
                self.manifest,
                "/tmp/pilots",
                do_scan=True,
                generated_at="2026-08-02T12:00:00+00:00",
            )
        self.assertFalse(report["expectations_met"])
        self.assertEqual(report["generated_at"], "2026-08-02T12:00:00+00:00")
        self.assertEqual(len(report["pilots"]), 4)
        blocked = report["pilots"][-1]
        self.assertEqual(blocked["id"], "bezier-numpy-blocked")
        self.assertEqual(
            blocked["gates"]["performance"]["status"], "blocked")
        self.assertIn(
            "no performance ratio",
            blocked["gates"]["performance"]["reason"])

        with mock.patch.object(
                run_pilots, "checkout_pilot",
                side_effect=lambda pilot, root: (
                    Path(root) / pilot.id, {"head": pilot.commit})), \
                mock.patch.object(
                    run_pilots, "scan_pilot",
                    return_value={"expectation_met": True}):
            report = run_pilots.run_matrix(
                self.manifest,
                "/tmp/pilots",
                do_checkout=True,
                do_scan=True,
                generated_at="2026-08-02T12:00:00+00:00",
            )
        self.assertTrue(report["expectations_met"])

    def test_run_matrix_filters_exact_pilot_ids_and_rejects_unknown(self):
        selected = self.manifest.pilots[1]
        evidence = {"head": selected.commit}
        with mock.patch.object(
                    run_pilots, "verify_checkout",
                    return_value=evidence) as verify, \
                mock.patch.object(
                    run_pilots, "scan_pilot",
                    return_value={"expectation_met": True}):
            report = run_pilots.run_matrix(
                self.manifest,
                "/tmp/pilots",
                do_scan=True,
                generated_at="2026-08-03T12:00:00+00:00",
                pilot_ids=[selected.id, selected.id],
            )
        self.assertEqual([item["id"] for item in report["pilots"]], [selected.id])
        verify.assert_called_once()
        with self.assertRaisesRegex(PilotRunError, "unknown pilot IDs"):
            run_pilots.run_matrix(
                self.manifest,
                "/tmp/pilots",
                do_scan=True,
                pilot_ids=["missing-pilot"],
            )

    def test_python_resolution_and_cli_output(self):
        self.assertTrue(Path(run_pilots._python_executable("python3")).is_file())
        with self.assertRaisesRegex(PilotRunError, "interpreter not found"):
            run_pilots._python_executable("definitely-not-an-ahpy-python")

        report = {"expectations_met": True, "pilots": []}
        with tempfile.TemporaryDirectory(prefix="ahpy-pilot-output-") as temp:
            output = Path(temp) / "nested" / "report.json"
            with mock.patch.object(run_pilots, "load_manifest",
                                   return_value=self.manifest), \
                    mock.patch.object(
                        run_pilots, "run_matrix",
                        return_value=report) as run_matrix:
                self.assertEqual(run_pilots.main([
                    "--checkout-root", temp,
                    "--scan",
                    "--pilot", self.pilot.id,
                    "--output", str(output),
                ]), 0)
            self.assertEqual(json.loads(output.read_text())["pilots"], [])
            self.assertEqual(
                run_matrix.call_args.kwargs["pilot_ids"],
                [self.pilot.id])

        report["expectations_met"] = False
        stdout = io.StringIO()
        with mock.patch.object(run_pilots, "load_manifest",
                               return_value=self.manifest), \
                mock.patch.object(run_pilots, "run_matrix", return_value=report), \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(run_pilots.main([
                "--checkout-root", "/tmp/pilots", "--scan"]), 1)
        self.assertFalse(json.loads(stdout.getvalue())["expectations_met"])

        with self.assertRaises(SystemExit):
            run_pilots.main([])
        with self.assertRaises(SystemExit):
            run_pilots.main([
                "--checkout-root", "/definitely/missing/ahpy-pilots",
                "--scan",
            ])


if __name__ == "__main__":
    unittest.main()
