import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "ahpy-performance-calibration.yml"
).read_text(encoding="utf8")


class PerformanceCalibrationWorkflowTest(unittest.TestCase):

    def test_workflow_is_manual_only_and_read_only(self):
        triggers = WORKFLOW.split("\nconcurrency:", 1)[0]
        self.assertIn("workflow_dispatch:", triggers)
        for forbidden in ("pull_request:", "push:", "schedule:"):
            self.assertNotIn(forbidden, triggers)
        permissions = WORKFLOW.split("\npermissions:\n", 1)[1].split(
            "\nenv:", 1)[0]
        self.assertIn("  actions: read", permissions)
        self.assertIn("  contents: read", permissions)
        for forbidden in (
                "write", "id-token", "attestations", "packages"):
            self.assertNotIn(forbidden, permissions)

    def test_five_isolated_samples_are_explicit_and_fail_closed(self):
        sample = WORKFLOW.split("  performance-sample:\n", 1)[1].split(
            "\n  calibrate-release-budget:\n", 1)[0]
        self.assertIn("fail-fast: false", sample)
        self.assertIn("max-parallel: 5", sample)
        self.assertIn("sample: [1, 2, 3, 4, 5]", sample)
        self.assertIn("timeout-minutes: 90", sample)
        self.assertIn("AHPY_BENCHMARK_SAMPLE_ID: ${{ matrix.sample }}", sample)
        self.assertIn("benchmark-${{ matrix.sample }}.json", sample)
        self.assertIn(
            "ahpy-performance-sample-${{ github.run_id }}-"
            "${{ github.run_attempt }}-${{ matrix.sample }}",
            sample,
        )
        self.assertIn("if-no-files-found: error", sample)

    def test_aggregate_requires_all_samples_and_exact_selected_commit(self):
        aggregate = WORKFLOW.split("  calibrate-release-budget:\n", 1)[1]
        self.assertIn("needs: performance-sample", aggregate)
        self.assertIn("timeout-minutes: 10", aggregate)
        self.assertIn("merge-multiple: true", aggregate)
        self.assertIn("performance-history/benchmark-*.json", aggregate)
        self.assertIn("--expected-commit ${{ github.sha }}", aggregate)
        self.assertIn("--repository ${{ github.repository }}", aggregate)
        self.assertIn("--minimum-reports 5", aggregate)
        self.assertIn("release-budget-proposal.json", aggregate)
        self.assertNotIn("continue-on-error:", WORKFLOW)

    def test_every_external_action_is_pinned(self):
        actions = re.findall(
            r"^\s*uses:\s+([^\s#]+)", WORKFLOW, re.MULTILINE)
        self.assertEqual(len(actions), 7)
        for action in actions:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
