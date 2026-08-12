from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from release_evidence import (
    artifact_records,
    checksum_manifest,
    evidence_documents,
    license_inventory,
    spdx_document,
    validate_release_bundle_evidence,
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
                "cython_base_commit": (
                    "b99cb0e3b5425e11414cadd24168a6cc850e8000"),
                "build_frontend_version": "1.5.0",
                "installed_hpy": "0.9.0",
                "installed_setuptools": "83.0.0",
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
            self.assertEqual(len(spdx["packages"]), 7)
            self.assertEqual(
                {package["name"] for package in spdx["packages"]},
                {
                    "aHPy-compiler", "ahpy-pep517-example", "build",
                    "Cython", "hpy", "setuptools",
                },
            )
            self.assertTrue(any(
                relation["relationshipType"] == "CONTAINS" and
                relation["relatedSpdxElement"] == "SPDXRef-Embedded-Cython"
                for relation in spdx["relationships"]
            ))
            self.assertTrue(any(
                relation["relationshipType"] == "BUILD_TOOL_OF"
                for relation in spdx["relationships"]
            ))
            self.assertEqual(
                {package["licenseDeclared"] for package in spdx["packages"]},
                {"Apache-2.0", "MIT"},
            )
            inventory = license_inventory(report)
            self.assertEqual(inventory["schema_version"], 2)
            self.assertEqual(inventory["source_commit"], self.source_commit)
            self.assertEqual(
                {component["name"] for component in inventory["components"]},
                {
                    "aHPy-compiler",
                    "ahpy-pep517-example",
                    "build",
                    "Cython",
                    "hpy",
                    "setuptools",
                },
            )
            cython = next(
                component for component in inventory["components"]
                if component["name"] == "Cython")
            self.assertEqual(
                cython["provenance"]["revision"],
                "b99cb0e3b5425e11414cadd24168a6cc850e8000",
            )
            self.assertEqual(len(cython["provenance"]["artifacts"]), 2)
            unknown = deepcopy(report)
            unknown["build_dependencies"][0]["name"] = "unknown-1.whl"
            with self.assertRaisesRegex(ValueError, "unclassified"):
                spdx_document(unknown)

    def test_license_inventory_rejects_incomplete_build_provenance(self):
        with TemporaryDirectory() as temp_dir:
            _, report = self.make_artifacts(temp_dir)
            for field, value in (
                    ("source_commit", "short"),
                    ("cython_base_commit", "0" * 40),
                    ("build_frontend_version", "0"),
                    ("installed_hpy", "0"),
                    ("installed_setuptools", "0")):
                with self.subTest(field=field):
                    invalid = deepcopy(report)
                    invalid["provenance"][field] = value
                    with self.assertRaises((ValueError, RuntimeError)):
                        license_inventory(invalid)
            invalid = deepcopy(report)
            invalid["provenance"] = None
            with self.assertRaisesRegex(ValueError, "lacks build provenance"):
                license_inventory(invalid)

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
            self.assertTrue(validate_release_bundle_evidence(bundle, report))
            self.assertEqual(
                bundle.joinpath("licenses.json").read_text(encoding="utf8"),
                evidence_documents(report)["licenses.json"],
            )
            bundle.joinpath(paths[0].name).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                validate_release_bundle_evidence(bundle, report)
            paths[0].write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                write_release_bundle(root / "mismatch", report, paths)
            with self.assertRaisesRegex(ValueError, "must be empty"):
                write_release_bundle(bundle, report, paths)
            with self.assertRaisesRegex(ValueError, "set does not match"):
                write_release_bundle(root / "incomplete", report, paths[:-1])

    def test_bundle_validator_rejects_missing_or_changed_evidence(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = root / "sources"
            sources.mkdir()
            paths, report = self.make_artifacts(sources)
            bundle = root / "bundle"
            write_release_bundle(bundle, report, paths)
            bundle.joinpath("licenses.json").write_text(
                "{}\n", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "evidence mismatch"):
                validate_release_bundle_evidence(bundle, report)
            bundle.joinpath("licenses.json").unlink()
            with self.assertRaisesRegex(ValueError, "lacks required evidence"):
                validate_release_bundle_evidence(bundle, report)


if __name__ == "__main__":
    unittest.main()
