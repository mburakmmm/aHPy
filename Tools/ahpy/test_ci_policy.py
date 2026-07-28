import re
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "tests" / "ahpy" / "ci-policy.toml"
JOB_CATEGORIES = (
    "required_jobs",
    "mixed_required_allowed_failure_jobs",
    "allowed_failure_jobs",
    "schedule_manual_required_jobs",
    "schedule_manual_allowed_failure_jobs",
    "manual_required_jobs",
    "release_or_build_jobs",
    "upstream_only_jobs",
    "reusable_jobs",
)
TRIGGER_CLASSES = {
    "pr-main-release-schedule-manual",
    "pr-main-release-manual-label",
    "manual-or-upstream-schedule",
    "pr-main-release-manual",
    "release-schedule-manual-build-label",
    "upstream-schedule-manual-build-label",
    "reusable",
}


def load_policy():
    return tomllib.loads(POLICY_PATH.read_text(encoding="utf8"))


def workflow_job_blocks(text):
    jobs_text = text.split("\njobs:\n", 1)[1]
    matches = list(re.finditer(
        r"(?m)^  (?P<name>[A-Za-z0-9_-]+):[ \t]*$", jobs_text))
    blocks = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else None
        blocks[match.group("name")] = jobs_text[match.start():end]
    return blocks


class CIPolicyTest(unittest.TestCase):

    def test_policy_lists_every_workflow_and_job_exactly_once(self):
        policy = load_policy()
        self.assertEqual(policy["schema_version"], 1)
        entries = policy["workflows"]
        paths = [entry["path"] for entry in entries]
        actual_paths = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / ".github" / "workflows").glob("*.yml")
        )
        self.assertEqual(sorted(paths), actual_paths)
        self.assertEqual(len(paths), len(set(paths)))

        for entry in entries:
            with self.subTest(workflow=entry["path"]):
                text = (ROOT / entry["path"]).read_text(encoding="utf8")
                actual_jobs = set(workflow_job_blocks(text))
                classified = [
                    job
                    for category in JOB_CATEGORIES
                    for job in entry.get(category, ())
                ]
                self.assertEqual(len(classified), len(set(classified)))
                self.assertEqual(set(classified), actual_jobs)
                self.assertIn(entry["trigger_class"], TRIGGER_CLASSES)

    def test_failure_categories_match_workflow_contracts(self):
        for entry in load_policy()["workflows"]:
            text = (ROOT / entry["path"]).read_text(encoding="utf8")
            blocks = workflow_job_blocks(text)
            with self.subTest(workflow=entry["path"]):
                for job in entry.get("required_jobs", ()):
                    self.assertNotIn("continue-on-error:", blocks[job])
                for job in entry.get("allowed_failure_jobs", ()):
                    self.assertIn("continue-on-error: true", blocks[job])
                for job in entry.get(
                        "schedule_manual_required_jobs", ()):
                    self.assertIn("github.event_name == 'schedule'", blocks[job])
                    self.assertIn(
                        "github.event_name == 'workflow_dispatch'", blocks[job])
                    self.assertNotIn("continue-on-error:", blocks[job])
                for job in entry.get(
                        "schedule_manual_allowed_failure_jobs", ()):
                    self.assertIn("github.event_name == 'schedule'", blocks[job])
                    self.assertIn(
                        "github.event_name == 'workflow_dispatch'", blocks[job])
                    self.assertIn("continue-on-error: true", blocks[job])
                for job in entry.get(
                        "mixed_required_allowed_failure_jobs", ()):
                    self.assertIn(
                        "continue-on-error: ${{ matrix.experimental }}",
                        blocks[job],
                    )

    def test_branch_policy_matches_expensive_workflow_triggers(self):
        policy = load_policy()["branch_policy"]
        self.assertEqual(policy["topic_branch_event"], "pull_request")
        self.assertEqual(policy["push_branches"], ["main", "ahpy/**"])
        for entry in load_policy()["workflows"]:
            if not entry["trigger_class"].startswith("pr-main-release"):
                continue
            text = (ROOT / entry["path"]).read_text(encoding="utf8")
            triggers = text.split("\nconcurrency:", 1)[0]
            self.assertIn("pull_request:", triggers, entry["path"])
            self.assertRegex(
                triggers,
                re.compile(
                    r"(?m)^  push:\n"
                    r"\s+branches:\n"
                    r"\s+- main\n"
                    r'\s+- "ahpy/\*\*"$'
                ),
                entry["path"],
            )

    def test_ahpy_required_aggregate_excludes_early_warnings(self):
        entry = next(
            entry for entry in load_policy()["workflows"]
            if entry["path"] == ".github/workflows/ahpy-universal.yml"
        )
        text = (ROOT / entry["path"]).read_text(encoding="utf8")
        block = workflow_job_blocks(text)["required-success"]
        required_dependencies = {
            "compiler-and-quality",
            "stable-universal",
            "development-revision",
            "sanitizers",
            "build-portability-artifact",
        }
        needs = set(re.findall(r"(?m)^      - ([A-Za-z0-9_-]+)$", block))
        self.assertEqual(needs, required_dependencies)
        self.assertIn("if: always()", block)
        self.assertIn("contains(needs.*.result, 'failure')", block)
        self.assertIn("contains(needs.*.result, 'cancelled')", block)
        for excluded_job in (
            "cross-interpreter",
            "native-memory-valgrind",
            "native-memory-windows",
            "nightly-interpreter",
            "nightly-hpy",
        ):
            self.assertNotIn(excluded_job, block)

    def test_turkish_production_roadmap_is_outside_english_codespell(self):
        text = (ROOT / ".codespellrc").read_text(encoding="utf8")
        skip_line = next(
            line for line in text.splitlines() if line.startswith("skip = "))
        skipped_paths = {
            value.strip() for value in skip_line.removeprefix("skip = ").split(",")
        }
        self.assertIn("production-todo.md", skipped_paths)

    def test_job_level_workflow_mappings_have_no_duplicate_keys(self):
        for entry in load_policy()["workflows"]:
            text = (ROOT / entry["path"]).read_text(encoding="utf8")
            for job, block in workflow_job_blocks(text).items():
                keys = re.findall(
                    r"(?m)^    ([A-Za-z0-9_-]+):(?:[ \t].*)?$", block)
                with self.subTest(workflow=entry["path"], job=job):
                    self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
