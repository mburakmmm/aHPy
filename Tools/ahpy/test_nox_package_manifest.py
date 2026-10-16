import copy
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import nox_package_manifest as package_manifest


SOURCE = """\
def identity(value, /):
    return value
"""


class NoxPackageManifestTest(unittest.TestCase):
    def test_repository_fixture_is_composed_byte_for_byte(self):
        root = package_manifest.ROOT
        manifest = package_manifest.build_manifest(
            root / "tests" / "ahpy" / "nox_export_source.pyx",
            "example.exports",
            "example_exports",
            "0.1.0",
            [[
                "macos-aarch64",
                "artifacts/macos-aarch64/exports.hpy0",
                root / "tests" / "ahpy" / "nox-artifact-fixture.hpy0",
            ]],
            source_root=root,
        )
        self.assertEqual(
            package_manifest.nox_manifest.canonical_manifest_bytes(manifest),
            (root / "tests" / "ahpy" /
             "nox-hpy-manifest-v1.json").read_bytes(),
        )
        workflow = (
            root / ".github" / "workflows" / "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Compose compiler and artifact NOX manifest", workflow)
        self.assertIn("Tools/ahpy/nox_package_manifest.py", workflow)

    def setUp(self):
        self.temp_dir = TemporaryDirectory(prefix="ahpy-nox-package-test-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.pyx"
        self.source.write_text(SOURCE, encoding="utf8")
        self.artifact = self.root / "module.hpy0"
        self.artifact.write_bytes(b"universal artifact\n")
        self.artifacts = [[
            "linux-x86_64", "artifacts/linux-x86_64/example.hpy0",
            str(self.artifact),
        ]]

    def build(self, **options):
        values = {
            "source": self.source,
            "module_name": "example.module",
            "package_name": "example_module",
            "package_version": "0.1.0",
            "artifacts": self.artifacts,
            "source_root": self.root,
        }
        values.update(options)
        return package_manifest.build_manifest(**values)

    def test_full_manifest_binds_compiler_source_options_and_artifact(self):
        manifest = self.build()
        self.assertEqual(manifest["module"], {
            "name": "example.module", "init_symbol": "HPyInit_module"})
        self.assertEqual(manifest["package"]["name"], "example_module")
        self.assertEqual(
            manifest["producer"]["ahpy_version"],
            package_manifest.AHPY_VERSION,
        )
        self.assertEqual(
            manifest["producer"]["cython_base"],
            package_manifest.CYTHON_BASE_COMMIT,
        )
        self.assertEqual(
            manifest["producer"]["compiler_options_digest"],
            package_manifest.compiler_options_digest("example.module"),
        )
        artifact = manifest["artifacts"][0]
        self.assertEqual(artifact["size"], self.artifact.stat().st_size)
        self.assertEqual(
            artifact["sha256"],
            hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            json.loads(package_manifest.nox_manifest.canonical_manifest_bytes(
                manifest)),
            manifest,
        )

        extra = self.root / "header.h"
        extra.write_bytes(b"header v1\n")
        changed = self.build(source_inputs=[extra])
        self.assertNotEqual(
            manifest["producer"]["source_digest"],
            changed["producer"]["source_digest"],
        )

    def test_source_and_artifact_evidence_fail_closed(self):
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "at least one source"):
            package_manifest.source_inputs_digest([], root=self.root)
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "does not exist"):
            package_manifest.source_inputs_digest(
                [self.root / "missing.pyx"], root=self.root)
        outside = Path(self.temp_dir.name).parent / "outside.pyx"
        outside.write_text(SOURCE, encoding="utf8")
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "escapes source root"):
            package_manifest.source_inputs_digest([outside], root=self.root)
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "duplicate source"):
            package_manifest.source_inputs_digest(
                [self.source, self.source], root=self.root)

        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "at least one target"):
            self.build(artifacts=[])
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "artifact does not exist"):
            package_manifest.artifact_record(
                "linux-x86_64", "artifact.hpy0", self.root / "missing")
        empty = self.root / "empty.hpy0"
        empty.touch()
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "artifact is empty"):
            package_manifest.artifact_record(
                "linux-x86_64", "artifact.hpy0", empty)
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "unsafe"):
            package_manifest.artifact_record(
                "linux-x86_64", "../artifact.hpy0", self.artifact)

    def test_analysis_and_manifest_drift_fail_closed(self):
        invalid_analyses = (
            [],
            {"protocol": package_manifest.nox_export.NOX_EXPORT_PROTOCOL},
            {
                "protocol": "future",
                "module": {}, "required_capabilities": [], "exports": [],
            },
        )
        for analysis in invalid_analyses:
            with self.subTest(analysis=analysis), mock.patch.object(
                    package_manifest.nox_export, "analyze_source",
                    return_value=analysis), self.assertRaises(
                        package_manifest.NoxPackageManifestError):
                self.build()

        analysis = package_manifest.nox_export.analyze_source(
            self.source, module_name="example.module")
        analysis["module"]["name"] = "wrong.module"
        with mock.patch.object(
                package_manifest.nox_export, "analyze_source",
                return_value=analysis), self.assertRaisesRegex(
                    package_manifest.NoxPackageManifestError, "wrong module"):
            self.build()

        with mock.patch.object(
                package_manifest, "AHPY_VERSION", ""), self.assertRaisesRegex(
                    package_manifest.NoxPackageManifestError,
                    "producer.ahpy_version"):
            self.build()

    def test_write_check_and_cli_paths_are_canonical(self):
        manifest = self.build()
        output = self.root / "nested" / "manifest.json"
        rendered = package_manifest.write_manifest(manifest, output)
        self.assertEqual(output.read_bytes(), rendered)
        self.assertEqual(
            package_manifest.write_manifest(manifest, output, check=True),
            rendered,
        )
        output.write_text("{}\n", encoding="utf8")
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "stale"):
            package_manifest.write_manifest(manifest, output, check=True)
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "cannot read"):
            package_manifest.write_manifest(
                manifest, self.root / "missing.json", check=True)

        arguments = [
            str(self.source),
            "--module-name", "example.module",
            "--package-name", "example_module",
            "--package-version", "0.1.0",
            "--source-root", str(self.root),
            "--artifact", *self.artifacts[0],
        ]
        stdout = mock.Mock()
        stdout.buffer = io.BytesIO()
        with mock.patch.object(sys, "stdout", stdout):
            self.assertEqual(package_manifest.main(arguments), 0)
        self.assertEqual(
            json.loads(stdout.buffer.getvalue())["package"]["name"],
            "example_module",
        )
        self.assertEqual(package_manifest.main(
            arguments + ["--output", str(output)]), 0)
        self.assertEqual(package_manifest.main(
            arguments + ["--output", str(output), "--check"]), 0)
        with self.assertRaises(SystemExit), mock.patch.object(
                sys, "stderr", io.StringIO()):
            package_manifest.main(arguments + ["--check"])
        with self.assertRaises(SystemExit), mock.patch.object(
                sys, "stderr", io.StringIO()):
            package_manifest.main([
                str(self.root / "missing.pyx"), *arguments[1:]])

    def test_write_rejects_invalid_manifest(self):
        manifest = copy.deepcopy(self.build())
        manifest["schema_version"] = 2
        with self.assertRaisesRegex(
                package_manifest.NoxPackageManifestError, "schema version"):
            package_manifest.write_manifest(
                manifest, self.root / "invalid.json")


if __name__ == "__main__":
    unittest.main()
