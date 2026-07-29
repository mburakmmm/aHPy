import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "ahpy-release-attestations.yml"
)
SIGNING_DOC_PATH = ROOT / "docs" / "ahpy" / "release-signing.md"


class ReleaseAttestationWorkflowTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf8")
        cls.signing_doc = SIGNING_DOC_PATH.read_text(encoding="utf8")

    def test_only_exact_release_tags_trigger_signing(self):
        triggers = self.workflow.split("\npermissions:", 1)[0]
        self.assertIn('      - "ahpy-v*"', triggers)
        for forbidden in (
            "pull_request:",
            "workflow_dispatch:",
            "schedule:",
            "branches:",
        ):
            self.assertNotIn(forbidden, triggers)
        self.assertIn("actual == expected", self.workflow)

    def test_signing_job_has_only_required_oidc_permissions(self):
        job = self.workflow.split("  attest-release:\n", 1)[1]
        permission_block = job.split("    steps:\n", 1)[0]
        self.assertIn("      contents: read", permission_block)
        self.assertIn("      id-token: write", permission_block)
        self.assertIn("      attestations: write", permission_block)
        self.assertIn("      artifact-metadata: write", permission_block)
        self.assertNotIn("contents: write", permission_block)
        self.assertNotIn("packages: write", permission_block)

    def test_external_actions_are_immutable(self):
        actions = re.findall(
            r"^\s*uses:\s+([^\s#]+)", self.workflow, re.MULTILINE)
        self.assertGreaterEqual(len(actions), 5)
        for action in actions:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertIn(
            "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6",
            actions,
        )

    def test_release_gate_rebuilds_before_attestation(self):
        build = self.workflow.index("release_artifact_integration.py")
        reproduce = self.workflow.index("verify_reproducible_packages.py")
        provenance = self.workflow.index("id: provenance")
        sbom = self.workflow.index("id: sbom")
        self.assertLess(build, reproduce)
        self.assertLess(reproduce, provenance)
        self.assertLess(provenance, sbom)
        self.assertIn(
            'subject-path: "packaging-results/release-bundle/*"',
            self.workflow,
        )
        self.assertIn(
            "sbom-path: packaging-results/release-bundle/sbom.spdx.json",
            self.workflow,
        )

    def test_verification_policy_pins_repository_workflow_and_tag(self):
        for required in (
            "sha256sum --check SHA256SUMS",
            "shasum -a 256 -c SHA256SUMS",
            "gh attestation verify",
            "--repo mburakmmm/aHPy",
            "--signer-workflow",
            ".github/workflows/ahpy-release-attestations.yml",
            "--source-ref refs/tags/ahpy-v",
            "--deny-self-hosted-runners",
            "--custom-trusted-root trusted_root.jsonl",
            "pypi-attestations",
        ):
            self.assertIn(required, self.signing_doc)


if __name__ == "__main__":
    unittest.main()
