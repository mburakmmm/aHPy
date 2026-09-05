from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import verify_reproducible_artifact as reproducibility


class ReproducibleArtifactTest(unittest.TestCase):

    def test_verify_accepts_identical_file_sets_and_bytes(self):
        def build(_python, output):
            output.mkdir()
            (output / "artifact.json").write_bytes(b"stable")

        with mock.patch.object(
                reproducibility, "build_artifact", side_effect=build) as called:
            reproducibility.verify("python")
        self.assertEqual(called.call_count, 2)

    def test_verify_rejects_different_file_sets(self):
        def build(_python, output):
            output.mkdir()
            (output / ("%s.json" % output.name)).write_bytes(b"stable")

        with (
            mock.patch.object(
                reproducibility, "build_artifact", side_effect=build),
            self.assertRaisesRegex(AssertionError, "file sets differ"),
        ):
            reproducibility.verify("python")

    def test_verify_rejects_different_file_bytes(self):
        def build(_python, output):
            output.mkdir()
            (output / "artifact.json").write_bytes(output.name.encode("ascii"))

        with (
            mock.patch.object(
                reproducibility, "build_artifact", side_effect=build),
            self.assertRaisesRegex(
                AssertionError, "not reproducible: artifact.json"),
        ):
            reproducibility.verify("python")

    def test_main_accepts_an_existing_interpreter_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            argv = ["verify_reproducible_artifact.py", "--python", str(python)]
            with (
                mock.patch("sys.argv", argv),
                mock.patch.object(reproducibility, "verify") as verify,
                mock.patch("builtins.print"),
            ):
                reproducibility.main()
        verify.assert_called_once_with(os.path.abspath(python))

    def test_main_resolves_an_interpreter_from_path(self):
        argv = ["verify_reproducible_artifact.py", "--python", "ahpy-python"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                reproducibility.shutil, "which", return_value="/tool/python"),
            mock.patch.object(reproducibility, "verify") as verify,
            mock.patch("builtins.print"),
        ):
            reproducibility.main()
        verify.assert_called_once_with("/tool/python")

    def test_main_rejects_a_missing_interpreter(self):
        argv = ["verify_reproducible_artifact.py", "--python", "missing-python"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                reproducibility.shutil, "which", return_value=None),
            mock.patch("sys.stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            reproducibility.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
