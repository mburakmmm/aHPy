import json
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
    "release-tags",
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

    def test_selective_workflows_publish_stable_required_aggregates(self):
        contracts = {
            ".github/workflows/benchmarks.yml": (
                "benchmarks-success",
                {"file-changes", "benchmarks"},
                "benchmark required checks",
            ),
            ".github/workflows/coverage.yml": (
                "coverage-success",
                {"file-changes", "pycoverage", "cycoverage"},
                "coverage required checks",
            ),
        }
        for path, (job, dependencies, check_name) in contracts.items():
            text = (ROOT / path).read_text(encoding="utf8")
            triggers = text.split("\nconcurrency:", 1)[0]
            blocks = workflow_job_blocks(text)
            block = blocks[job]
            with self.subTest(workflow=path):
                self.assertNotIn("\n    paths:", triggers)
                self.assertIn("file-changes", blocks)
                self.assertIn("contents: read", blocks["file-changes"])
                self.assertIn("pull-requests: read", blocks["file-changes"])
                self.assertEqual(
                    set(re.findall(
                        r"(?m)^    needs: \[(.+)\]", block)[0].split(", ")),
                    dependencies,
                )
                self.assertIn(f"name: {check_name}", block)
                self.assertIn("if: always()", block)
                self.assertIn(
                    "contains(needs.*.result, 'failure')", block)
                self.assertIn(
                    "contains(needs.*.result, 'cancelled')", block)

    def test_repository_ruleset_matches_ci_policy(self):
        ruleset = json.loads(
            (ROOT / ".github" / "rulesets" / "production-branches.json")
            .read_text(encoding="utf8")
        )
        policy = load_policy()["branch_policy"]
        self.assertEqual(ruleset["enforcement"], "active")
        self.assertEqual(ruleset["bypass_actors"], [])
        self.assertEqual(
            ruleset["conditions"]["ref_name"],
            {
                "include": [
                    f"refs/heads/{branch}"
                    for branch in policy["protected_branches"]
                ],
                "exclude": [],
            },
        )
        rules = {rule["type"]: rule for rule in ruleset["rules"]}
        self.assertEqual(
            set(rules),
            {
                "deletion",
                "non_fast_forward",
                "pull_request",
                "required_status_checks",
            },
        )
        pull_request = rules["pull_request"]["parameters"]
        self.assertEqual(pull_request["required_approving_review_count"], 0)
        self.assertTrue(pull_request["required_review_thread_resolution"])
        status_checks = rules["required_status_checks"]["parameters"]
        self.assertTrue(status_checks["do_not_enforce_on_create"])
        self.assertTrue(status_checks["strict_required_status_checks_policy"])
        self.assertEqual(
            [
                check["context"]
                for check in status_checks["required_status_checks"]
            ],
            policy["required_status_contexts"],
        )
        self.assertEqual(
            {
                check["integration_id"]
                for check in status_checks["required_status_checks"]
            },
            {policy["required_status_integration_id"]},
        )
        workflow_source = "\n".join(
            (ROOT / entry["path"]).read_text(encoding="utf8")
            for entry in load_policy()["workflows"]
        )
        for context in policy["required_status_contexts"]:
            self.assertTrue(
                f"name: {context}" in workflow_source
                or f"\n  {context}:" in workflow_source,
                context,
            )

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
