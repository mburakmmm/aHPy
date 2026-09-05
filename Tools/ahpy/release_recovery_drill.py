#!/usr/bin/env python3
"""Run a local, no-publication release recovery and backport drill."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from maintenance_policy import DEFAULT_POLICY, load_policy


COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_BRANCH_RE = re.compile(r"ahpy/[0-9]+\.[0-9]+\Z")
CHANGED_PATHS = ("backend.txt", "tests/fixed_regression.txt")
FIXED_GIT_ENVIRONMENT = {
    "GIT_AUTHOR_DATE": "2026-08-12T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-08-12T00:00:00+00:00",
}


class ReleaseRecoveryError(ValueError):
    """The recovery drill or its retained report is incomplete or unsafe."""


def _require(condition, message):
    if not condition:
        raise ReleaseRecoveryError(message)


def _exact_keys(mapping, keys, context):
    _require(isinstance(mapping, dict), f"{context} must be an object")
    expected = set(keys)
    observed = set(mapping)
    _require(observed == expected, "%s keys mismatch; missing=%s unknown=%s" % (
        context,
        ",".join(sorted(expected - observed)) or "none",
        ",".join(sorted(observed - expected)) or "none",
    ))


def _run(command, cwd, environment=None):
    merged = os.environ.copy()
    if environment:
        merged.update(environment)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ReleaseRecoveryError(
            f"release drill command failed ({result.returncode}): "
            f"{' '.join(command)}: {detail}")
    return result.stdout.strip()


def _git(repo, *arguments, environment=None):
    return _run(["git", *arguments], repo, environment)


def validate_report(report, policy):
    _exact_keys(report, {
        "schema_version", "generated_at", "status", "policy_version",
        "category", "base_commit", "source_commit", "backport_commit",
        "release_branch", "topic_branch", "source_commit_named",
        "regression_test", "changed_paths", "support_contract_unchanged",
        "direct_push", "history_rewrite", "mandatory_matrix_required",
        "recovery",
    }, "release recovery report")
    _require(report["schema_version"] == 1 and report["policy_version"] ==
             policy["policy_version"], "release recovery schema mismatch")
    _require(report["status"] == "pass", "release recovery drill did not pass")
    try:
        generated_at = datetime.fromisoformat(
            report["generated_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ReleaseRecoveryError(
            "release recovery generated_at is invalid") from exc
    _require(generated_at.tzinfo is not None,
             "release recovery generated_at needs a timezone")
    for field in ("base_commit", "source_commit", "backport_commit"):
        _require(isinstance(report[field], str) and
                 COMMIT_RE.fullmatch(report[field]),
                 f"release recovery {field} must be an exact commit")
    _require(report["category"] in policy["branches"]["backport_categories"],
             "release recovery category is not backportable")
    _require(isinstance(report["release_branch"], str) and
             RELEASE_BRANCH_RE.fullmatch(report["release_branch"]),
             "release recovery branch does not match policy")
    _require(isinstance(report["topic_branch"], str) and
             report["topic_branch"].startswith(
                 policy["branches"]["topic_prefix"]),
             "release recovery topic branch does not match policy")
    _require(report["source_commit_named"] is True,
             "backport must name its source commit")
    _require(report["regression_test"] == "tests/fixed_regression.txt" and
             report["changed_paths"] == list(CHANGED_PATHS),
             "backport must carry the original regression test and exact fix")
    _require(report["support_contract_unchanged"] is True,
             "backport must not expand the support contract")
    _require(report["direct_push"] is False and
             report["history_rewrite"] is False,
             "backport must use a reviewed topic branch without rewriting")
    _require(report["mandatory_matrix_required"] is True,
             "backport must retain the mandatory matrix requirement")
    _require(report["recovery"] == policy["recovery"],
             "release recovery actions drifted from maintenance policy")
    return report


def _execute_drill(root, policy):
    repo = root / "repository"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main", "--quiet")
    _git(repo, "config", "user.name", "aHPy release drill")
    _git(repo, "config", "user.email", "release-drill@invalid.example")
    (repo / "backend.txt").write_text("baseline\n", encoding="utf8")
    (repo / "support-tier.txt").write_text(
        "preview-cpython311-hpy09\n", encoding="utf8")
    _git(repo, "add", "backend.txt", "support-tier.txt")
    _git(repo, "commit", "--quiet", "-m", "Create release baseline",
         environment=FIXED_GIT_ENVIRONMENT)
    base_commit = _git(repo, "rev-parse", "HEAD")
    release_branch = "ahpy/3.2"
    _git(repo, "branch", release_branch)

    source_branch = policy["branches"]["topic_prefix"] + "recovery-source"
    _git(repo, "switch", "--quiet", "-c", source_branch)
    (repo / "backend.txt").write_text("correctness fix\n", encoding="utf8")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "fixed_regression.txt").write_text(
        "original regression test\n", encoding="utf8")
    _git(repo, "add", "backend.txt", "tests/fixed_regression.txt")
    _git(repo, "commit", "--quiet", "-m", "Fix release correctness defect",
         environment=FIXED_GIT_ENVIRONMENT)
    source_commit = _git(repo, "rev-parse", "HEAD")

    _git(repo, "switch", "--quiet", release_branch)
    topic_branch = policy["branches"]["topic_prefix"] + "backport-correctness"
    _git(repo, "switch", "--quiet", "-c", topic_branch)
    _git(repo, "cherry-pick", "--quiet", "-x", source_commit,
         environment=FIXED_GIT_ENVIRONMENT)
    backport_commit = _git(repo, "rev-parse", "HEAD")
    message = _git(repo, "show", "-s", "--format=%B", "HEAD")
    changed_paths = _git(
        repo, "diff", "--name-only", base_commit, backport_commit).splitlines()
    support_contract_unchanged = (
        (repo / "support-tier.txt").read_text(encoding="utf8") ==
        "preview-cpython311-hpy09\n"
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "policy_version": policy["policy_version"],
        "category": "correctness",
        "base_commit": base_commit,
        "source_commit": source_commit,
        "backport_commit": backport_commit,
        "release_branch": release_branch,
        "topic_branch": topic_branch,
        "source_commit_named": source_commit in message,
        "regression_test": "tests/fixed_regression.txt",
        "changed_paths": changed_paths,
        "support_contract_unchanged": support_contract_unchanged,
        "direct_push": policy["branches"]["direct_push"],
        "history_rewrite": policy["branches"]["history_rewrite"],
        "mandatory_matrix_required": policy["recovery"][
            "backport_mandatory_matrix_required"],
        "recovery": policy["recovery"],
    }
    return validate_report(report, policy)


def run_drill(work_root=None, policy_path=DEFAULT_POLICY):
    git = shutil.which("git")
    _require(git is not None, "git executable is required for release drill")
    policy = load_policy(policy_path)
    if work_root is None:
        with TemporaryDirectory(prefix="ahpy-release-recovery-") as temp_dir:
            return _execute_drill(Path(temp_dir), policy)
    root = Path(work_root)
    root.mkdir(parents=True, exist_ok=True)
    _require(not any(root.iterdir()),
             f"release drill work root must be empty: {root}")
    return _execute_drill(root, policy)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    try:
        report = run_drill(options.work_root, options.policy)
    except (ReleaseRecoveryError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
