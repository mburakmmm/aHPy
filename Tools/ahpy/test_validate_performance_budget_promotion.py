from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import validate_performance_budget_promotion as promotion


COMMIT = "a" * 40


class PerformanceBudgetPromotionTest(unittest.TestCase):
    def _contract(self):
        return {
            "schema_version": 1,
            "policy": {
                "classification": "regression",
                "release_enforced": False,
                "calibration_status": "hosted-history-pending",
                "minimum_hosted_reports": 5,
                "candidate_binding": "unbound",
                "calibration_source_commit": "",
            },
            "environment": {
                "abi": "universal",
                "hpy": "0.9.0",
                "python_implementation": "CPython",
            },
            "measurement": {
                "iterations": 100000,
                "warmups": 2,
                "repeats": 7,
            },
            "large_type_compile": {
                "timeout_seconds": 60,
                "enforce_o3": False,
            },
            "runtime_ratio": {
                operation: 2.0 for operation in promotion.OPERATIONS
            },
            "footprint": {
                "generated_c_bytes": 100000,
                "generated_binary_bytes": 200000,
                "binary_to_reference_ratio": 2.0,
            },
        }

    def _proposal(self):
        contract = self._contract()
        distribution = {"proposed_maximum": 1.25}
        return {
            "schema_version": promotion.CALIBRATION_SCHEMA_VERSION,
            "proposal_only": True,
            "apply_automatically": False,
            "source_commit": COMMIT,
            "report_count": 5,
            "minimum_reports": 5,
            "input_budget_policy": copy.deepcopy(contract["policy"]),
            "input_budget_contract": contract,
            "runtime_ratio": {
                operation: dict(distribution)
                for operation in promotion.OPERATIONS
            },
            "build_time": {
                "cython_seconds": {"proposed_maximum": 1.5},
                "native_build_seconds": {"proposed_maximum": 2.5},
            },
            "peak_memory": {
                "generated_peak_rss_bytes": {"proposed_maximum": 36000000},
                "generated_to_reference_ratio": {
                    "proposed_maximum": 1.2,
                },
            },
            "footprint": {
                "generated_c_bytes_proposed_maximum": 36000,
                "generated_binary_bytes_proposed_maximum": 91200,
                "binary_to_reference_ratio_proposed_maximum": 1.22,
            },
            "large_type_compile": {
                "frontend_seconds": {"proposed_maximum": 1.75},
                "o0_seconds": {"proposed_maximum": 6.25},
            },
        }

    def _release_budget(self):
        proposal = self._proposal()
        return {
            "schema_version": 1,
            "policy": {
                "classification": "release",
                "release_enforced": True,
                "calibration_status": "approved",
                "minimum_hosted_reports": 5,
                "candidate_binding": "hosted-checkout",
                "calibration_source_commit": COMMIT,
            },
            "environment": copy.deepcopy(
                proposal["input_budget_contract"]["environment"]),
            "measurement": copy.deepcopy(
                proposal["input_budget_contract"]["measurement"]),
            "large_type_compile": copy.deepcopy(
                proposal["input_budget_contract"]["large_type_compile"]),
            "runtime_ratio": {
                operation: proposal["runtime_ratio"][operation][
                    "proposed_maximum"]
                for operation in promotion.OPERATIONS
            },
            "footprint": {
                budget_field: proposal["footprint"][proposal_field]
                for budget_field, proposal_field
                in promotion.FOOTPRINT_PROPOSALS.items()
            },
            "release_absolute": {
                budget_field: self._nested_proposed(proposal, path)
                for budget_field, path
                in promotion.RELEASE_ABSOLUTE_PROPOSALS.items()
            },
        }

    @staticmethod
    def _nested_proposed(proposal, path):
        value = proposal
        for part in path:
            value = value[part]
        return value["proposed_maximum"]

    @staticmethod
    def _toml(data):
        lines = ["schema_version = %d" % data["schema_version"]]
        for section in (
                "policy", "environment", "measurement",
                "large_type_compile", "runtime_ratio", "footprint",
                "release_absolute"):
            if section not in data:
                continue
            lines.extend(("", "[%s]" % section))
            for name, value in data[section].items():
                if isinstance(value, bool):
                    rendered = str(value).lower()
                elif isinstance(value, str):
                    rendered = json.dumps(value)
                else:
                    rendered = repr(value)
                lines.append("%s = %s" % (name, rendered))
        return "\n".join(lines) + "\n"

    def _write_pair(self, root, proposal=None, budget=None):
        proposal = self._proposal() if proposal is None else proposal
        budget = self._release_budget() if budget is None else budget
        proposal_path = Path(root) / "proposal.json"
        budget_path = Path(root) / "budgets.toml"
        proposal_path.write_text(json.dumps(proposal), encoding="utf8")
        budget_path.write_text(self._toml(budget), encoding="utf8")
        return proposal_path, budget_path

    def test_valid_promotion_returns_machine_readable_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self._write_pair(temp_dir)
            result = promotion.validate_promotion(*paths)
        self.assertEqual(result, {
            "schema_version": promotion.PROMOTION_SCHEMA_VERSION,
            "status": "valid",
            "calibration_source_commit": COMMIT,
            "report_count": 5,
            "checked_fields": 19,
        })

    def test_proposal_envelope_is_fail_closed(self):
        cases = (
            ("schema_version", 2, "schema_version"),
            ("proposal_only", False, "proposal-only"),
            ("apply_automatically", True, "proposal-only"),
            ("source_commit", "short", "source_commit"),
            ("report_count", True, "positive integer"),
            ("minimum_reports", 0, "positive integer"),
            ("report_count", 4, "fewer reports"),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                proposal = self._proposal()
                proposal[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    promotion.validate_proposal(proposal)
        with self.assertRaisesRegex(ValueError, "must be an object"):
            promotion.validate_proposal([])

    def test_input_contract_and_policy_are_fail_closed(self):
        cases = (
            ("input_budget_contract__schema_version", 2, "contract is invalid"),
            ("input_budget_contract__environment__abi", "cpython",
             "environment.abi must be universal"),
            ("input_budget_policy__minimum_hosted_reports", 6,
             "differs from its contract"),
            ("input_budget_policy__classification", "release",
             "differs from its contract"),
            ("minimum_reports", 4, "fewer reports"),
        )
        for dotted, value, message in cases:
            with self.subTest(dotted=dotted):
                proposal = self._proposal()
                target = proposal
                parts = dotted.split("__")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
                if dotted == "minimum_reports":
                    proposal["report_count"] = 3
                with self.assertRaisesRegex(ValueError, message):
                    promotion.validate_proposal(proposal)

        proposal = self._proposal()
        proposal["minimum_reports"] = 5
        proposal["input_budget_policy"]["minimum_hosted_reports"] = 6
        proposal["input_budget_contract"]["policy"][
            "minimum_hosted_reports"] = 6
        with self.assertRaisesRegex(ValueError, "minimum weakens"):
            promotion.validate_proposal(proposal)

        proposal = self._proposal()
        proposal["input_budget_policy"]["calibration_status"] = "approved"
        proposal["input_budget_contract"]["policy"][
            "calibration_status"] = "approved"
        with self.assertRaisesRegex(ValueError, "input budget contract is invalid"):
            promotion.validate_proposal(proposal)

    def test_proposed_threshold_shape_and_values_are_validated(self):
        cases = (
            ("runtime_ratio", {}, "runtime operations"),
            ("runtime_ratio__call", {}, "proposed_maximum is missing"),
            ("runtime_ratio__call__proposed_maximum", float("inf"),
             "positive finite"),
            ("footprint", [], "lacks footprint"),
            ("footprint__generated_c_bytes_proposed_maximum", 0,
             "positive finite"),
            ("build_time", {}, "proposal.build_time.cython_seconds"),
        )
        for dotted, value, message in cases:
            with self.subTest(dotted=dotted):
                proposal = self._proposal()
                target = proposal
                parts = dotted.split("__")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
                with self.assertRaisesRegex(ValueError, message):
                    promotion.validate_proposal(proposal)

    def test_missing_or_invalid_proposal_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "proposal.json"
            with self.assertRaisesRegex(ValueError, "cannot read"):
                promotion.load_proposal(path)
            path.write_text("{", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "cannot read"):
                promotion.load_proposal(path)

    def test_release_policy_binding_and_sample_floor_are_required(self):
        cases = (
            ("policy__classification", "regression", "must use release"),
            ("policy__calibration_source_commit", "b" * 40,
             "calibration_source_commit differs"),
            ("policy__minimum_hosted_reports", 6, "fewer reports"),
        )
        for dotted, value, message in cases:
            with self.subTest(dotted=dotted):
                budget = self._release_budget()
                target = budget
                for part in dotted.split("__")[:-1]:
                    target = target[part]
                target[dotted.split("__")[-1]] = value
                if dotted == "policy__classification":
                    budget["policy"].update({
                        "release_enforced": False,
                        "calibration_status": "hosted-history-pending",
                        "candidate_binding": "unbound",
                        "calibration_source_commit": "",
                    })
                    del budget["release_absolute"]
                with tempfile.TemporaryDirectory() as temp_dir:
                    paths = self._write_pair(temp_dir, budget=budget)
                    with self.assertRaisesRegex(ValueError, message):
                        promotion.validate_promotion(*paths)

    def test_contract_drift_is_rejected(self):
        cases = (
            ("environment__hpy", "0.10.0", "environment differs"),
            ("measurement__iterations", 200000, "measurement differs"),
            ("large_type_compile__timeout_seconds", 120,
             "large_type_compile differs"),
        )
        for dotted, value, message in cases:
            with self.subTest(dotted=dotted):
                budget = self._release_budget()
                section, field = dotted.split("__")
                budget[section][field] = value
                with tempfile.TemporaryDirectory() as temp_dir:
                    paths = self._write_pair(temp_dir, budget=budget)
                    with self.assertRaisesRegex(ValueError, message):
                        promotion.validate_promotion(*paths)

    def test_every_promoted_threshold_must_match_exactly(self):
        cases = (
            ("runtime_ratio", "call", "runtime_ratio.call"),
            ("footprint", "generated_c_bytes", "footprint.generated_c_bytes"),
            ("release_absolute", "large_type_o0_seconds",
             "release_absolute.large_type_o0_seconds"),
        )
        for section, field, message in cases:
            with self.subTest(section=section, field=field):
                budget = self._release_budget()
                budget[section][field] += 1
                with tempfile.TemporaryDirectory() as temp_dir:
                    paths = self._write_pair(temp_dir, budget=budget)
                    with self.assertRaisesRegex(ValueError, message):
                        promotion.validate_promotion(*paths)

    def test_invalid_release_budget_file_is_wrapped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            proposal_path, budget_path = self._write_pair(temp_dir)
            budget_path.write_text("{", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "cannot read release"):
                promotion.validate_promotion(proposal_path, budget_path)

    def test_cli_supports_text_and_json_and_reports_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            proposal_path, budget_path = self._write_pair(temp_dir)
            base = [
                "validate_performance_budget_promotion.py",
                str(proposal_path), str(budget_path),
            ]
            output = io.StringIO()
            with mock.patch("sys.argv", base), contextlib.redirect_stdout(output):
                promotion.main()
            self.assertIn("19 thresholds from 5 hosted reports", output.getvalue())

            output = io.StringIO()
            with (
                mock.patch("sys.argv", base + ["--json"]),
                contextlib.redirect_stdout(output),
            ):
                promotion.main()
            self.assertEqual(json.loads(output.getvalue())["status"], "valid")

            with (
                mock.patch("sys.argv", base),
                mock.patch("sys.stderr"),
                mock.patch.object(
                    promotion, "validate_promotion",
                    side_effect=ValueError("invalid promotion"),
                ),
                self.assertRaises(SystemExit) as raised,
            ):
                promotion.main()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
