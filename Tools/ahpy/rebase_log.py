#!/usr/bin/env python3
"""Validate the ordered Cython upstream baseline and conflict-decision log."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import CYTHON_BASE_COMMIT


DEFAULT_LOG = ROOT / "tests" / "ahpy" / "rebase-log.toml"
RELEASE_CONTRACT = ROOT / "tests" / "ahpy" / "release-contract.toml"
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
CONFLICT_CLASSES = {
    "ahpy-specific", "backend-neutral", "obsolete", "upstream-taken"}


class RebaseLogError(ValueError):
    """The upstream baseline or recorded conflict decisions are invalid."""


def _require(condition, message):
    if not condition:
        raise RebaseLogError(message)


def _keys(mapping, expected, context):
    _require(isinstance(mapping, dict), f"{context} must be a table")
    _require(set(mapping) == set(expected), f"{context} keys are incomplete or unknown")


def _safe_path(value, context):
    _require(isinstance(value, str) and value, f"{context} must be a path")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts,
             f"{context} must stay inside the repository")
    return path


def validate_log(data, root=ROOT, source="rebase log"):
    _keys(data, {"schema_version", "upstream_repository", "current_base", "events"},
          source)
    _require(data["schema_version"] == 1, f"{source}: unsupported schema")
    _require(data["upstream_repository"] == "https://github.com/cython/cython.git",
             f"{source}: upstream repository mismatch")
    _require(isinstance(data["current_base"], str) and
             COMMIT.fullmatch(data["current_base"]),
             f"{source}: current_base must be a full commit")
    _require(data["current_base"] == CYTHON_BASE_COMMIT,
             f"{source}: current_base differs from ahpy_version.py")
    release_path = Path(root) / RELEASE_CONTRACT.relative_to(ROOT)
    _require(release_path.is_file(), f"{source}: release contract is missing")
    try:
        release = tomllib.loads(release_path.read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RebaseLogError(f"{source}: cannot read release contract: {exc}") from exc
    _require(isinstance(release.get("cython"), dict) and
             isinstance(release["cython"].get("base_commit"), str),
             f"{source}: release contract lacks cython.base_commit")
    _require(release["cython"]["base_commit"] == data["current_base"],
             f"{source}: release contract base differs from rebase log")

    events = data["events"]
    _require(isinstance(events, list) and events, f"{source}: events must be non-empty")
    previous = None
    for index, event in enumerate(events, 1):
        context = f"events[{index}]"
        _keys(event, {
            "sequence", "date", "kind", "from_commit", "to_commit", "strategy",
            "result", "conflicts", "validation_documents", "notes",
        }, context)
        _require(event["sequence"] == index, f"{context}: sequence must be contiguous")
        try:
            parsed_date = date.fromisoformat(event["date"])
        except (TypeError, ValueError) as exc:
            raise RebaseLogError(f"{context}: date must be ISO-8601") from exc
        _require(parsed_date <= date.today(), f"{context}: date cannot be in the future")
        _require(event["kind"] in {"baseline", "rebase"},
                 f"{context}: unknown event kind")
        _require(all(isinstance(event[field], str) and COMMIT.fullmatch(event[field])
                     for field in ("from_commit", "to_commit")),
                 f"{context}: commits must be full lowercase hashes")
        _require(event["result"] == "accepted" and
                 isinstance(event["strategy"], str) and event["strategy"] and
                 isinstance(event["notes"], str) and event["notes"].strip(),
                 f"{context}: accepted strategy and notes are required")
        if event["kind"] == "baseline":
            _require(index == 1 and event["from_commit"] == event["to_commit"] and
                     event["strategy"] == "baseline-selection",
                     f"{context}: baseline must be the unchanged first event")
        else:
            _require(previous is not None and event["from_commit"] == previous and
                     event["to_commit"] != event["from_commit"],
                     f"{context}: rebase must continue the prior accepted base")
        conflicts = event["conflicts"]
        _require(isinstance(conflicts, list), f"{context}: conflicts must be an array")
        seen_paths = set()
        for conflict_index, conflict in enumerate(conflicts, 1):
            conflict_context = f"{context}.conflicts[{conflict_index}]"
            _keys(conflict, {"path", "classification", "decision"}, conflict_context)
            path = _safe_path(conflict["path"], f"{conflict_context}.path")
            _require(str(path) not in seen_paths, f"{context}: duplicate conflict path")
            seen_paths.add(str(path))
            _require(conflict["classification"] in CONFLICT_CLASSES and
                     isinstance(conflict["decision"], str) and
                     conflict["decision"].strip(),
                     f"{conflict_context}: classification and decision are required")
        if event["kind"] == "baseline":
            _require(not conflicts, f"{context}: baseline cannot claim conflicts")
        documents = event["validation_documents"]
        _require(isinstance(documents, list) and documents and
                 len(documents) == len(set(documents)),
                 f"{context}: validation_documents must be unique and non-empty")
        document_paths = [
            _safe_path(value, f"{context}.validation_documents")
            for value in documents]
        missing = [str(path) for path in document_paths
                   if not (Path(root) / path).is_file()]
        _require(not missing, f"{context}: missing validation documents: {', '.join(missing)}")
        previous = event["to_commit"]
    _require(previous == data["current_base"],
             f"{source}: final event does not match current_base")
    return data


def load_log(path=DEFAULT_LOG, root=ROOT):
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RebaseLogError(f"cannot read rebase log {path}: {exc}") from exc
    return validate_log(data, root=root, source=str(path))


def render_text(data):
    latest = data["events"][-1]
    return (
        "aHPy Cython rebase log: valid\n"
        f"current base: {data['current_base']}\n"
        f"events: {len(data['events'])}\n"
        f"latest: {latest['date']} {latest['kind']} {latest['result']}\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    options = parser.parse_args(argv)
    try:
        data = load_log(options.log, options.root)
    except RebaseLogError as exc:
        parser.error(str(exc))
    if options.as_json:
        json.dump(data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
