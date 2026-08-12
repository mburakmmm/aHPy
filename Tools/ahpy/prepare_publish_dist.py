#!/usr/bin/env python3
"""Prepare the exact frontend files for a no-upload PyPI rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import (
    AHPY_DISTRIBUTION,
    AHPY_HPY_SUPPORTED_VERSION,
    AHPY_SETUPTOOLS_VERSION,
    AHPY_VERSION,
    source_commit,
    validate_source_commit,
)
from release_evidence import artifact_records, validate_release_bundle_evidence


REPOSITORIES = {
    "testpypi": "https://test.pypi.org/legacy/",
    "pypi": "https://upload.pypi.org/legacy/",
}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frontend_records(report):
    artifact_records(report)
    normalized = AHPY_DISTRIBUTION.lower().replace("-", "_")
    expected_names = {
        "%s-%s.tar.gz" % (normalized, AHPY_VERSION),
        "%s-%s-py3-none-any.whl" % (normalized, AHPY_VERSION),
    }
    records = [report["sdist"], report["frontend_wheel"]]
    if {record["name"] for record in records} != expected_names:
        raise ValueError(
            "publish set must be the exact frontend sdist and py3-none-any wheel"
        )
    return sorted(records, key=lambda record: record["name"])


def prepare_publish_directory(
    bundle_dir,
    publish_dir,
    *,
    repository="testpypi",
    expected_commit=None,
):
    """Copy only validated frontend distributions into an empty directory."""
    if repository not in REPOSITORIES:
        raise ValueError("unknown package repository %s" % repository)
    bundle_dir = Path(bundle_dir)
    publish_dir = Path(publish_dir)
    try:
        report = json.loads(
            bundle_dir.joinpath("provenance.json").read_text(encoding="utf8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("release bundle lacks valid provenance.json") from exc

    if report.get("schema_version") != 2:
        raise ValueError("release provenance schema must be 2")
    provenance = report.get("provenance", {})
    report_commit = validate_source_commit(provenance.get("source_commit", ""))
    if expected_commit is None:
        expected_commit = source_commit(ROOT)
    expected_commit = validate_source_commit(expected_commit)
    if report_commit != expected_commit:
        raise ValueError("release bundle does not belong to the selected source")
    if provenance.get("installed_hpy") != AHPY_HPY_SUPPORTED_VERSION:
        raise ValueError("release bundle does not use the supported HPy version")
    if provenance.get("installed_setuptools") != AHPY_SETUPTOOLS_VERSION:
        raise ValueError(
            "release bundle does not use the supported setuptools version")
    for gate in (
        "offline_install",
        "frontend_uninstall_reinstall",
        "example_uninstall_reinstall",
    ):
        if report.get(gate) is not True:
            raise ValueError("release bundle gate is not green: %s" % gate)

    validate_release_bundle_evidence(bundle_dir, report)

    records = _frontend_records(report)
    publish_dir.mkdir(parents=True, exist_ok=True)
    if any(publish_dir.iterdir()):
        raise ValueError("publish directory must be empty")
    validated_sources = []
    for record in records:
        source = bundle_dir / record["name"]
        if not source.is_file() or _sha256(source) != record["sha256"]:
            raise ValueError(
                "release bundle content mismatch for %s" % record["name"])
        validated_sources.append((record, source))

    copied = []
    for record, source in validated_sources:
        destination = publish_dir / record["name"]
        shutil.copy2(source, destination)
        copied.append({
            "name": record["name"],
            "sha256": record["sha256"],
        })
    return {
        "schema_version": 1,
        "actual_upload": False,
        "distribution": AHPY_DISTRIBUTION,
        "version": AHPY_VERSION,
        "source_commit": report_commit,
        "repository": repository,
        "repository_url": REPOSITORIES[repository],
        "files": copied,
        "excluded_bundle_files": sorted(
            path.name for path in bundle_dir.iterdir()
            if path.is_file() and path.name not in {
                record["name"] for record in records
            }
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--publish-dir", type=Path, required=True)
    parser.add_argument(
        "--repository", choices=sorted(REPOSITORIES), default="testpypi")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = prepare_publish_directory(
        args.bundle_dir,
        args.publish_dir,
        repository=args.repository,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf8")
    else:
        print(rendered, end="")
    print(
        "aHPy %s no-upload rehearsal passed: %s" % (
            args.repository,
            ", ".join(record["name"] for record in report["files"]),
        )
    )


if __name__ == "__main__":
    main()
