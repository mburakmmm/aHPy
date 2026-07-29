import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import prepare_publish_dist


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
                root, "setuptools-80.9.0-py3-none-any.whl", b"setuptools"),
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
            "installed_hpy": "0.9.0",
            "installed_setuptools": "80.9.0",
        },
    }
    root.joinpath("provenance.json").write_text(
        json.dumps(report), encoding="utf8")
    root.joinpath("SHA256SUMS").write_text("evidence\n", encoding="utf8")
    return report


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
            self.assertEqual(list(root.joinpath("publish").iterdir()), [])

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


if __name__ == "__main__":
    unittest.main()
