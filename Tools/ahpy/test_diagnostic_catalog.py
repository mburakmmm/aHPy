import ast
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import build_diagnostic_catalog
from build_diagnostic_catalog import build_catalog


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs" / "ahpy" / "audits" / "diagnostics-catalog.json"


class DiagnosticCatalogTest(unittest.TestCase):
    def test_catalog_is_complete_unique_and_current(self):
        generated = build_catalog(ROOT)
        committed = json.loads(CATALOG.read_text(encoding="utf8"))
        self.assertEqual(generated, committed)
        self.assertGreaterEqual(generated["diagnostic_count"], 120)
        identifiers = [entry["id"] for entry in generated["diagnostics"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for entry in generated["diagnostics"]:
            self.assertTrue(entry["message_template"])
            self.assertTrue(entry["migration_action"]["id"])

    def test_message_expression_normalizes_supported_template_shapes(self):
        expressions = {
            "'left' + 'right'": "leftright",
            "'value %s' % name": "value %s",
            "f'prefix {name} suffix'": "prefix {expression} suffix",
            "name": "name",
        }
        for source, expected in expressions.items():
            with self.subTest(source=source):
                node = ast.parse(source, mode="eval").body
                self.assertEqual(
                    build_diagnostic_catalog._message_expression(node, source),
                    expected,
                )

    def test_catalog_source_selects_unsupported_and_prefixed_errors(self):
        source = (
            "def collect(node):\n"
            "    node.unsupported('generic iteration is not implemented')\n"
            "    error(node.pos, 'aHPy bootstrap backend: set construction')\n"
            "    error(node.pos, 'ordinary compiler error')\n"
            "    ignored()\n"
        )
        with TemporaryDirectory(prefix="ahpy-diagnostic-catalog-") as temp:
            root = Path(temp)
            path = root / "sample.py"
            path.write_text(source, encoding="utf8")
            entries = build_diagnostic_catalog.catalog_source(
                root, "sample.py")
        self.assertEqual(len(entries), 2)
        self.assertEqual([entry["line"] for entry in entries], [2, 3])
        self.assertEqual(entries[0]["source"], "sample.py")
        self.assertEqual(
            entries[0]["migration_action"]["id"],
            "unsupported-source-node",
        )
        self.assertEqual(
            entries[1]["migration_action"]["id"],
            "set-construction",
        )

    def test_main_checks_writes_and_prints_canonical_catalog(self):
        catalog = {
            "schema_version": 1,
            "diagnostic_count": 0,
            "diagnostics": [],
        }
        rendered = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
        with TemporaryDirectory(prefix="ahpy-diagnostic-main-") as temp:
            root = Path(temp)
            expected = root / "catalog.json"
            output = root / "output.json"
            expected.write_text(rendered, encoding="utf8")

            with (
                mock.patch.object(sys, "argv", [
                    "build_diagnostic_catalog.py", "--check", str(expected)]),
                mock.patch.object(
                    build_diagnostic_catalog, "build_catalog",
                    return_value=catalog),
            ):
                self.assertEqual(build_diagnostic_catalog.main(), 0)

            expected.write_text("stale\n", encoding="utf8")
            with (
                mock.patch.object(sys, "argv", [
                    "build_diagnostic_catalog.py", "--check", str(expected)]),
                mock.patch.object(
                    build_diagnostic_catalog, "build_catalog",
                    return_value=catalog),
                mock.patch.object(sys, "stderr"),
            ):
                self.assertEqual(build_diagnostic_catalog.main(), 1)

            with (
                mock.patch.object(sys, "argv", [
                    "build_diagnostic_catalog.py", "--output", str(output)]),
                mock.patch.object(
                    build_diagnostic_catalog, "build_catalog",
                    return_value=catalog),
            ):
                self.assertEqual(build_diagnostic_catalog.main(), 0)
            self.assertEqual(output.read_text(encoding="utf8"), rendered)

            with (
                mock.patch.object(sys, "argv", ["build_diagnostic_catalog.py"]),
                mock.patch.object(
                    build_diagnostic_catalog, "build_catalog",
                    return_value=catalog),
                mock.patch.object(sys, "stdout") as stdout,
            ):
                self.assertEqual(build_diagnostic_catalog.main(), 0)
            stdout.write.assert_called_once_with(rendered)

            with (
                mock.patch.object(sys, "argv", [
                    "build_diagnostic_catalog.py",
                    "--check", str(expected), "--output", str(output)]),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                build_diagnostic_catalog.main()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
