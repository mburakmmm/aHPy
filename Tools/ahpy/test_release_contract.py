from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

import release_contract


class ReleaseContractTest(unittest.TestCase):
    def _contract(self):
        return tomllib.loads(
            release_contract.DEFAULT_CONTRACT.read_text(encoding="utf8"))

    def _repository_root(self, root):
        root = Path(root)
        for relative in (
                release_contract.HPY_VERSIONS,
                release_contract.UNIVERSAL_WORKFLOW,
                release_contract.CONTRACT_DOCUMENT):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                (release_contract.ROOT / relative).read_text(encoding="utf8"),
                encoding="utf8",
            )
        return root

    @staticmethod
    def _replace(root, relative, old, new):
        path = Path(root) / relative
        path.write_text(
            path.read_text(encoding="utf8").replace(old, new, 1),
            encoding="utf8",
        )

    def test_repository_contract_is_valid_and_summary_is_stable(self):
        contract = release_contract.load_contract()
        result = release_contract.summary(contract)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["product_level"], "preview")
        self.assertEqual(result["platform_count"], 6)
        self.assertEqual(result["frontend_count"], 7)
        self.assertEqual(result["supported_hpy_versions"], ["0.9.0"])
        self.assertEqual(result["supported_python_versions"], ["3.11"])

    def test_contract_envelope_and_distribution_are_exact(self):
        cases = (
            ("schema_version", 2, "schema must be 1"),
            ("product_level", "stable", "unpublished preview"),
            ("publication_status", "published", "unpublished preview"),
            ("general_cython_compatibility", True, "general Cython"),
            ("distribution", "Cython", "distribution identity"),
            ("distribution_version", "1.0", "distribution identity"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                contract = self._contract()
                contract[field] = value
                with self.assertRaisesRegex(
                        release_contract.ReleaseContractError, message):
                    release_contract.validate_contract(contract)
        contract = self._contract()
        contract["unknown"] = True
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "keys are incomplete"):
            release_contract.validate_contract(contract)
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "must be a table"):
            release_contract.validate_contract([])

    def test_cython_and_hpy_identity_are_exact(self):
        cases = (
            ("cython", {}, "cython keys"),
            ("cython__version", "0", "Cython identity"),
            ("hpy", {}, "hpy keys"),
            ("hpy__supported_versions", ["0.10.0"], "supported HPy"),
            ("hpy__setuptools_version", "1", "setuptools version"),
            ("hpy__development_commit", "short", "development identity"),
            ("hpy__development_status", "supported", "development identity"),
        )
        for dotted, value, message in cases:
            with self.subTest(dotted=dotted):
                contract = self._contract()
                target = contract
                parts = dotted.split("__")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
                with self.assertRaisesRegex(
                        release_contract.ReleaseContractError, message):
                    release_contract.validate_contract(contract)

    def test_hpy_manifest_is_required_and_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            (root / release_contract.HPY_VERSIONS).unlink()
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError, "cannot read HPy"):
                release_contract.validate_contract(self._contract(), root=root)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            (root / release_contract.HPY_VERSIONS).write_text(
                "schema_version = 1\n", encoding="utf8")
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError,
                    "lacks stable/development"):
                release_contract.validate_contract(self._contract(), root=root)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            self._replace(
                root, release_contract.HPY_VERSIONS,
                'version = "0.9.0"', 'version = "0.10.0"')
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError, "supported HPy"):
                release_contract.validate_contract(self._contract(), root=root)

    def test_python_support_and_patch_are_exact(self):
        cases = (
            ("supported_implementation", "PyPy", "Python support"),
            ("supported_versions", ["3.12"], "Python support"),
            ("locally_validated_patch", "3.12.1", "CPython 3.11"),
            ("locally_validated_patch", 311, "CPython 3.11"),
            ("unsupported_implementations", ["PyPy"], "exactly PyPy"),
            ("unsupported_implementations", ["PyPy", "PyPy"],
             "exactly PyPy"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                contract = self._contract()
                contract["python"][field] = value
                with self.assertRaisesRegex(
                        release_contract.ReleaseContractError, message):
                    release_contract.validate_contract(contract)
        contract = self._contract()
        contract["python"]["unknown"] = True
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "python keys"):
            release_contract.validate_contract(contract)

    def test_evidence_requires_exact_positive_run_identity(self):
        contract = self._contract()
        contract["evidence"]["implementation_commit"] = "short"
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "full commit"):
            release_contract.validate_contract(contract)
        for value in (0, True, "123"):
            with self.subTest(value=value):
                contract = self._contract()
                contract["evidence"]["ahpy_run"] = value
                with self.assertRaisesRegex(
                        release_contract.ReleaseContractError,
                        "positive run id"):
                    release_contract.validate_contract(contract)
        contract = self._contract()
        del contract["evidence"]["ci_run"]
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "evidence keys"):
            release_contract.validate_contract(contract)

    def test_platform_records_are_exact_unique_and_hosted(self):
        cases = []
        contract = self._contract()
        contract["platforms"] = "invalid"
        cases.append((contract, "must be an array"))
        contract = self._contract()
        contract["platforms"][0] = None
        cases.append((contract, "entries must be tables"))
        contract = self._contract()
        contract["platforms"][-1]["id"] = contract["platforms"][0]["id"]
        cases.append((contract, "ids must be unique"))
        contract = self._contract()
        contract["platforms"].pop()
        cases.append((contract, "ids differ"))
        contract = self._contract()
        contract["platforms"][0]["unknown"] = True
        cases.append((contract, "platforms.linux-x64-gcc keys"))
        contract = self._contract()
        contract["platforms"][0]["runner"] = "ubuntu-latest"
        cases.append((contract, "differs from the preview lane"))
        for contract, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                        release_contract.ReleaseContractError, message):
                    release_contract.validate_contract(contract)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            self._replace(
                root, release_contract.UNIVERSAL_WORKFLOW,
                "python Tools/ahpy/release_contract.py --json",
                "python Tools/ahpy/doctor.py --json",
            )
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError,
                    "not enforced by the Universal workflow"):
                release_contract.validate_contract(self._contract(), root=root)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            self._replace(
                root, release_contract.UNIVERSAL_WORKFLOW,
                "name: linux-x64-gcc", "name: missing-linux-x64-gcc")
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError,
                    "absent from the Universal workflow"):
                release_contract.validate_contract(self._contract(), root=root)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            (root / release_contract.UNIVERSAL_WORKFLOW).unlink()
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError,
                    "cannot read Universal workflow"):
                release_contract.validate_contract(self._contract(), root=root)

    def test_frontend_records_are_exact_and_scoped(self):
        contract = self._contract()
        contract["frontends"] = "invalid"
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "must be an array"):
            release_contract.validate_contract(contract)
        contract = self._contract()
        contract["frontends"][-1]["id"] = contract["frontends"][0]["id"]
        with self.assertRaisesRegex(
                release_contract.ReleaseContractError, "ids must be unique"):
            release_contract.validate_contract(contract)
        cases = (
            ("unknown", True, "keys are incomplete"),
            ("status", "planned", "invalid preview status"),
            ("name", "", "name must be a non-empty"),
            ("scope", " ", "scope must be a non-empty"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                contract = self._contract()
                contract["frontends"][0][field] = value
                with self.assertRaisesRegex(
                        release_contract.ReleaseContractError, message):
                    release_contract.validate_contract(contract)

    def test_documented_identity_and_evidence_cannot_drift(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            self._replace(
                root, release_contract.CONTRACT_DOCUMENT,
                self._contract()["evidence"]["implementation_commit"],
                "b" * 40,
            )
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError,
                    "differs from release-contract.md"):
                release_contract.validate_contract(self._contract(), root=root)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._repository_root(temp_dir)
            (root / release_contract.CONTRACT_DOCUMENT).unlink()
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError,
                    "cannot read release contract documentation"):
                release_contract.validate_contract(self._contract(), root=root)

    def test_load_contract_wraps_missing_and_invalid_toml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.toml"
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError, "cannot read"):
                release_contract.load_contract(path)
            path.write_text("{", encoding="utf8")
            with self.assertRaisesRegex(
                    release_contract.ReleaseContractError, "cannot read"):
                release_contract.load_contract(path)

    def test_cli_supports_text_json_and_fail_closed_errors(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(release_contract.main([]), 0)
        self.assertIn("aHPy release contract: valid", output.getvalue())
        self.assertIn("6 platforms, 7 frontends", output.getvalue())

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(release_contract.main(["--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "valid")

        with (
            mock.patch.object(
                release_contract, "load_contract",
                side_effect=release_contract.ReleaseContractError("invalid"),
            ),
            mock.patch("sys.stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            release_contract.main([])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
