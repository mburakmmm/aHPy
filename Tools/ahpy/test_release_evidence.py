from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from release_evidence import (
    artifact_records,
    checksum_manifest,
    license_inventory,
    spdx_document,
    write_release_bundle,
)


class ReleaseEvidenceTest(unittest.TestCase):
    source_commit = "a" * 40

    def make_artifacts(self, root):
        names = (
            "ahpy_compiler-3.3.0.1.dev0.tar.gz",
            "ahpy_compiler-3.3.0.1.dev0-py3-none-any.whl",
            "ahpy_pep517_example-0.0.0-cp311-test.whl",
            "hpy-0.9.0-cp311-test.whl",
            "setuptools-83.0.0-py3-none-any.whl",
        )
        paths = []
        records = []
        for index, name in enumerate(names):
            path = Path(root, name)
            payload = ("artifact-%d" % index).encode("ascii")
            path.write_bytes(payload)
            paths.append(path)
            records.append({
                "name": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        report = {
            "schema_version": 2,
            "provenance": {
                "source_commit": self.source_commit,
                "source_date_epoch": 1767225600,
            },
            "sdist": {**records[0], "members": 1},
            "frontend_wheel": records[1],
            "example_wheel": records[2],
            "build_dependencies": records[3:],
            "offline_install": True,
        }
        return paths, report

    def test_artifact_records_fail_closed(self):
        with TemporaryDirectory() as temp_dir:
            _, report = self.make_artifacts(temp_dir)
            self.assertEqual(len(artifact_records(report)), 5)
            invalid = deepcopy(report)
            invalid["sdist"]["sha256"] = "not-a-digest"
            with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
                artifact_records(invalid)
            duplicate = deepcopy(report)
            duplicate["frontend_wheel"]["name"] = duplicate["sdist"]["name"]
            with self.assertRaisesRegex(ValueError, "must be unique"):
                artifact_records(duplicate)
            nested = deepcopy(report)
            nested["sdist"]["name"] = "nested/artifact.tar.gz"
            with self.assertRaisesRegex(ValueError, "plain filenames"):
                artifact_records(nested)

    def test_checksum_manifest_is_sorted_and_complete(self):
        with TemporaryDirectory() as temp_dir:
            _, report = self.make_artifacts(temp_dir)
            lines = checksum_manifest(report).splitlines()
            self.assertEqual(len(lines), 5)
            self.assertEqual(
                [line.split("  ", 1)[1] for line in lines],
                sorted(record["name"] for record in artifact_records(report)),
            )

    def test_spdx_and_license_documents_freeze_release_identity(self):
        with TemporaryDirectory() as temp_dir:
            _, report = self.make_artifacts(temp_dir)
            spdx = spdx_document(report)
            self.assertEqual(spdx["spdxVersion"], "SPDX-2.3")
            self.assertIn(self.source_commit, spdx["documentNamespace"])
            self.assertEqual(len(spdx["packages"]), 5)
            self.assertEqual(
                {package["licenseDeclared"] for package in spdx["packages"]},
                {"Apache-2.0", "MIT"},
            )
            inventory = license_inventory(self.source_commit)
            self.assertEqual(inventory["source_commit"], self.source_commit)
            self.assertEqual(
                {component["name"] for component in inventory["components"]},
                {
                    "aHPy-compiler",
                    "ahpy-pep517-example",
                    "hpy",
                    "setuptools",
                },
            )
            unknown = deepcopy(report)
            unknown["build_dependencies"][0]["name"] = "unknown-1.whl"
            with self.assertRaisesRegex(ValueError, "unclassified"):
                spdx_document(unknown)

    def test_release_bundle_contains_artifacts_and_all_evidence(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = root / "sources"
            sources.mkdir()
            paths, report = self.make_artifacts(sources)
            bundle = root / "bundle"
            names = write_release_bundle(bundle, report, paths)
            self.assertEqual(
                set(names),
                {
                    *(path.name for path in paths),
                    "SHA256SUMS",
                    "licenses.json",
                    "provenance.json",
                    "sbom.spdx.json",
                },
            )
            self.assertEqual(
                bundle.joinpath("SHA256SUMS").read_text(encoding="utf8"),
                checksum_manifest(report),
            )
            self.assertEqual(
                json.loads(bundle.joinpath(
                    "provenance.json").read_text(encoding="utf8")),
                report,
            )
            paths[0].write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                write_release_bundle(root / "mismatch", report, paths)
            with self.assertRaisesRegex(ValueError, "must be empty"):
                write_release_bundle(bundle, report, paths)
            with self.assertRaisesRegex(ValueError, "set does not match"):
                write_release_bundle(root / "incomplete", report, paths[:-1])


if __name__ == "__main__":
    unittest.main()
