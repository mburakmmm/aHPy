import re
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ahpy-security.yml"


class SecurityWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf8")
        cls.dependabot = (ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf8")
        cls.security = (ROOT / "SECURITY.md").read_text(encoding="utf8")
        cls.maintenance = (
            ROOT / "docs" / "ahpy" / "maintenance.md").read_text(
                encoding="utf8")
        cls.codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(
            encoding="utf8")
        cls.policy = tomllib.loads((
            ROOT / "tests" / "ahpy" / "maintenance-policy.toml"
        ).read_text(encoding="utf8"))

    def test_security_triggers_changes_release_lines_and_weekly_scan(self):
        triggers = self.workflow.split("\npermissions:", 1)[0]
        for required in (
                "pull_request:", "push:", "- main", '"ahpy/**"',
                "schedule:", 'cron: "17 4 * * 1"', "workflow_dispatch:"):
            self.assertIn(required, triggers)
        self.assertIn("cancel-in-progress: true", triggers)

    def test_permissions_are_minimal_and_security_write_is_scoped(self):
        global_permissions = self.workflow.split("\njobs:", 1)[0].split(
            "\npermissions:", 1)[1]
        self.assertIn("contents: read", global_permissions)
        self.assertNotIn("write", global_permissions)
        dependency_job, codeql_job = self.workflow.split(
            "  dependency-review:\n", 1)[1].split("  codeql:\n", 1)
        self.assertIn("if: github.event_name == 'pull_request'", dependency_job)
        self.assertNotIn("security-events: write", dependency_job)
        self.assertIn("security-events: write", codeql_job)
        self.assertNotIn("contents: write", codeql_job)

    def test_external_actions_are_exact_immutable_releases(self):
        actions = re.findall(r"^\s*uses:\s+([^\s#]+)", self.workflow, re.MULTILINE)
        self.assertEqual(len(actions), 5)
        for action in actions:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertIn(
            "actions/dependency-review-action@"
            "a1d282b36b6f3519aa1f3fc636f609c47dddb294", actions)
        self.assertEqual(sum(
            action.endswith("@7211b7c8077ea37d8641b6271f6a365a22a5fbfa")
            for action in actions), 2)
        self.assertEqual(self.workflow.count("persist-credentials: false"), 2)

    def test_dependency_review_and_codeql_fail_closed_contract(self):
        for required in (
                "fail-on-severity: moderate", "warn-only: false",
                "show-openssf-scorecard: true", "- c-cpp", "- python",
                "build-mode: none", "queries: security-extended",
                'category: "/language:${{ matrix.language }}"'):
            self.assertIn(required, self.workflow)
        self.assertNotIn("continue-on-error", self.workflow)

    def test_dependabot_covers_actions_and_all_python_dependency_roots(self):
        self.assertEqual(self.dependabot.count('package-ecosystem: "pip"'), 3)
        for directory in ('directory: ".github"', 'directory: "/"',
                          'directory: "/tests/ahpy"'):
            self.assertIn(directory, self.dependabot)
        self.assertIn('package-ecosystem: "github-actions"', self.dependabot)
        self.assertEqual(self.dependabot.count('interval: "monthly"'), 4)

    def test_public_policy_names_private_channel_capacity_and_responsibility(self):
        self.assertIn("security/advisories/new", self.security)
        self.assertIn("private vulnerability reporting", self.security)
        self.assertIn("channel was enabled", self.security)
        self.assertIn("no response-time or embargo", self.security.lower())
        for required in (
                "@mburakmmm", "bus factor is explicitly one",
                "at most one stable", "explicit dated EOL",
                "at least one subsequent aHPy release cycle",
                "Every change plus weekly scheduled scan",
                "TestPyPI/PyPI upload"):
            self.assertIn(required, self.maintenance)
        self.assertRegex(
            self.maintenance, r"Direct pushes and\s+history rewrites are forbidden")
        self.assertIn("* @mburakmmm", self.codeowners)
        self.assertEqual(self.policy["ownership"]["bus_factor"], 1)


if __name__ == "__main__":
    unittest.main()
