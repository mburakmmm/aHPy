#!/usr/bin/env python3
"""Run the generated Universal corpus under a strict Linux Valgrind gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from test_generated_hpy import build_and_run


ROOT = Path(__file__).resolve().parents[2]
POSITIVE_CONTROL = ROOT / "tests" / "ahpy" / "lsan_positive_control.c"
SUPPRESSION_TEMPLATE = Path(__file__).resolve().parent / "lsan.supp"
VALGRIND_ERROR_EXIT = 42


def _tool_path(name):
    return shutil.which(name)


def _compile_positive_control(cc, output):
    subprocess.run(
        [cc, "-O0", "-g", str(POSITIVE_CONTROL), "-o", str(output)],
        check=True,
    )


def _valgrind_command(valgrind, suppression_file, log_pattern=None):
    command = [
        valgrind,
        "--error-exitcode=%d" % VALGRIND_ERROR_EXIT,
        "--leak-check=full",
        "--show-leak-kinds=definite",
        "--errors-for-leak-kinds=definite",
        "--num-callers=40",
    ]
    command.append("--suppressions=%s" % suppression_file)
    if log_pattern is not None:
        command.append("--log-file=%s" % log_pattern)
    return command


def _run_valgrind_leak_check(
        valgrind, binary, suppression_file, log_pattern=None):
    command = _valgrind_command(
        valgrind, suppression_file, log_pattern=log_pattern)
    command.append(str(binary))
    return subprocess.run(command, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--build-dir",
        default=str(ROOT / "build" / "ahpy-valgrind"),
    )
    parser.add_argument(
        "--positive-control-only",
        action="store_true",
        help="exercise only the leak positive control",
    )
    parser.add_argument(
        "--suppressions",
        type=Path,
        default=SUPPRESSION_TEMPLATE,
    )
    args = parser.parse_args()

    if sys.platform == "darwin":
        print(
            "Valgrind gate requires Linux; the mixed-runtime macOS ASan lane "
            "keeps detect_leaks=0 and is not a substitute.",
            file=sys.stderr,
        )
        return 2

    valgrind = _tool_path("valgrind")
    if valgrind is None:
        print(
            "Valgrind gate cannot run: valgrind is not installed.",
            file=sys.stderr,
        )
        return 2

    build_dir = Path(args.build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    suppression_file = args.suppressions.resolve()
    if not suppression_file.is_file():
        raise FileNotFoundError(
            "Valgrind suppression file does not exist: %s" % suppression_file)
    evidence_suppression = (build_dir / "lsan.supp").resolve()
    if evidence_suppression != suppression_file:
        shutil.copy2(suppression_file, evidence_suppression)
    environment_report = {
        "schema_version": 1,
        "python": subprocess.check_output(
            [args.python, "-c", "import sys; print(sys.version)"],
            text=True,
        ).strip(),
        "python_executable": shutil.which(args.python) or args.python,
        "compiler": subprocess.check_output(
            [args.cc, "--version"], text=True).splitlines()[0],
        "valgrind": subprocess.check_output(
            [valgrind, "--version"], text=True).strip(),
        "suppression_sha256": hashlib.sha256(
            evidence_suppression.read_bytes()).hexdigest(),
        "expected_generated_runtime_logs": 5,
    }
    (build_dir / "environment.json").write_text(
        json.dumps(environment_report, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )

    binary = build_dir / "lsan_positive_control"
    _compile_positive_control(args.cc, binary)

    leak_result = _run_valgrind_leak_check(
        valgrind, binary, evidence_suppression)
    combined = leak_result.stdout + leak_result.stderr
    (build_dir / "valgrind-positive-control.log").write_text(
        combined, encoding="utf8")
    if leak_result.returncode != VALGRIND_ERROR_EXIT:
        raise RuntimeError(
            "positive-control leak was not detected through the reviewed "
            "suppression set:\n%s" % combined)
    if "definitely lost" not in combined:
        raise RuntimeError(
            "positive-control output lacked a definite-leak marker:\n%s" % combined)

    if not args.positive_control_only:
        log_pattern = (build_dir / "valgrind-generated-%p.log").resolve()
        runtime_prefix = _valgrind_command(
            valgrind,
            evidence_suppression,
            log_pattern=log_pattern,
        )
        build_and_run(args.python, runtime_prefix=runtime_prefix)
        logs = sorted(build_dir.glob("valgrind-generated-*.log"))
        if len(logs) != 5:
            raise RuntimeError(
                "expected five Valgrind runtime logs, found %d" % len(logs))

    print(
        "Valgrind gate passed: positive-control leak detected and generated "
        "Universal runtime checks reported no definite native leak."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
