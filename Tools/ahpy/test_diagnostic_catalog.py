import json
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
