import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest import mock

import documentation_contract as contract


class DocumentationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tomllib.loads(
            contract.DEFAULT_CONTRACT.read_text(encoding="utf8"))

    def test_repository_contract_covers_all_audiences_and_links(self):
        report = contract.load_contract()
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["document_count"], 28)
        self.assertGreaterEqual(report["local_link_count"], 70)
        self.assertEqual(report["categories"], {
            "architecture": 6,
            "contributor": 4,
            "debugging": 4,
            "release": 6,
            "user": 8,
        })
        self.assertEqual(
            {item["path"] for item in report["documents"]},
            contract.REQUIRED_PATHS)
        module_state = next(
            item for item in report["documents"]
            if item["id"] == "module-state")
        self.assertTrue(module_state["indexed"])
        workflow = (
            contract.ROOT / ".github" / "workflows" / "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Validate production documentation contract", workflow)
        self.assertIn("Tools/ahpy/documentation_contract.py", workflow)
        self.assertIn("packaging-results/documentation-contract.json", workflow)

    def test_contract_shape_and_document_records_fail_closed(self):
        mutations = []
        data = copy.deepcopy(self.data)
        data.pop("status")
        mutations.append((data, "keys mismatch"))
        for field, value, message in (
                ("schema_version", 2, "unsupported schema"),
                ("status", "stable", "must remain preview"),
                ("categories", list(reversed(contract.CATEGORIES)),
                 "categories must be exact"),
                ("documents", [], "non-empty array")):
            data = copy.deepcopy(self.data)
            data[field] = value
            mutations.append((data, message))

        for field, value, message in (
                ("id", "Not Valid", "lowercase kebab-case"),
                ("category", "operator", "unknown category"),
                ("path", "/absolute.md", "stay inside"),
                ("indexed", 1, "must be boolean"),
                ("required_headings", [], "unique strings")):
            data = copy.deepcopy(self.data)
            data["documents"][0][field] = value
            mutations.append((data, message))
        data = copy.deepcopy(self.data)
        data["documents"][0]["unknown"] = True
        mutations.append((data, "keys mismatch"))
        data = copy.deepcopy(self.data)
        data["documents"][1]["id"] = data["documents"][0]["id"]
        mutations.append((data, "duplicate document id"))
        data = copy.deepcopy(self.data)
        data["documents"][1]["path"] = data["documents"][0]["path"]
        mutations.append((data, "duplicate document path"))
        data = copy.deepcopy(self.data)
        data["documents"][0]["required_headings"] = ["missing heading"]
        mutations.append((data, "missing required headings"))
        data = copy.deepcopy(self.data)
        data["documents"].pop()
        mutations.append((data, "document path set mismatch"))

        for data, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(
                    contract.DocumentationContractError, message):
                contract.validate_contract(data)

    def test_helpers_reject_unsafe_paths_and_broken_links(self):
        with self.assertRaisesRegex(
                contract.DocumentationContractError, "must be a table"):
            contract._exact_keys([], {"field"}, "record")
        for value in (None, "../outside.md", "/absolute.md"):
            with self.subTest(value=value), self.assertRaises(
                    contract.DocumentationContractError):
                contract._safe_path(value, "document")

        with TemporaryDirectory(prefix="ahpy-document-links-") as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            docs.mkdir()
            target = docs / "target.md"
            target.write_text("# Target\n", encoding="utf8")
            folder = docs / "folder"
            folder.mkdir()
            source = docs / "source.md"
            source.write_text(
                "# Source\n"
                "[target](target.md#section)\n"
                "[angle](<target.md>)\n"
                "![image](target.md \"title\")\n"
                "[directory](folder/)\n"
                "[fragment](#local)\n"
                "[external](https://example.com)\n"
                "[mail](mailto:test@example.com)\n"
                "[custom](vscode://example/path)\n"
                "[network](//example.com/path)\n",
                encoding="utf8")
            targets = contract._validate_local_links(source, root)
            self.assertEqual(targets, {target.resolve(), folder.resolve()})
            self.assertTrue(contract._is_indexed(target.resolve(), targets))
            nested = folder / "nested.md"
            self.assertTrue(contract._is_indexed(nested.resolve(), targets))
            self.assertFalse(contract._is_indexed(
                (docs / "unlisted.md").resolve(), targets))

            with TemporaryDirectory(
                    prefix="ahpy-outside-root-", dir=root.parent
            ) as outside_dir:
                outside = Path(outside_dir) / "outside.md"
                outside.write_text("# Outside\n", encoding="utf8")
                symlink = docs / "outside.md"
                try:
                    symlink.symlink_to(outside)
                except OSError:
                    pass
                else:
                    escaped = copy.deepcopy(self.data)
                    original = escaped["documents"][0]["path"]
                    escaped["documents"][0]["path"] = "docs/outside.md"
                    escaped_paths = set(contract.REQUIRED_PATHS)
                    escaped_paths.remove(original)
                    with mock.patch.object(
                            contract, "REQUIRED_PATHS", escaped_paths | {
                                "docs/outside.md",
                            }), self.assertRaisesRegex(
                                contract.DocumentationContractError,
                                "path escapes repository"):
                        contract.validate_contract(escaped, root=root)

            for link, message in (
                    ("[broken](missing.md)", "broken local link"),
                    ("[absolute](/tmp/outside)", "must be relative"),
                    ("[escape](../../outside.md)", "escapes repository"),
                    ("[empty](?query)", "empty local link")):
                source.write_text("# Source\n" + link, encoding="utf8")
                with self.subTest(link=link), self.assertRaisesRegex(
                        contract.DocumentationContractError, message):
                    contract._validate_local_links(source, root)

    def test_missing_files_unindexed_docs_and_external_contract_labels_fail(self):
        with TemporaryDirectory(prefix="ahpy-document-root-") as temp_dir:
            with self.assertRaisesRegex(
                    contract.DocumentationContractError, "file is missing"):
                contract.validate_contract(self.data, root=Path(temp_dir))

        data = copy.deepcopy(self.data)
        index = next(
            item for item in data["documents"]
            if item["id"] == "project-contract")
        index["indexed"] = True
        with self.assertRaisesRegex(
                contract.DocumentationContractError, "index does not link"):
            contract.validate_contract(data)

        report = contract.validate_contract(
            self.data, source="/outside/documentation-contract.toml")
        self.assertEqual(
            report["contract"], "/outside/documentation-contract.toml")

    def test_loader_and_cli_emit_schema_versioned_evidence(self):
        with TemporaryDirectory(prefix="ahpy-document-contract-") as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(
                    contract.DocumentationContractError, "cannot read"):
                contract.load_contract(root / "missing.toml")
            broken = root / "broken.toml"
            broken.write_text("schema = [", encoding="utf8")
            with self.assertRaisesRegex(
                    contract.DocumentationContractError, "cannot read"):
                contract.load_contract(broken)

            output = root / "nested" / "documentation.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(contract.main([]), 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "valid")
            self.assertEqual(contract.main(["--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["document_count"], 28)

            with mock.patch.object(
                    contract, "load_contract",
                    side_effect=contract.DocumentationContractError("invalid")), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                with self.assertRaises(SystemExit):
                    contract.main([])


if __name__ == "__main__":
    unittest.main()
