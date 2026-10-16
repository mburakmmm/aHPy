import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import nox_integration_policy as policy


class NoxIntegrationPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = policy.load_policy()

    def test_repository_policy_is_fail_closed_and_planning_only(self):
        self.assertEqual(self.policy["status"], "planned")
        self.assertEqual(
            self.policy["direction"], "ahpy-universal-to-nox")
        self.assertFalse(self.policy["reverse_direction_supported"])
        self.assertFalse(self.policy["silent_fallback_allowed"])
        self.assertFalse(self.policy["partial_package_allowed"])
        self.assertFalse(self.policy["nox_source_mutation_allowed"])
        self.assertEqual(
            self.policy["host"]["minimum_nox_release"], "unreleased")
        self.assertEqual(self.policy["host"]["support_status"], "blocked")
        self.assertFalse(self.policy["baseline"]["support_claim"])
        self.assertFalse(
            self.policy["baseline"]["retained_hosted_evidence"])
        self.assertEqual(list(self.policy["diagnostics"].values()), [
            "AHPY_NOX001", "AHPY_NOX002", "AHPY_NOX003", "AHPY_NOX004",
            "AHPY_NOX005", "AHPY_NOX006", "AHPY_NOX007", "AHPY_NOX008",
        ])

    def test_policy_and_schema_are_wired_into_hosted_evidence(self):
        workflow = (
            policy.ROOT / ".github" / "workflows" / "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Validate aHPy to NOX integration policy", workflow)
        self.assertIn("Tools/ahpy/nox_integration_policy.py --json", workflow)
        self.assertIn("packaging-results/nox-integration-policy.json", workflow)

    def test_rendering_reports_boundary_without_support_claim(self):
        rendered = policy.render_text(self.policy)
        self.assertIn("aHPy to NOX integration policy: valid", rendered)
        self.assertIn("status: planned", rendered)
        self.assertIn("direction: ahpy-universal-to-nox", rendered)
        self.assertIn("host profile: nox-hpy-host-v1", rendered)
        self.assertIn("HPy ABI: universal 0.9", rendered)
        self.assertIn("QBE baseline: local-probe-pass", rendered)
        self.assertIn("LLVM baseline: local-probe-fail", rendered)
        self.assertIn("support claim: false", rendered)

    def test_top_level_contract_mutations_fail_closed(self):
        mutations = []
        data = copy.deepcopy(self.policy)
        data.pop("ownership")
        mutations.append(data)
        for field, value in (
                ("schema_version", 2),
                ("contract_version", 2),
                ("status", "supported"),
                ("direction", "nox-to-python"),
                ("reverse_direction_supported", True),
                ("silent_fallback_allowed", True),
                ("partial_package_allowed", True),
                ("nox_source_mutation_allowed", True)):
            data = copy.deepcopy(self.policy)
            data[field] = value
            mutations.append(data)
        for data in mutations:
            with self.subTest(data=data):
                with self.assertRaises(policy.NoxIntegrationPolicyError):
                    policy.validate_policy(data)

    def test_host_artifact_and_ownership_mutations_fail_closed(self):
        mutations = []
        for table, field, value in (
                ("artifacts", "extension_suffix", ".so"),
                ("artifacts", "path_mode", "absolute"),
                ("artifacts", "reproducible", False),
                ("host", "hpy_abi", "hybrid"),
                ("host", "hpy_version", "latest"),
                ("host", "minimum_nox_release", "2.0.9"),
                ("host", "support_status", "supported"),
                ("host", "capability_query_required", False),
                ("baseline", "support_claim", True),
                ("baseline", "retained_hosted_evidence", True),
                ("baseline", "analyzed_nox_commit", "main")):
            data = copy.deepcopy(self.policy)
            data[table][field] = value
            mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["ownership"]["ahpy"].append("dynamic-loading")
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["ownership"]["nox"].remove("dynamic-loading")
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["diagnostics"]["unsupported_type"] = "AHPY_NOX007"
        mutations.append(data)
        for data in mutations:
            with self.subTest(data=data):
                with self.assertRaises(policy.NoxIntegrationPolicyError):
                    policy.validate_policy(data)

    def test_classifications_are_sorted_unique_and_disjoint(self):
        for table in ("types", "calls"):
            data = copy.deepcopy(self.policy)
            data[table]["required"] = list(reversed(
                data[table]["required"]))
            with self.subTest(table=table, defect="order"):
                with self.assertRaises(policy.NoxIntegrationPolicyError):
                    policy.validate_policy(data)
            data = copy.deepcopy(self.policy)
            data[table]["blocked"].append(data[table]["required"][0])
            data[table]["blocked"].sort()
            with self.subTest(table=table, defect="overlap"):
                with self.assertRaises(policy.NoxIntegrationPolicyError):
                    policy.validate_policy(data)

    def test_required_paths_and_schema_fail_closed(self):
        data = copy.deepcopy(self.policy)
        data["required_documents"] = ["../outside.md"]
        with self.assertRaises(policy.NoxIntegrationPolicyError):
            policy.validate_policy(data)

        data = copy.deepcopy(self.policy)
        data["required_documents"] = ["missing.md"]
        with self.assertRaisesRegex(
                policy.NoxIntegrationPolicyError, "files are missing"):
            policy.validate_policy(data)

        schema_path = (
            policy.ROOT / self.policy["artifacts"]["integration_schema"])
        schema = json.loads(schema_path.read_text(encoding="utf8"))
        schema["properties"]["host"]["properties"]["hpy_abi"] = {
            "const": "hybrid",
        }
        with self.assertRaisesRegex(
                policy.NoxIntegrationPolicyError, "host identity"):
            policy._validate_manifest_schema(schema, "test schema")

        with TemporaryDirectory(prefix="ahpy-nox-schema-") as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with self.assertRaisesRegex(
                    policy.NoxIntegrationPolicyError,
                    "cannot read NOX package schema"):
                policy._load_manifest_schema(missing)
            broken = Path(temp_dir) / "broken.json"
            broken.write_text("{not-json", encoding="utf8")
            with self.assertRaisesRegex(
                    policy.NoxIntegrationPolicyError,
                    "cannot read NOX package schema"):
                policy._load_manifest_schema(broken)

    def test_loader_and_cli_reject_bad_input_and_write_json(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(policy.main([]), 0)
        self.assertIn("integration policy: valid", stdout.getvalue())

        with TemporaryDirectory(prefix="ahpy-nox-policy-") as temp_dir:
            root = Path(temp_dir)
            output = root / "nested" / "policy.json"
            self.assertEqual(policy.main([
                "--json", "--output", str(output),
            ]), 0)
            rendered = json.loads(output.read_text(encoding="utf8"))
            self.assertEqual(rendered["contract_version"], 1)
            self.assertFalse(rendered["baseline"]["support_claim"])

            missing = root / "missing.toml"
            with self.assertRaisesRegex(
                    policy.NoxIntegrationPolicyError, "cannot read"):
                policy.load_policy(missing, root=root)
            broken = root / "broken.toml"
            broken.write_text("not = [valid", encoding="utf8")
            with self.assertRaisesRegex(
                    policy.NoxIntegrationPolicyError, "cannot read"):
                policy.load_policy(broken, root=root)
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()):
                policy.main(["--policy", str(missing)])


if __name__ == "__main__":
    unittest.main()
