#!/usr/bin/env python3
"""Launch one generated-corpus process through the verified Python image."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


EXPORT_FAILURE = 97
RUNTIME_TIMEOUT = 600


def _timeout_text(value):
    if isinstance(value, bytes):
        return value.decode("utf8", "replace")
    return value or ""


def _child_command(target, original_command):
    command = list(original_command)
    if command and command[0] == "--":
        command.pop(0)
    if len(command) < 2:
        raise ValueError(
            "runtime wrapper requires the original Python and its script")
    return [str(target), *command[1:]]


def _export_command(appverif, target_name, xml_path):
    return [
        str(appverif),
        "-export", "log",
        "-for", target_name,
        "-with", "To=%s" % xml_path,
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--appverif", type=Path, required=True)
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    token = "%d-%s" % (os.getpid(), uuid.uuid4().hex)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    child = _child_command(args.target, args.command)
    environment = os.environ.copy()
    environment["AHPY_APPVERIFIER_TOKEN"] = token
    environment["AHPY_APPVERIFIER_MARKER_DIR"] = str(
        args.evidence_dir / "markers")
    environment["AHPY_APPVERIFIER_REQUIRE"] = "1"
    current_pythonpath = environment.get("PYTHONPATH")
    pythonpath = [str(args.probe_dir)]
    if current_pythonpath:
        pythonpath.append(current_pythonpath)
    environment["PYTHONPATH"] = os.pathsep.join(pythonpath)

    try:
        result = subprocess.run(
            child,
            capture_output=True,
            text=True,
            errors="replace",
            env=environment,
            timeout=RUNTIME_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(
            child,
            124,
            stdout=_timeout_text(exc.stdout),
            stderr=_timeout_text(exc.stderr) +
            "\nverified runtime exceeded %d seconds\n" % RUNTIME_TIMEOUT,
        )
    xml_path = args.evidence_dir / ("runtime-%s.xml" % token)
    export = subprocess.run(
        _export_command(args.appverif, args.target.name, xml_path),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=120,
    )
    record = {
        "schema_version": 1,
        "token": token,
        "command": child,
        "returncode": result.returncode,
        "xml": str(xml_path),
        "export_returncode": export.returncode,
        "export_stdout": export.stdout,
        "export_stderr": export.stderr,
    }
    (args.evidence_dir / ("runtime-%s.json" % token)).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    (args.evidence_dir / ("runtime-%s.stdout" % token)).write_text(
        result.stdout, encoding="utf8")
    (args.evidence_dir / ("runtime-%s.stderr" % token)).write_text(
        result.stderr, encoding="utf8")
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    if result.returncode:
        return result.returncode
    if export.returncode or not xml_path.is_file():
        sys.stderr.write(
            "AppVerifier did not export the verified runtime log.\n")
        return EXPORT_FAILURE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
