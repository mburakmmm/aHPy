import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "ahpy-testpypi.yml"
).read_text(encoding="utf8")


class TestPyPIWorkflowTest(unittest.TestCase):

    def test_manual_rehearsal_does_not_publish_by_default(self):
        triggers = WORKFLOW.split("\npermissions:", 1)[0]
        self.assertIn("workflow_dispatch:", triggers)
        self.assertIn("default: false", triggers)
        for forbidden in ("pull_request:", "push:", "schedule:"):
            self.assertNotIn(forbidden, triggers)
        publish = WORKFLOW.split("  publish-testpypi:\n", 1)[1]
        self.assertIn("if: ${{ inputs.publish }}", publish)

    def test_build_and_oidc_publish_permissions_are_separate(self):
        build, publish = WORKFLOW.split("  publish-testpypi:\n", 1)
        self.assertNotIn("id-token: write", build)
        permission_block = publish.split("    steps:\n", 1)[0]
        self.assertIn("      actions: read", permission_block)
        self.assertIn("      id-token: write", permission_block)
        self.assertNotIn("contents: write", permission_block)
        self.assertNotIn("packages: write", permission_block)
        self.assertIn("      name: testpypi", permission_block)

    def test_candidate_is_fail_closed_and_frontend_only(self):
        build, publish = WORKFLOW.split("  publish-testpypi:\n", 1)
        for required in (
            "release_artifact_integration.py",
            "verify_reproducible_packages.py",
            "prepare_publish_dist.py",
            "--repository testpypi",
            "twine check --strict",
        ):
            self.assertIn(required, build)
        self.assertLess(
            build.index("release_artifact_integration.py"),
            build.index("prepare_publish_dist.py"),
        )
        self.assertIn("packages-dir: candidate/publish-dist", publish)

    def test_publish_uses_pinned_pypa_action_without_passwords(self):
        actions = re.findall(
            r"^\s*uses:\s+([^\s#]+)", WORKFLOW, re.MULTILINE)
        self.assertGreaterEqual(len(actions), 5)
        for action in actions:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertIn(
            "pypa/gh-action-pypi-publish@"
            "ba38be9e461d3875417946c167d0b5f3d385a247",
            actions,
        )
        self.assertNotIn("password:", WORKFLOW)
        self.assertNotIn("username:", WORKFLOW)
        self.assertIn("skip-existing: false", WORKFLOW)
        self.assertIn("attestations: true", WORKFLOW)
        self.assertIn("https://test.pypi.org/legacy/", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
