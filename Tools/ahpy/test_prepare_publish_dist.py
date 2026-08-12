import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import prepare_publish_dist
from release_evidence import evidence_documents


COMMIT = "a" * 40


def _write_artifact(root, name, content):
    path = root / name
    path.write_bytes(content)
    return {
        "name": name,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _bundle(root):
    records = {
        "sdist": _write_artifact(
            root, "ahpy_compiler-3.3.0.1.dev0.tar.gz", b"sdist"),
        "frontend_wheel": _write_artifact(
            root,
            "ahpy_compiler-3.3.0.1.dev0-py3-none-any.whl",
            b"frontend",
        ),
        "example_wheel": _write_artifact(
            root,
            "ahpy_pep517_example-0.0.0-cp311-cp311-linux_x86_64.whl",
            b"example",
        ),
        "build_dependencies": [
            _write_artifact(
                root, "hpy-0.9.0-cp311-cp311-linux_x86_64.whl", b"hpy"),
            _write_artifact(
                root, "setuptools-83.0.0-py3-none-any.whl", b"setuptools"),
        ],
    }
    report = {
        "schema_version": 2,
        **records,
        "offline_install": True,
        "frontend_uninstall_reinstall": True,
        "example_uninstall_reinstall": True,
        "provenance": {
            "source_commit": COMMIT,
            "cython_base_commit": (
                "86b94cef002aa23aea0b390335ea3d9e9b62c19e"),
            "build_frontend_version": "1.5.0",
            "installed_hpy": "0.9.0",
            "installed_setuptools": "83.0.0",
        },
    }
    _write_evidence(root, report)
    return report


def _write_evidence(root, report):
    for name, content in evidence_documents(report).items():
        root.joinpath(name).write_text(content, encoding="utf8")


class PreparePublishDistTest(unittest.TestCase):

    def test_copies_only_frontend_distributions(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            publish = root / "publish"
            bundle.mkdir()
            _bundle(bundle)
            report = prepare_publish_dist.prepare_publish_directory(
                bundle, publish, expected_commit=COMMIT)
            self.assertFalse(report["actual_upload"])
            self.assertEqual(report["repository"], "testpypi")
            self.assertEqual(
                [record["name"] for record in report["files"]],
                [
                    "ahpy_compiler-3.3.0.1.dev0-py3-none-any.whl",
                    "ahpy_compiler-3.3.0.1.dev0.tar.gz",
                ],
            )
            self.assertEqual(
                sorted(path.name for path in publish.iterdir()),
                [record["name"] for record in report["files"]],
            )
            self.assertIn(
                "ahpy_pep517_example-0.0.0-cp311-cp311-linux_x86_64.whl",
                report["excluded_bundle_files"],
            )

    def test_rejects_wrong_source_commit(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            _bundle(bundle)
            with self.assertRaisesRegex(ValueError, "selected source"):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", expected_commit="b" * 40)

    def test_rejects_tampered_artifact(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            _bundle(bundle)
            bundle.joinpath(
                "ahpy_compiler-3.3.0.1.dev0.tar.gz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", expected_commit=COMMIT)
            self.assertFalse(root.joinpath("publish").exists())

    def test_rechecks_selected_file_after_bundle_validation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            report = _bundle(bundle)
            bundle.joinpath(report["sdist"]["name"]).unlink()
            with (
                mock.patch.object(
                    prepare_publish_dist,
                    "validate_release_bundle_evidence",
                    return_value=True,
                ),
                self.assertRaisesRegex(ValueError, "content mismatch"),
            ):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", expected_commit=COMMIT)

    def test_rejects_nonempty_destination(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            publish = root / "publish"
            bundle.mkdir()
            publish.mkdir()
            publish.joinpath("old.whl").write_bytes(b"old")
            _bundle(bundle)
            with self.assertRaisesRegex(ValueError, "must be empty"):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, publish, expected_commit=COMMIT)

    def test_rejects_unknown_repository(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "unknown"):
                prepare_publish_dist.prepare_publish_directory(
                    temp, Path(temp) / "publish",
                    repository="mirror", expected_commit=COMMIT)

    def test_rejects_invalid_provenance_schema_versions_and_gates(self):
        mutations = (
            (lambda report: report.update(schema_version=1), "schema must be 2"),
            (
                lambda report: report["provenance"].update(
                    installed_hpy="0.10.0"),
                "supported HPy version",
            ),
            (
                lambda report: report["provenance"].update(
                    installed_setuptools="0"),
                "supported setuptools version",
            ),
            (
                lambda report: report["provenance"].update(
                    build_frontend_version="0"),
                "build_frontend_version=1.5.0",
            ),
            (
                lambda report: report.update(offline_install=False),
                "gate is not green: offline_install",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                with TemporaryDirectory() as temp:
                    root = Path(temp)
                    bundle = root / "bundle"
                    bundle.mkdir()
                    report = _bundle(bundle)
                    mutate(report)
                    (bundle / "provenance.json").write_text(
                        json.dumps(report), encoding="utf8")
                    with self.assertRaisesRegex(ValueError, message):
                        prepare_publish_dist.prepare_publish_directory(
                            bundle, root / "publish", expected_commit=COMMIT)

        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "provenance.json").write_text(
                "not-json", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "valid provenance.json"):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", expected_commit=COMMIT)

    def test_rejects_nonfrontend_publish_identity(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            report = _bundle(bundle)
            original = bundle / report["frontend_wheel"]["name"]
            report["frontend_wheel"]["name"] = "ahpy_compiler-wrong.whl"
            original.rename(bundle / report["frontend_wheel"]["name"])
            _write_evidence(bundle, report)
            with self.assertRaisesRegex(ValueError, "exact frontend"):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", expected_commit=COMMIT)

    def test_rejects_missing_or_tampered_supply_chain_evidence(self):
        cases = (
            ("licenses.json", "{}\n", "evidence mismatch"),
            ("sbom.spdx.json", None, "lacks required evidence"),
        )
        for name, replacement, message in cases:
            with self.subTest(name=name), TemporaryDirectory() as temp:
                root = Path(temp)
                bundle = root / "bundle"
                bundle.mkdir()
                _bundle(bundle)
                path = bundle / name
                if replacement is None:
                    path.unlink()
                else:
                    path.write_text(replacement, encoding="utf8")
                with self.assertRaisesRegex(ValueError, message):
                    prepare_publish_dist.prepare_publish_directory(
                        bundle, root / "publish", expected_commit=COMMIT)

        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            report = _bundle(bundle)
            dependency = bundle / report["build_dependencies"][0]["name"]
            dependency.write_bytes(b"tampered dependency")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", expected_commit=COMMIT)

    def test_default_source_commit_and_pypi_repository_are_recorded(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            _bundle(bundle)
            with mock.patch.object(
                    prepare_publish_dist, "source_commit",
                    return_value=COMMIT) as commit:
                report = prepare_publish_dist.prepare_publish_directory(
                    bundle, root / "publish", repository="pypi")
            commit.assert_called_once_with(prepare_publish_dist.ROOT)
            self.assertEqual(report["repository"], "pypi")
            self.assertEqual(
                report["repository_url"],
                prepare_publish_dist.REPOSITORIES["pypi"],
            )

    def test_main_writes_or_prints_no_upload_report(self):
        report = {
            "files": [{"name": "frontend.whl", "sha256": "a" * 64}],
        }
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "nested" / "publish.json"
            base = [
                "prepare_publish_dist.py",
                "--bundle-dir", str(root / "bundle"),
                "--publish-dir", str(root / "publish"),
            ]
            with (
                mock.patch.object(sys, "argv", base + [
                    "--repository", "pypi", "--output", str(output)]),
                mock.patch.object(
                    prepare_publish_dist, "prepare_publish_directory",
                    return_value=report) as prepare,
                mock.patch("builtins.print") as printed,
            ):
                prepare_publish_dist.main()
            prepare.assert_called_once_with(
                root / "bundle", root / "publish", repository="pypi")
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertIn("no-upload rehearsal passed", printed.call_args.args[0])

            with (
                mock.patch.object(sys, "argv", base),
                mock.patch.object(
                    prepare_publish_dist, "prepare_publish_directory",
                    return_value=report),
                mock.patch("builtins.print") as printed,
            ):
                prepare_publish_dist.main()
            self.assertEqual(printed.call_count, 2)
            self.assertEqual(json.loads(printed.call_args_list[0].args[0]), report)


if __name__ == "__main__":
    unittest.main()
