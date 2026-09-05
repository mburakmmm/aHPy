import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import build_inventory


class BuildInventoryTest(unittest.TestCase):
    def test_classification_is_conservative(self):
        self.assertEqual(
            build_inventory.classify("PyLong_FromLong")[0],
            "directly_mappable",
        )
        self.assertEqual(
            build_inventory.classify("Py_INCREF")[0],
            "structurally_different",
        )
        self.assertEqual(
            build_inventory.classify("_PySecret_Call")[0],
            "legacy_only",
        )
        self.assertEqual(
            build_inventory.classify("PyUnreviewed_API")[0],
            "unsupported_by_validated_hpy",
        )
        self.assertEqual(
            build_inventory.classify("PyMem_Malloc")[0],
            "backend_independent_replacement",
        )

    def test_git_revision_uses_requested_repository(self):
        root = Path("/repository")
        with mock.patch.object(
            build_inventory.subprocess,
            "run",
            return_value=mock.Mock(stdout="deadbeef\n"),
        ) as run:
            self.assertEqual(build_inventory.git_revision(root), "deadbeef")
        self.assertEqual(run.call_args.args[0], ["git", "rev-parse", "HEAD"])
        self.assertEqual(run.call_args.kwargs["cwd"], root)
        self.assertTrue(run.call_args.kwargs["check"])

    @mock.patch.object(build_inventory, "git_revision", return_value="abc123")
    def test_inventory_is_deterministic_and_counts_symbols(self, _git_revision):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compiler = root / "Cython" / "Compiler"
            utility = root / "Cython" / "Utility"
            tests = root / "tests" / "run"
            compiler.mkdir(parents=True)
            utility.mkdir(parents=True)
            tests.mkdir(parents=True)
            (compiler / "Example.py").write_text(
                'x = "PyLong_FromLong(1) PyObject"\n', encoding="utf-8"
            )
            (utility / "Example.c").write_text(
                "#include <Python.h>\nPy_INCREF(value);\n"
                "#if CYTHON_AVOID_BORROWED_REFS\n#endif\n",
                encoding="utf-8",
            )
            (tests / "example.pyx").write_text(
                "#tag: run hpy_candidate\n", encoding="utf-8"
            )
            (tests / "notes.txt").write_text("not tagged\n", encoding="utf-8")
            (tests / "directory.pyx").mkdir()

            inventory = build_inventory.build_inventory(root)

        self.assertEqual(inventory["cython_revision"], "abc123")
        self.assertEqual(inventory["source_summary"]["api_symbol_count"], 2)
        self.assertEqual(
            inventory["source_summary"]["python_header_files"],
            ["Cython/Utility/Example.c"],
        )
        self.assertEqual(
            inventory["test_summary"]["tag_counts"],
            {"hpy_candidate": 1, "run": 1},
        )
        self.assertEqual(
            inventory["python_object_types"],
            [{
                "type": "PyObject",
                "occurrences": 1,
                "files": ["Cython/Compiler/Example.py"],
            }],
        )
        avoid_borrowed = next(
            item
            for item in inventory["existing_abstractions"]
            if item["marker"] == "CYTHON_AVOID_BORROWED_REFS"
        )
        self.assertEqual(avoid_borrowed["occurrences"], 1)

    def test_main_resolves_root_and_renders_sorted_json(self):
        report = {"schema_version": 1, "z": 2, "a": 1}
        stdout = io.StringIO()
        with (
            mock.patch("sys.argv", ["build_inventory.py", "--root", "."]),
            mock.patch.object(
                build_inventory, "build_inventory", return_value=report
            ) as build,
            mock.patch.object(sys, "stdout", stdout),
        ):
            build_inventory.main()
        build.assert_called_once_with(Path(".").resolve())
        self.assertEqual(json.loads(stdout.getvalue()), report)


if __name__ == "__main__":
    unittest.main()
