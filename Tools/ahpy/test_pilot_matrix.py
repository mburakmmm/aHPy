import contextlib
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

import pilot_matrix
from pilot_matrix import ManifestError, load_manifest, manifest_report


MANIFEST = Path(__file__).resolve().parents[2] / "tests" / "ahpy" / "pilots.toml"


class PilotMatrixTest(unittest.TestCase):
    def setUp(self):
        self.valid_text = MANIFEST.read_text(encoding="utf8")

    def _load_text(self, text):
        with tempfile.TemporaryDirectory(prefix="ahpy-pilots-") as temp:
            path = Path(temp) / "pilots.toml"
            path.write_text(text, encoding="utf8")
            return load_manifest(path)

    def test_repository_manifest_selects_each_required_category(self):
        manifest = load_manifest(MANIFEST)
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.selected_at, "2026-08-02")
        self.assertEqual(
            {pilot.category for pilot in manifest.pilots},
            set(pilot_matrix.CATEGORIES),
        )
        self.assertEqual(len(manifest.pilots), 4)
        self.assertTrue(all(len(pilot.commit) == 40 for pilot in manifest.pilots))
        self.assertTrue(all(pilot.source_changes for pilot in manifest.pilots))
        blocked = manifest.pilots[-1]
        self.assertEqual(blocked.expected_diagnostics, (
            "src/python/bezier/_speedup.pyx:37:1:numpy-c-api",
            "src/python/bezier/_speedup.pyx:38:1:numpy-c-api",
        ))

    def test_manifest_report_is_json_serializable_and_counts_statuses(self):
        report = manifest_report(load_manifest(MANIFEST), MANIFEST)
        payload = json.loads(json.dumps(report))
        self.assertEqual(payload["summary"]["pilots"], 4)
        self.assertEqual(payload["summary"]["expected_statuses"]["rejected"], 4)
        self.assertEqual(payload["pilots"][0]["id"], "cypack-pure-cython")

    def test_rejects_unknown_missing_and_invalid_scalar_fields(self):
        cases = (
            ("schema_version = 1", "manifest must contain only"),
            (self.valid_text.replace("schema_version = 1", "schema_version = 2", 1),
             "unsupported schema_version"),
            (self.valid_text.replace("selected_at = \"2026-08-02\"",
                                     "selected_at = \"02-08-2026\"", 1),
             "selected_at must use"),
            (self.valid_text.replace("project = \"cython-package-example\"",
                                     "project = \"cython-package-example\"\nunknown = true", 1),
             "unknown fields"),
            (self.valid_text.replace(
                "project = \"cython-package-example\"\n", "", 1),
             "missing fields"),
            (self.valid_text.replace("id = \"cypack-pure-cython\"",
                                     "id = \"Not Valid\"", 1),
             "lowercase kebab-case"),
            (self.valid_text.replace("commit = \"7dfb3905259c5c7a82770806e5e558999eef79ce\"",
                                     "commit = \"6bb54f1\"", 1),
             "40-hex SHA"),
            (self.valid_text.replace("license_spdx = \"MIT\"",
                                     "license_spdx = \"BSD 3 Clause\"", 1),
             "SPDX identifier"),
            (self.valid_text.replace("expected_initial_status = \"rejected\"",
                                     "expected_initial_status = \"pending\"", 1),
             "invalid expected_initial_status"),
        )
        for text, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                    ManifestError, message):
                self._load_text(text)

        with self.assertRaisesRegex(ManifestError, "non-empty string"):
            pilot_matrix._require_string({"field": ""}, "field", "pilot")
        with self.assertRaisesRegex(ManifestError, "must be a table"):
            pilot_matrix._parse_pilot("not-a-table", 0)

        record = tomllib.loads(self.valid_text)["pilots"][0]
        record["category"] = "unknown-category"
        with self.assertRaisesRegex(ManifestError, "unknown category"):
            pilot_matrix._parse_pilot(record, 0)

        record = tomllib.loads(self.valid_text)["pilots"][0]
        record["expected_action_ids"] = ["Not Valid"]
        with self.assertRaisesRegex(ManifestError, "migration action ID"):
            pilot_matrix._parse_pilot(record, 0)

    def test_rejects_unsafe_urls_paths_lists_and_category_shape(self):
        cases = (
            (self.valid_text.replace(
                "https://github.com/FedericoStra/cython-package-example.git",
                "git@github.com:FedericoStra/cython-package-example.git", 1),
             "HTTPS GitHub"),
            (self.valid_text.replace("license_file = \"LICENSE.txt\"",
                                     "license_file = \"../LICENSE.txt\"", 1),
             "inside the upstream checkout"),
            (self.valid_text.replace(
                'source_paths = [\n  "src/cypack/answer.pyx",\n  "src/cypack/fibonacci.pyx",\n  "src/cypack/utils.pyx",\n]',
                "source_paths = []", 1),
             "non-empty string array"),
            (self.valid_text.replace(
                '  "src/cypack/utils.pyx",\n]',
                '  "src/cypack/utils.pyx",\n  "src/cypack/utils.pyx",\n]', 1),
             "contains duplicates"),
            (self.valid_text.replace("category = \"external-c\"",
                                     "category = \"pure-cython\"", 1),
             "each required pilot category"),
            (self.valid_text.replace("id = \"murmurhash-external-c\"",
                                     "id = \"cypack-pure-cython\"", 1),
             "pilot IDs must be unique"),
            (self.valid_text.replace(
                "https://github.com/explosion/murmurhash.git",
                "https://github.com/FedericoStra/cython-package-example.git", 1),
             "pilot repositories must be unique"),
        )
        for text, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                    ManifestError, message):
                self._load_text(text)

    def test_blocked_category_must_expect_rejection(self):
        marker = "expected_initial_status = \"rejected\""
        index = self.valid_text.rfind(marker)
        text = (self.valid_text[:index] +
                "expected_initial_status = \"compatible\"" +
                self.valid_text[index + len(marker):])
        with self.assertRaisesRegex(ManifestError, "blocked pilot"):
            self._load_text(text)

    def test_expected_diagnostics_require_selected_path_and_action(self):
        exact = "src/python/bezier/_speedup.pyx:37:1:numpy-c-api"
        cases = (
            (exact.replace(":37:1:", ":zero:1:"),
             "invalid expected diagnostic"),
            (exact.replace("src/python/bezier/_speedup.pyx", "other.pyx"),
             "path is not selected"),
            (exact.replace("numpy-c-api", "python-header"),
             "action is not required"),
        )
        for replacement, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                    ManifestError, message):
                self._load_text(self.valid_text.replace(exact, replacement, 1))

    def test_read_and_toml_failures_are_actionable(self):
        with self.assertRaisesRegex(ManifestError, "cannot read pilot manifest"):
            load_manifest(Path("/does/not/exist/pilots.toml"))
        with self.assertRaisesRegex(ManifestError, "cannot read pilot manifest"):
            self._load_text("schema_version = [")
        with self.assertRaisesRegex(ManifestError, "pilots must be an array"):
            self._load_text(
                'schema_version = 1\nselected_at = "2026-08-02"\npilots = {}\n')
        shortened = self.valid_text[:self.valid_text.rfind("[[pilots]]")]
        with self.assertRaisesRegex(ManifestError, "select exactly 4 pilots"):
            self._load_text(shortened)

    def test_cli_supports_text_json_and_fail_closed_errors(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(pilot_matrix.main(["--manifest", str(MANIFEST)]), 0)
        self.assertIn("validated 4 pinned aHPy pilots", output.getvalue())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                pilot_matrix.main(["--manifest", str(MANIFEST), "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["summary"]["pilots"], 4)

        parser = mock.Mock()
        parser.error.side_effect = RuntimeError("fail closed")
        with mock.patch.object(pilot_matrix.argparse, "ArgumentParser",
                               return_value=parser):
            parser.parse_args.return_value = mock.Mock(
                manifest=Path("/missing"), json=False)
            with self.assertRaisesRegex(RuntimeError, "fail closed"):
                pilot_matrix.main([])
        parser.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
