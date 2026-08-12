import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import rebase_log


class RebaseLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = rebase_log.load_log()

    def test_repository_log_matches_embedded_and_release_base(self):
        self.assertEqual(self.log["current_base"], rebase_log.CYTHON_BASE_COMMIT)
        text = rebase_log.render_text(self.log)
        self.assertIn("aHPy Cython rebase log: valid", text)
        self.assertIn("events: 1", text)
        self.assertIn("baseline accepted", text)

    def test_baseline_contract_rejects_invalid_shapes_and_values(self):
        mutations = []
        data = copy.deepcopy(self.log)
        data.pop("events")
        mutations.append(data)
        for field, value in (
                ("schema_version", 2),
                ("upstream_repository", "https://example.invalid/cython.git"),
                ("current_base", "short"),
                ("current_base", "0" * 40)):
            data = copy.deepcopy(self.log)
            data[field] = value
            mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"] = []
        mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0].pop("notes")
        mutations.append(data)
        for field, value in (
                ("sequence", 2),
                ("date", "not-a-date"),
                ("date", "2999-01-01"),
                ("kind", "merge"),
                ("from_commit", "short"),
                ("result", "pending"),
                ("strategy", ""),
                ("notes", "")):
            data = copy.deepcopy(self.log)
            data["events"][0][field] = value
            mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0]["to_commit"] = "1" * 40
        mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0]["conflicts"] = [{}]
        mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0]["validation_documents"] = []
        mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0]["validation_documents"] = ["SECURITY.md", "SECURITY.md"]
        mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0]["validation_documents"] = ["../outside"]
        mutations.append(data)
        data = copy.deepcopy(self.log)
        data["events"][0]["validation_documents"] = ["missing.md"]
        mutations.append(data)

        for data in mutations:
            with self.subTest(data=data):
                with self.assertRaises(rebase_log.RebaseLogError):
                    rebase_log.validate_log(data)

    def _transition_root(self, root, current):
        release = root / "tests" / "ahpy" / "release-contract.toml"
        release.parent.mkdir(parents=True)
        release.write_text(f'[cython]\nbase_commit = "{current}"\n', encoding="utf8")
        evidence = root / "docs" / "evidence.md"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("validated\n", encoding="utf8")
        return evidence.relative_to(root).as_posix()

    def test_rebase_transition_and_conflict_decisions_are_chained(self):
        old = "1" * 40
        new = "2" * 40
        with TemporaryDirectory(prefix="ahpy-rebase-transition-") as temp_dir:
            root = Path(temp_dir)
            evidence = self._transition_root(root, new)
            data = {
                "schema_version": 1,
                "upstream_repository": "https://github.com/cython/cython.git",
                "current_base": new,
                "events": [
                    {
                        "sequence": 1, "date": "2026-01-01", "kind": "baseline",
                        "from_commit": old, "to_commit": old,
                        "strategy": "baseline-selection", "result": "accepted",
                        "conflicts": [], "validation_documents": [evidence],
                        "notes": "baseline",
                    },
                    {
                        "sequence": 2, "date": "2026-02-01", "kind": "rebase",
                        "from_commit": old, "to_commit": new,
                        "strategy": "topic-rebase", "result": "accepted",
                        "conflicts": [{
                            "path": "Cython/Compiler/ModuleNode.py",
                            "classification": "backend-neutral",
                            "decision": "retain the neutral seam",
                        }],
                        "validation_documents": [evidence], "notes": "validated",
                    },
                ],
            }
            with mock.patch.object(rebase_log, "CYTHON_BASE_COMMIT", new):
                self.assertIs(rebase_log.validate_log(data, root=root), data)

                broken = copy.deepcopy(data)
                broken["events"][1]["from_commit"] = "3" * 40
                with self.assertRaises(rebase_log.RebaseLogError):
                    rebase_log.validate_log(broken, root=root)

                for field, value in (
                        ("path", "/absolute"),
                        ("classification", "unknown"),
                        ("decision", "")):
                    broken = copy.deepcopy(data)
                    broken["events"][1]["conflicts"][0][field] = value
                    with self.subTest(field=field), self.assertRaises(
                            rebase_log.RebaseLogError):
                        rebase_log.validate_log(broken, root=root)

                broken = copy.deepcopy(data)
                broken["events"][1]["conflicts"].append(copy.deepcopy(
                    broken["events"][1]["conflicts"][0]))
                with self.assertRaises(rebase_log.RebaseLogError):
                    rebase_log.validate_log(broken, root=root)

                broken = copy.deepcopy(data)
                broken["current_base"] = old
                with self.assertRaises(rebase_log.RebaseLogError):
                    rebase_log.validate_log(broken, root=root)

    def test_release_contract_and_log_read_failures_are_actionable(self):
        with TemporaryDirectory(prefix="ahpy-rebase-read-") as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(rebase_log.RebaseLogError, "cannot read rebase"):
                rebase_log.load_log(root / "missing.toml", root=root)
            broken = root / "broken.toml"
            broken.write_text("not = [valid", encoding="utf8")
            with self.assertRaisesRegex(rebase_log.RebaseLogError, "cannot read rebase"):
                rebase_log.load_log(broken, root=root)

            data = copy.deepcopy(self.log)
            with self.assertRaisesRegex(rebase_log.RebaseLogError, "release contract is missing"):
                rebase_log.validate_log(data, root=root)
            release = root / "tests" / "ahpy" / "release-contract.toml"
            release.parent.mkdir(parents=True)
            release.write_text("not = [valid", encoding="utf8")
            with self.assertRaisesRegex(rebase_log.RebaseLogError, "cannot read release"):
                rebase_log.validate_log(data, root=root)
            release.write_text("[other]\nvalue = 1\n", encoding="utf8")
            with self.assertRaisesRegex(rebase_log.RebaseLogError, "lacks cython"):
                rebase_log.validate_log(data, root=root)

    def test_cli_prints_text_json_and_errors(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(rebase_log.main([]), 0)
        self.assertIn("aHPy Cython rebase log: valid", stdout.getvalue())
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(rebase_log.main(["--json"]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["schema_version"], 1)
        with TemporaryDirectory(prefix="ahpy-rebase-cli-") as temp_dir:
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()):
                rebase_log.main(["--log", str(Path(temp_dir) / "missing")])


if __name__ == "__main__":
    unittest.main()
