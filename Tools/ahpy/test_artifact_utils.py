from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from artifact_utils import (
    find_universal_binaries,
    require_universal_binary,
    universal_extension_suffix,
)


class ArtifactUtilsTest(unittest.TestCase):
    def test_native_suffix_contract(self):
        self.assertEqual(universal_extension_suffix("posix"), ".hpy0.so")
        self.assertEqual(universal_extension_suffix("nt"), ".hpy0.pyd")

    def test_windows_linker_sidecars_are_not_loadable_binaries(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "demo.hpy0.pyd"
            binary.touch()
            (root / "demo.hpy0.lib").touch()
            (root / "demo.hpy0.exp").touch()
            (root / "unrelated.hpy0.pyd").touch()

            self.assertEqual(
                require_universal_binary(root, "demo", os_name="nt"),
                binary,
            )
            self.assertEqual(
                find_universal_binaries(root, os_name="nt"),
                [binary, root / "unrelated.hpy0.pyd"],
            )

    def test_module_basename_and_exact_suffix_are_required(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "package" / "demo.hpy0.so"
            binary.parent.mkdir()
            binary.touch()
            (binary.parent / "demo-extra.hpy0.so").touch()
            (binary.parent / "demo.hpy0.so.debug").touch()

            self.assertEqual(
                require_universal_binary(root, "package.demo", os_name="posix"),
                binary,
            )

    def test_invalid_suffix_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must start with .hpy0"):
            find_universal_binaries(".", extension_suffix=".so")

    def test_required_binary_rejects_missing_and_ambiguous_artifacts(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(AssertionError, "expected one demo"):
                require_universal_binary(root, "demo", os_name="posix")
            (root / "demo.hpy0.so").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "demo.hpy0.so").touch()
            with self.assertRaisesRegex(AssertionError, "got"):
                require_universal_binary(root, "demo", os_name="posix")


if __name__ == "__main__":
    unittest.main()
