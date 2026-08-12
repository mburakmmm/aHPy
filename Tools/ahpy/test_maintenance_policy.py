import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import maintenance_policy


class MaintenancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = maintenance_policy.load_policy()

    def test_repository_policy_is_complete_and_renders_capacity(self):
        text = maintenance_policy.render_text(self.policy)
        self.assertIn("aHPy maintenance policy: valid", text)
        self.assertIn("project maintainers: @mburakmmm", text)
        self.assertIn("bus factor: 1", text)
        self.assertIn("dependency updates: monthly", text)
        self.assertIn("security scanning: continuous-and-weekly", text)
        self.assertIn("standard recovery: yank", text)
        workflow = (
            maintenance_policy.ROOT / ".github" / "workflows" /
            "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Exercise release recovery and backport policy", workflow)
        self.assertIn("Tools/ahpy/release_recovery_drill.py", workflow)
        self.assertIn("packaging-results/release-recovery-drill.json", workflow)

    def test_policy_tables_fail_closed_on_inconsistent_contracts(self):
        mutations = []

        data = copy.deepcopy(self.policy)
        data.pop("cadence")
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["schema_version"] = 2
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["project_status"] = "stable"
        mutations.append(data)

        for field, value in (
                ("project_maintainers", ["not-a-handle"]),
                ("security_maintainers", []),
                ("release_maintainers", ["@bad_handle"]),
                ("bus_factor", 0),
                ("release_approval_minimum", 2)):
            data = copy.deepcopy(self.policy)
            data["ownership"][field] = value
            mutations.append(data)

        for field, value in (
                ("integration", "develop"),
                ("release_pattern", "release/*"),
                ("topic_prefix", "topic"),
                ("backport_categories", ["security"]),
                ("direct_push", True),
                ("history_rewrite", True)):
            data = copy.deepcopy(self.policy)
            data["branches"][field] = value
            mutations.append(data)

        data = copy.deepcopy(self.policy)
        data["support"]["stable_release_lines"] = 1
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["cadence"]["hpy_review"] = "never"
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["cadence"]["security_scanning"] = "monthly"
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["deprecation"]["silent_abi_fallback_allowed"] = True
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["security"]["public_vulnerability_issues"] = True
        mutations.append(data)
        for field, value in (
                ("standard_defect_action", "delete"),
                ("replacement_version_required", False),
                ("public_reason_required", False),
                ("delete_allowed_for", ["ordinary-defect"]),
                ("unyank_requires_owner_approval", False),
                ("security_coordination", "public-immediately"),
                ("backport_regression_test_required", False),
                ("backport_mandatory_matrix_required", False),
                ("support_expansion_allowed", True)):
            data = copy.deepcopy(self.policy)
            data["recovery"][field] = value
            mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["automation"]["codeql_languages"] = ["python"]
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["required_documents"] = ["SECURITY.md", "SECURITY.md"]
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["required_documents"] = ["../outside"]
        mutations.append(data)
        data = copy.deepcopy(self.policy)
        data["required_documents"] = ["missing-policy-document.md"]
        mutations.append(data)

        for data in mutations:
            with self.subTest(data=data):
                with self.assertRaises(maintenance_policy.MaintenancePolicyError):
                    maintenance_policy.validate_policy(data)

    def test_table_shapes_and_paths_are_strict(self):
        data = copy.deepcopy(self.policy)
        data["ownership"]["unknown"] = True
        with self.assertRaisesRegex(
                maintenance_policy.MaintenancePolicyError, "keys mismatch"):
            maintenance_policy.validate_policy(data)
        with self.assertRaises(maintenance_policy.MaintenancePolicyError):
            maintenance_policy._exact_keys([], {"field"}, "invalid")
        with self.assertRaises(maintenance_policy.MaintenancePolicyError):
            maintenance_policy._safe_repo_path(42, "invalid")
        with self.assertRaises(maintenance_policy.MaintenancePolicyError):
            maintenance_policy._safe_repo_path("/absolute", "invalid")

    def test_loader_rejects_missing_and_malformed_toml(self):
        with TemporaryDirectory(prefix="ahpy-maintenance-policy-") as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(
                    maintenance_policy.MaintenancePolicyError, "cannot read"):
                maintenance_policy.load_policy(root / "missing.toml", root=root)
            broken = root / "broken.toml"
            broken.write_text("not = [valid", encoding="utf8")
            with self.assertRaisesRegex(
                    maintenance_policy.MaintenancePolicyError, "cannot read"):
                maintenance_policy.load_policy(broken, root=root)

    def test_cli_prints_text_json_and_actionable_errors(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(maintenance_policy.main([]), 0)
        self.assertIn("aHPy maintenance policy: valid", stdout.getvalue())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(maintenance_policy.main(["--json"]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["schema_version"], 1)

        with TemporaryDirectory(prefix="ahpy-maintenance-cli-") as temp_dir:
            missing = Path(temp_dir) / "missing.toml"
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()):
                maintenance_policy.main(["--policy", str(missing)])


if __name__ == "__main__":
    unittest.main()
