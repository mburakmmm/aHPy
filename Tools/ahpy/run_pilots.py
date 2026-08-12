#!/usr/bin/env python3
"""Checkout pinned third-party pilots and produce fail-closed scan evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

from pilot_matrix import DEFAULT_MANIFEST, ManifestError, load_manifest
from scan_compatibility import scan_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SUFFIXES = {".py", ".pyx"}


class PilotRunError(RuntimeError):
    """Pilot infrastructure or provenance validation failed."""


def _run(command, cwd=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise PilotRunError(
            f"command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else ""))
    return result.stdout.strip()


def _git(checkout, *arguments):
    return _run(["git", "-C", str(checkout), *arguments])


def verify_checkout(pilot, checkout):
    checkout = Path(checkout)
    if not (checkout / ".git").exists():
        raise PilotRunError(f"{pilot.id}: checkout is not a Git worktree: {checkout}")
    head = _git(checkout, "rev-parse", "HEAD")
    if head != pilot.commit:
        raise PilotRunError(
            f"{pilot.id}: checkout HEAD {head!r} does not match {pilot.commit}")
    remote = _git(checkout, "remote", "get-url", "origin")
    if remote != pilot.repository:
        raise PilotRunError(
            f"{pilot.id}: origin {remote!r} does not match {pilot.repository!r}")
    dirty = _git(checkout, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise PilotRunError(f"{pilot.id}: pristine upstream checkout is dirty")
    required = (pilot.license_file, *pilot.source_paths)
    missing = [path for path in required if not (checkout / path).is_file()]
    if missing:
        raise PilotRunError(
            f"{pilot.id}: pinned checkout is missing: {', '.join(missing)}")
    return {
        "head": head,
        "origin": remote,
        "license_file": pilot.license_file,
        "source_paths": list(pilot.source_paths),
        "pristine": True,
    }


def checkout_pilot(pilot, checkout_root):
    checkout_root = Path(checkout_root)
    checkout_root.mkdir(parents=True, exist_ok=True)
    checkout = checkout_root / pilot.id
    if checkout.exists():
        return checkout, verify_checkout(pilot, checkout)
    _run(["git", "init", "--quiet", str(checkout)])
    try:
        _git(checkout, "remote", "add", "origin", pilot.repository)
        _git(checkout, "fetch", "--quiet", "--depth=1", "origin", pilot.commit)
        _git(checkout, "checkout", "--quiet", "--detach", "FETCH_HEAD")
        evidence = verify_checkout(pilot, checkout)
    except Exception:
        shutil.rmtree(checkout, ignore_errors=True)
        raise
    return checkout, evidence


def _observed_status(report):
    if report["summary"]["compiler-error"]:
        return "compiler-error"
    if report["summary"]["rejected"]:
        return "rejected"
    return "compatible"


def _diagnostic_key(checkout, diagnostic):
    raw_path = diagnostic.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    try:
        path = path.resolve().relative_to(Path(checkout).resolve())
    except ValueError:
        return None
    line = diagnostic.get("line")
    column = diagnostic.get("column")
    action_id = diagnostic.get("action", {}).get("id")
    if (not isinstance(line, int) or line <= 0 or
            not isinstance(column, int) or column <= 0 or
            not isinstance(action_id, str)):
        return None
    return f"{path.as_posix()}:{line}:{column}:{action_id}"


def scan_pilot(pilot, checkout, python=sys.executable, root=ROOT):
    sources = [
        checkout / path for path in pilot.source_paths
        if Path(path).suffix in SOURCE_SUFFIXES
    ]
    if not sources:
        raise PilotRunError(f"{pilot.id}: no Python/Cython source selected")
    report = scan_sources(python, sources, root=root)
    observed_status = _observed_status(report)
    observed_action_ids = sorted({
        diagnostic["action"]["id"]
        for source in report["sources"]
        for diagnostic in source["diagnostics"]
    })
    missing_action_ids = sorted(
        set(pilot.expected_action_ids) - set(observed_action_ids))
    observed_diagnostics = sorted(filter(None, (
        _diagnostic_key(checkout, diagnostic)
        for source in report["sources"]
        for diagnostic in source["diagnostics"]
    )))
    missing_diagnostics = sorted(
        set(pilot.expected_diagnostics) - set(observed_diagnostics))
    expectation_met = (
        observed_status == pilot.expected_initial_status and
        not missing_action_ids and
        not missing_diagnostics
    )
    return {
        "id": pilot.id,
        "category": pilot.category,
        "commit": pilot.commit,
        "expected": {
            "status": pilot.expected_initial_status,
            "required_action_ids": list(pilot.expected_action_ids),
            "required_diagnostics": list(pilot.expected_diagnostics),
        },
        "observed": {
            "status": observed_status,
            "action_ids": observed_action_ids,
            "diagnostics": observed_diagnostics,
        },
        "expectation_met": expectation_met,
        "missing_action_ids": missing_action_ids,
        "missing_diagnostics": missing_diagnostics,
        "scan": report,
    }


def run_matrix(manifest, checkout_root, python=sys.executable, root=ROOT,
               do_checkout=False, do_scan=False, generated_at=None,
               pilot_ids=None):
    if not do_checkout and not do_scan:
        raise PilotRunError("select --checkout, --scan, or both")
    checkout_root = Path(checkout_root).resolve()
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    selected = manifest.pilots
    if pilot_ids:
        requested = set(pilot_ids)
        known = {pilot.id for pilot in manifest.pilots}
        unknown = sorted(requested - known)
        if unknown:
            raise PilotRunError(
                f"unknown pilot IDs: {', '.join(unknown)}")
        selected = tuple(
            pilot for pilot in manifest.pilots if pilot.id in requested)
    pilots = []
    for pilot in selected:
        checkout = checkout_root / pilot.id
        if do_checkout:
            checkout, checkout_evidence = checkout_pilot(pilot, checkout_root)
        else:
            checkout_evidence = verify_checkout(pilot, checkout)
        result = {
            "id": pilot.id,
            "category": pilot.category,
            "checkout": str(checkout),
            "provenance": checkout_evidence,
        }
        if do_scan:
            result["initial_scan"] = scan_pilot(
                pilot, checkout, python=python, root=root)
        pilots.append(result)
    expectations_met = all(
        item.get("initial_scan", {}).get("expectation_met", True)
        for item in pilots
    )
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "backend": "hpy-universal",
        "manifest_selected_at": manifest.selected_at,
        "checkout_root": str(checkout_root),
        "expectations_met": expectations_met,
        "pilots": pilots,
    }


def _python_executable(value):
    candidate = Path(value)
    if candidate.exists():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if resolved is None:
        raise PilotRunError(f"Python interpreter not found: {value}")
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument("--checkout", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument(
        "--pilot", action="append", dest="pilot_ids",
        help="run only this exact manifest pilot ID; may be repeated")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--generated-at")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    if options.checkout_root is None:
        parser.error("--checkout-root is required")
    try:
        manifest = load_manifest(options.manifest)
        python = _python_executable(options.python)
        report = run_matrix(
            manifest,
            options.checkout_root,
            python=python,
            do_checkout=options.checkout,
            do_scan=options.scan,
            generated_at=options.generated_at,
            pilot_ids=options.pilot_ids,
        )
    except (ManifestError, PilotRunError) as exc:
        parser.error(str(exc))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(payload, encoding="utf8")
    else:
        sys.stdout.write(payload)
    return 0 if report["expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
