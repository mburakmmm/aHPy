import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import portability_smoke


class PortabilitySmokeTest(unittest.TestCase):
    def test_manifest_verification_rejects_changed_binary(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "demo.hpy0.so"
            binary.write_bytes(b"binary")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            manifest = {
                "builder": "CPython 3.11",
                "files": [{
                    "name": binary.name,
                    "size": binary.stat().st_size,
                    "sha256": digest,
                }],
            }
            (root / "artifact-manifest.json").write_text(
                json.dumps(manifest), encoding="utf8")
            self.assertEqual(
                portability_smoke.verify_manifest(root), manifest)
            binary.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "size mismatch"):
                portability_smoke.verify_manifest(root)

    def test_native_directory_excludes_cpython_loader_stubs(self):
        with TemporaryDirectory() as source_temp, TemporaryDirectory() as dest_temp:
            source = Path(source_temp)
            destination = Path(dest_temp)
            (source / "demo.hpy0.so").write_bytes(b"binary")
            (source / "demo.py").write_text("raise AssertionError\n")
            manifest = {
                "files": [
                    {"name": "demo.hpy0.so"},
                    {"name": "demo.py"},
                ],
            }
            self.assertEqual(
                portability_smoke.prepare_native_directory(
                    source, manifest, destination),
                ["demo.hpy0.so"],
            )
            self.assertTrue((destination / "demo.hpy0.so").is_file())
            self.assertFalse((destination / "demo.py").exists())

    @mock.patch.object(portability_smoke.importlib.util, "find_spec")
    def test_loader_detection_fails_closed_to_native(self, find_spec):
        find_spec.side_effect = ModuleNotFoundError("hpy")
        self.assertFalse(portability_smoke.has_python_hpy_loader())
        find_spec.side_effect = None
        find_spec.return_value = object()
        self.assertTrue(portability_smoke.has_python_hpy_loader())

    @mock.patch.object(
        portability_smoke, "has_python_hpy_loader", return_value=True)
    def test_pypy_and_graalpy_prefer_native_importers(self, _has_loader):
        for implementation in ("PyPy", "GraalVM"):
            with self.subTest(implementation=implementation):
                with mock.patch.object(
                    portability_smoke.platform,
                    "python_implementation",
                    return_value=implementation,
                ):
                    self.assertEqual(
                        portability_smoke.select_loader_mode(), "native")

    @mock.patch.object(
        portability_smoke.platform,
        "python_implementation",
        return_value="CPython",
    )
    @mock.patch.object(portability_smoke, "has_python_hpy_loader")
    def test_cpython_requires_the_python_loader(self, has_loader, _implementation):
        has_loader.return_value = True
        self.assertEqual(portability_smoke.select_loader_mode(), "python-stub")
        has_loader.return_value = False
        self.assertEqual(portability_smoke.select_loader_mode(), "native")


if __name__ == "__main__":
    unittest.main()
