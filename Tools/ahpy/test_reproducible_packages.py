import hashlib
import io
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import verify_reproducible_packages


class ReproduciblePackagesTest(unittest.TestCase):
    def test_contract_fixes_epoch_and_builds_both_archive_formats(self):
        source = Path(verify_reproducible_packages.__file__).read_text(
            encoding="utf8")
        self.assertIn('"SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH', source)
        self.assertIn('"PYTHONHASHSEED": "0"', source)
        self.assertIn('"--sdist", "--wheel", "--no-isolation"', source)
        self.assertIn('"byte_identical": True', source)
        workflow = (Path(verify_reproducible_packages.__file__).parents[2] /
                    ".github" / "workflows" / "ahpy-universal.yml").read_text(
                        encoding="utf8")
        self.assertIn("verify_reproducible_packages.py", workflow)
        self.assertIn("package-reproducibility.json", workflow)

    def test_identical_directories_return_hashes_and_sizes(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            payloads = {
                "ahpy_compiler.tar.gz": b"sdist",
                "ahpy_compiler.whl": b"wheel",
            }
            for name, payload in payloads.items():
                (first / name).write_bytes(payload)
                (second / name).write_bytes(payload)

            records = verify_reproducible_packages.compare_artifact_directories(
                first, second)

            self.assertEqual(sorted(payloads), [record["name"] for record in records])
            for record in records:
                payload = payloads[record["name"]]
                self.assertEqual(len(payload), record["size"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), record["sha256"])

    def test_comparison_rejects_set_and_content_mismatches(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "only-first.whl").write_bytes(b"same")
            with self.assertRaisesRegex(AssertionError, "artifact sets differ"):
                verify_reproducible_packages.compare_artifact_directories(
                    first, second)

            (first / "only-first.whl").rename(first / "same.whl")
            (second / "same.whl").write_bytes(b"different")
            with self.assertRaisesRegex(AssertionError, "not byte-reproducible"):
                verify_reproducible_packages.compare_artifact_directories(
                    first, second)

    def test_sdist_normalization_removes_order_and_timestamp_variation(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            for path, names, mtime in (
                (first, ("package/b", "package/a"), 1),
                (second, ("package/a", "package/b"), 2),
            ):
                with tarfile.open(path, "w:gz") as archive:
                    for name in names:
                        payload = name.encode("ascii")
                        member = tarfile.TarInfo(name)
                        member.size = len(payload)
                        member.mtime = mtime
                        member.uid = mtime
                        member.gid = mtime
                        archive.addfile(member, io.BytesIO(payload))

            verify_reproducible_packages.normalize_sdist(first)
            verify_reproducible_packages.normalize_sdist(second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                self.assertEqual(
                    ["package/a", "package/b"],
                    [member.name for member in archive.getmembers()],
                )
                self.assertEqual(
                    {int(verify_reproducible_packages.SOURCE_DATE_EPOCH)},
                    {member.mtime for member in archive.getmembers()},
                )
                self.assertEqual(
                    {(0, 0, "", "")},
                    {(member.uid, member.gid, member.uname, member.gname)
                     for member in archive.getmembers()},
                )

    def test_build_once_sets_reproducible_environment_and_validates_formats(self):
        environments = []

        def fake_build(command, *, cwd=None, env=None):
            environments.append(env)
            dist = Path(command[command.index("--outdir") + 1])
            with tarfile.open(dist / "ahpy_compiler-test.tar.gz", "w:gz") as archive:
                payload = b"source"
                member = tarfile.TarInfo("package/source.py")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            (dist / "ahpy_compiler-test.whl").write_bytes(b"wheel")

        with TemporaryDirectory() as temp_dir, patch.object(
                verify_reproducible_packages, "_run", side_effect=fake_build):
            dist = verify_reproducible_packages._build_once(
                "/chosen/python", Path(temp_dir) / "build")
            self.assertEqual(
                ["ahpy_compiler-test.tar.gz", "ahpy_compiler-test.whl"],
                sorted(path.name for path in dist.iterdir()),
            )
            self.assertFalse((Path(temp_dir) / "build" / "source").exists())
        self.assertEqual("0", environments[0]["PYTHONHASHSEED"])
        self.assertEqual(
            verify_reproducible_packages.SOURCE_DATE_EPOCH,
            environments[0]["SOURCE_DATE_EPOCH"],
        )
        self.assertNotIn("HPY", environments[0])

        def incomplete_build(command, *, cwd=None, env=None):
            dist = Path(command[command.index("--outdir") + 1])
            (dist / "only.whl").write_bytes(b"wheel")

        with TemporaryDirectory() as temp_dir, patch.object(
                verify_reproducible_packages, "_run",
                side_effect=incomplete_build):
            with self.assertRaisesRegex(AssertionError, "exactly one sdist"):
                verify_reproducible_packages._build_once(
                    "/chosen/python", Path(temp_dir) / "build")

    def test_provenance_and_missing_interpreter_paths(self):
        payload = (
            '{"build":"1.5.0","implementation":"CPython",'
            '"platform":"test","python":"3.11.15",'
            '"setuptools":"80.9.0"}\n'
        )
        with patch.object(
                verify_reproducible_packages.subprocess, "check_output",
                return_value=payload) as check:
            provenance = verify_reproducible_packages._provenance("/python")
        self.assertEqual("1.5.0", provenance["build"])
        self.assertEqual(["/python", "-c"], check.call_args.args[0][:2])

        with patch.object(
                verify_reproducible_packages.shutil, "which",
                return_value=None):
            with self.assertRaisesRegex(ValueError, "interpreter not found"):
                verify_reproducible_packages.verify("missing-python")

if __name__ == "__main__":
    unittest.main()
