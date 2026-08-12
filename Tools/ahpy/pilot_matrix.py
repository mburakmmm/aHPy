#!/usr/bin/env python3
"""Validate and summarize the reproducible aHPy third-party pilot matrix."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tomllib
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "tests" / "ahpy" / "pilots.toml"
SCHEMA_VERSION = 1
CATEGORIES = (
    "pure-cython",
    "external-c",
    "extension-type-gc-inheritance",
    "cpython-numpy-blocked",
)
STATUSES = {"compatible", "rejected", "compiler-error"}
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SPDX_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*\Z")
DIAGNOSTIC_EXPECTATION_RE = re.compile(
    r"(?P<path>[^:]+):(?P<line>[1-9][0-9]*):"
    r"(?P<column>[1-9][0-9]*):(?P<action>[a-z0-9]+(?:-[a-z0-9]+)*)\Z")


class ManifestError(ValueError):
    """The pilot manifest violates the fail-closed schema."""


@dataclass(frozen=True)
class Pilot:
    id: str
    category: str
    project: str
    repository: str
    commit: str
    upstream_version: str
    license_spdx: str
    license_file: str
    source_paths: tuple[str, ...]
    expected_initial_status: str
    expected_action_ids: tuple[str, ...]
    expected_diagnostics: tuple[str, ...]
    source_changes: tuple[str, ...]


@dataclass(frozen=True)
class PilotManifest:
    schema_version: int
    selected_at: str
    pilots: tuple[Pilot, ...]


PILOT_FIELDS = frozenset(Pilot.__dataclass_fields__)


def _require_string(record, field, pilot_id):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{pilot_id}: {field} must be a non-empty string")
    return value


def _require_string_list(record, field, pilot_id, allow_empty=False):
    value = record.get(field)
    if (not isinstance(value, list) or (not value and not allow_empty) or
            any(not isinstance(item, str) or not item.strip()
                for item in value)):
        raise ManifestError(
            f"{pilot_id}: {field} must be "
            f"{'a string array' if allow_empty else 'a non-empty string array'}")
    if len(value) != len(set(value)):
        raise ManifestError(f"{pilot_id}: {field} contains duplicates")
    return tuple(value)


def _validate_repo_path(path, field, pilot_id):
    candidate = PurePosixPath(path)
    if (candidate.is_absolute() or not candidate.parts or
            any(part in ("", ".", "..") for part in candidate.parts)):
        raise ManifestError(
            f"{pilot_id}: {field} must stay inside the upstream checkout: "
            f"{path!r}")


def _parse_pilot(record, index):
    if not isinstance(record, dict):
        raise ManifestError(f"pilots[{index}] must be a table")
    pilot_id = record.get("id", f"pilots[{index}]")
    unknown = set(record) - PILOT_FIELDS
    missing = PILOT_FIELDS - set(record)
    if unknown:
        raise ManifestError(
            f"{pilot_id}: unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ManifestError(
            f"{pilot_id}: missing fields: {', '.join(sorted(missing))}")

    strings = {
        field: _require_string(record, field, pilot_id)
        for field in (
            "id", "category", "project", "repository", "commit",
            "upstream_version", "license_spdx", "license_file",
            "expected_initial_status",
        )
    }
    source_paths = _require_string_list(
        record, "source_paths", strings["id"])
    expected_action_ids = _require_string_list(
        record, "expected_action_ids", strings["id"])
    expected_diagnostics = _require_string_list(
        record, "expected_diagnostics", strings["id"], allow_empty=True)
    source_changes = _require_string_list(
        record, "source_changes", strings["id"])

    if not ID_RE.fullmatch(strings["id"]):
        raise ManifestError(f"{strings['id']}: id must be lowercase kebab-case")
    if strings["category"] not in CATEGORIES:
        raise ManifestError(
            f"{strings['id']}: unknown category {strings['category']!r}")
    if not COMMIT_RE.fullmatch(strings["commit"]):
        raise ManifestError(
            f"{strings['id']}: commit must be an exact lowercase 40-hex SHA")
    if not SPDX_RE.fullmatch(strings["license_spdx"]):
        raise ManifestError(
            f"{strings['id']}: license_spdx must be a simple SPDX identifier")
    parsed = urlparse(strings["repository"])
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or
            not parsed.path.endswith(".git") or parsed.params or
            parsed.query or parsed.fragment):
        raise ManifestError(
            f"{strings['id']}: repository must be an HTTPS GitHub clone URL")
    if strings["expected_initial_status"] not in STATUSES:
        raise ManifestError(
            f"{strings['id']}: invalid expected_initial_status "
            f"{strings['expected_initial_status']!r}")
    _validate_repo_path(strings["license_file"], "license_file", strings["id"])
    for path in source_paths:
        _validate_repo_path(path, "source_paths", strings["id"])
    for action_id in expected_action_ids:
        if not ID_RE.fullmatch(action_id):
            raise ManifestError(
                f"{strings['id']}: invalid migration action ID {action_id!r}")
    for expectation in expected_diagnostics:
        match = DIAGNOSTIC_EXPECTATION_RE.fullmatch(expectation)
        if match is None:
            raise ManifestError(
                f"{strings['id']}: invalid expected diagnostic {expectation!r}; "
                "use path:line:column:action-id")
        path = match.group("path")
        _validate_repo_path(path, "expected_diagnostics", strings["id"])
        if path not in source_paths:
            raise ManifestError(
                f"{strings['id']}: expected diagnostic path is not selected: "
                f"{path}")
        if match.group("action") not in expected_action_ids:
            raise ManifestError(
                f"{strings['id']}: expected diagnostic action is not required: "
                f"{match.group('action')}")
    if (strings["category"] == "cpython-numpy-blocked" and
            strings["expected_initial_status"] != "rejected"):
        raise ManifestError(
            f"{strings['id']}: blocked pilot must expect rejection")

    return Pilot(
        source_paths=source_paths,
        expected_action_ids=expected_action_ids,
        expected_diagnostics=expected_diagnostics,
        source_changes=source_changes,
        **strings,
    )


def load_manifest(path=DEFAULT_MANIFEST):
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"cannot read pilot manifest {path}: {exc}") from exc
    if set(data) != {"schema_version", "selected_at", "pilots"}:
        raise ManifestError(
            "manifest must contain only schema_version, selected_at, and pilots")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported schema_version {data['schema_version']!r}; "
            f"expected {SCHEMA_VERSION}")
    selected_at = data["selected_at"]
    if (not isinstance(selected_at, str) or
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selected_at)):
        raise ManifestError("selected_at must use YYYY-MM-DD")
    records = data["pilots"]
    if not isinstance(records, list):
        raise ManifestError("pilots must be an array of tables")
    pilots = tuple(_parse_pilot(record, index)
                   for index, record in enumerate(records))
    if len(pilots) != len(CATEGORIES):
        raise ManifestError(
            f"manifest must select exactly {len(CATEGORIES)} pilots")
    ids = [pilot.id for pilot in pilots]
    if len(ids) != len(set(ids)):
        raise ManifestError("pilot IDs must be unique")
    repositories = [pilot.repository for pilot in pilots]
    if len(repositories) != len(set(repositories)):
        raise ManifestError("pilot repositories must be unique")
    categories = [pilot.category for pilot in pilots]
    if set(categories) != set(CATEGORIES) or len(categories) != len(set(categories)):
        raise ManifestError(
            "manifest must contain each required pilot category exactly once")
    return PilotManifest(SCHEMA_VERSION, selected_at, pilots)


def manifest_report(manifest, path):
    return {
        "schema_version": manifest.schema_version,
        "selected_at": manifest.selected_at,
        "manifest": str(Path(path).resolve()),
        "summary": {
            "pilots": len(manifest.pilots),
            "categories": list(CATEGORIES),
            "expected_statuses": {
                status: sum(
                    pilot.expected_initial_status == status
                    for pilot in manifest.pilots)
                for status in sorted(STATUSES)
            },
        },
        "pilots": [asdict(pilot) for pilot in manifest.pilots],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--json", action="store_true", help="emit the validated matrix as JSON")
    options = parser.parse_args(argv)
    try:
        manifest = load_manifest(options.manifest)
    except ManifestError as exc:
        parser.error(str(exc))
    report = manifest_report(manifest, options.manifest)
    if options.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(
            f"validated {len(manifest.pilots)} pinned aHPy pilots from "
            f"{options.manifest}")
        for pilot in manifest.pilots:
            print(
                f"- {pilot.id}: {pilot.commit} "
                f"({pilot.license_spdx}, {pilot.expected_initial_status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
