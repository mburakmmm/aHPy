#!/usr/bin/env python3
"""Record the exact moving interpreter/HPy revision used by a nightly lane."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _distribution_direct_url(distribution):
    text = distribution.read_text("direct_url.json")
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("installed HPy direct_url.json is invalid") from error
    if not isinstance(value, dict):
        raise ValueError("installed HPy direct_url.json must be an object")
    return value


def _vcs_commit(direct_url):
    if not direct_url:
        return None
    vcs_info = direct_url.get("vcs_info")
    if not isinstance(vcs_info, dict):
        return None
    commit = vcs_info.get("commit_id")
    return commit if isinstance(commit, str) else None


def _repository_commit(root=ROOT):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root,
        check=True, capture_output=True, text=True)
    commit = result.stdout.strip()
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("repository HEAD is not a full Git commit")
    return commit


def _validate_requested_python(requested, actual):
    requested_release = requested.removesuffix("-dev")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", requested_release):
        raise ValueError("requested Python must use X.Y, X.Y.Z, or X.Y-dev")
    if actual != requested_release and not actual.startswith(requested_release + "."):
        raise ValueError(
            "actual Python %s does not match requested %s" % (actual, requested))


def _validate_hpy_source(direct_url, expected_url, expected_ref):
    actual_url = direct_url.get("url") if direct_url else None
    vcs_info = direct_url.get("vcs_info") if direct_url else None
    actual_ref = vcs_info.get("requested_revision") if isinstance(vcs_info, dict) else None
    if actual_url != expected_url:
        raise ValueError(
            "installed HPy URL %r does not match %r" % (actual_url, expected_url))
    if actual_ref != expected_ref:
        raise ValueError(
            "installed HPy ref %r does not match %r" % (actual_ref, expected_ref))


def collect_environment(lane, requested_python, require_hpy_vcs=False,
                        expected_hpy_url=None, expected_hpy_ref=None,
                        distribution=None, repository_commit=None,
                        python_version=None):
    if lane not in ("interpreter", "hpy"):
        raise ValueError("nightly lane must be interpreter or hpy")
    if distribution is None:
        distribution = importlib.metadata.distribution("hpy")
    direct_url = _distribution_direct_url(distribution)
    commit = _vcs_commit(direct_url)
    actual_python = python_version or platform.python_version()
    _validate_requested_python(requested_python, actual_python)
    if require_hpy_vcs and not COMMIT_PATTERN.fullmatch(commit or ""):
        raise ValueError(
            "HPy branch-tip lane requires a full VCS commit in direct_url.json")
    if require_hpy_vcs:
        if not expected_hpy_url or not expected_hpy_ref:
            raise ValueError("HPy branch-tip lane requires expected URL and ref")
        _validate_hpy_source(direct_url, expected_hpy_url, expected_hpy_ref)
    if repository_commit is None:
        repository_commit = _repository_commit()
    return {
        "schema_version": 1,
        "lane": lane,
        "support_status": "allowed-failure-early-warning",
        "requested_python": requested_python,
        "python": {
            "implementation": platform.python_implementation(),
            "version": actual_python,
            "executable": sys.executable,
            "cache_tag": sys.implementation.cache_tag,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "hpy": {
            "version": distribution.version,
            "direct_url": direct_url,
            "vcs_commit": commit,
        },
        "ahpy": {
            "commit": repository_commit,
            "github_sha": os.environ.get("GITHUB_SHA"),
        },
    }


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=("interpreter", "hpy"), required=True)
    parser.add_argument("--requested-python", required=True)
    parser.add_argument("--require-hpy-vcs", action="store_true")
    parser.add_argument("--expected-hpy-url")
    parser.add_argument("--expected-hpy-ref")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = collect_environment(
            args.lane, args.requested_python,
            require_hpy_vcs=args.require_hpy_vcs,
            expected_hpy_url=args.expected_hpy_url,
            expected_hpy_ref=args.expected_hpy_ref)
    except (ValueError, importlib.metadata.PackageNotFoundError,
            subprocess.CalledProcessError) as error:
        parser.error(str(error))
    write_report(report, args.output)
    print(
        "Nightly evidence: lane=%s python=%s hpy=%s commit=%s" %
        (report["lane"], report["python"]["version"],
         report["hpy"]["version"], report["hpy"]["vcs_commit"] or "release"))


if __name__ == "__main__":
    main()
