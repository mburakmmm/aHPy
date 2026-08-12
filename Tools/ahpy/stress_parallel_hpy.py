#!/usr/bin/env python3
"""Run independent HPy build/execution gates concurrently without orphaning them."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUNDS = 5
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_GRACE_SECONDS = 5.0
DEFAULT_POLL_SECONDS = 0.05
_FAULT_RESULT = re.compile(
    r"Generated Universal HPy module: (\d+) isolated "
    r"API/allocation fault injection cases passed"
)


@dataclass(frozen=True)
class StressCommand:
    name: str
    argv: tuple[str, ...]


def build_commands(python, fuzz_cases=48):
    python = str(python)
    return (
        StressCommand("fault", (
            python, "Tools/ahpy/test_fault_injection.py",
            "--python", python,
        )),
        StressCommand("generated", (
            python, "Tools/ahpy/test_generated_hpy.py",
            "--python", python,
        )),
        StressCommand("setuptools", (
            python, "Tools/ahpy/setuptools_integration.py",
            "--python", python,
        )),
        StressCommand("fuzz", (
            python, "Tools/ahpy/fuzz_supported_surface.py",
            "--python", python,
            "--seed", "0xA4F9", "--cases", str(fuzz_cases),
        )),
    )


def _append_flag(environment, name, flag):
    current = environment.get(name, "").strip()
    environment[name] = (current + " " + flag).strip()


def child_environment(base_environment, command_name, round_number,
                      temp_root, native_optimization):
    environment = dict(base_environment)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONWARNINGS"] = "ignore"
    environment["AHPY_STRESS_COMMAND"] = command_name
    environment["AHPY_STRESS_ROUND"] = str(round_number)
    for variable in ("TMPDIR", "TMP", "TEMP"):
        environment[variable] = str(temp_root)
    if native_optimization != "default":
        if os.name == "nt":
            flag = "/Od" if native_optimization == "0" else "/O" + native_optimization
        else:
            flag = "-O%s -g0" % native_optimization
        _append_flag(environment, "CFLAGS", flag)
        _append_flag(environment, "CXXFLAGS", flag)
    return environment


def _popen_group_kwargs():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _wait_until_exit(process, deadline, poll_seconds):
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(poll_seconds)
    return process.poll()


def terminate_process_group(process, grace_seconds=DEFAULT_GRACE_SECONDS,
                            poll_seconds=DEFAULT_POLL_SECONDS):
    if process.poll() is not None:
        return False
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False, capture_output=True, text=True)
        _wait_until_exit(
            process, time.monotonic() + grace_seconds, poll_seconds)
        if process.poll() is None:
            process.kill()
    else:
        try:
            process_group = os.getpgid(process.pid)
        except ProcessLookupError:
            return False
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            return False
        _wait_until_exit(
            process, time.monotonic() + grace_seconds, poll_seconds)
        if process.poll() is None:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=max(grace_seconds, 0.1))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    return True


def _file_evidence(path, tail_bytes=4096):
    content = path.read_bytes() if path.exists() else b""
    tail = content[-tail_bytes:].decode("utf8", "replace")
    return {
        "path": str(path),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "tail": tail,
    }


def _finish_result(active, status, returncode, timed_out=False):
    active["stdout_handle"].close()
    active["stderr_handle"].close()
    finished = time.monotonic()
    return {
        "name": active["command"].name,
        "argv": list(active["command"].argv),
        "status": status,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round(finished - active["started"], 6),
        "temp_root": str(active["temp_root"]),
        "stdout": _file_evidence(active["stdout_path"]),
        "stderr": _file_evidence(active["stderr_path"]),
    }


def run_round(commands, round_number, work_root, log_root, timeout_seconds,
              grace_seconds=DEFAULT_GRACE_SECONDS,
              poll_seconds=DEFAULT_POLL_SECONDS,
              native_optimization="0", base_environment=None):
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if grace_seconds < 0 or poll_seconds <= 0:
        raise ValueError("grace_seconds must be non-negative and poll_seconds positive")
    base_environment = os.environ if base_environment is None else base_environment
    round_work = Path(work_root) / ("round-%03d" % round_number)
    round_logs = Path(log_root) / ("round-%03d" % round_number)
    round_work.mkdir(parents=True, exist_ok=True)
    round_logs.mkdir(parents=True, exist_ok=True)
    active = {}
    results = []
    names = [command.name for command in commands]
    if len(set(names)) != len(names):
        raise ValueError("stress command names must be unique")

    try:
        for command in commands:
            temp_root = round_work / command.name
            temp_root.mkdir()
            stdout_path = round_logs / (command.name + ".stdout.log")
            stderr_path = round_logs / (command.name + ".stderr.log")
            stdout_handle = stdout_path.open("wb")
            stderr_handle = stderr_path.open("wb")
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    command.argv,
                    cwd=ROOT,
                    env=child_environment(
                        base_environment, command.name, round_number,
                        temp_root, native_optimization),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    **_popen_group_kwargs(),
                )
            except OSError as error:
                stderr_handle.write((str(error) + "\n").encode("utf8", "replace"))
                stdout_handle.close()
                stderr_handle.close()
                results.append({
                    "name": command.name,
                    "argv": list(command.argv),
                    "status": "start-error",
                    "returncode": None,
                    "timed_out": False,
                    "duration_seconds": round(time.monotonic() - started, 6),
                    "temp_root": str(temp_root),
                    "stdout": _file_evidence(stdout_path),
                    "stderr": _file_evidence(stderr_path),
                })
                continue
            active[command.name] = {
                "command": command,
                "process": process,
                "started": started,
                "deadline": started + timeout_seconds,
                "temp_root": temp_root,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "stdout_handle": stdout_handle,
                "stderr_handle": stderr_handle,
            }

        while active:
            now = time.monotonic()
            finished_names = []
            for name, item in active.items():
                process = item["process"]
                returncode = process.poll()
                if returncode is not None:
                    status = "passed" if returncode == 0 else "failed"
                    results.append(_finish_result(item, status, returncode))
                    finished_names.append(name)
                elif now >= item["deadline"]:
                    terminate_process_group(
                        process, grace_seconds=grace_seconds,
                        poll_seconds=poll_seconds)
                    results.append(_finish_result(
                        item, "timed-out", process.returncode, timed_out=True))
                    finished_names.append(name)
            for name in finished_names:
                del active[name]
            if active:
                time.sleep(poll_seconds)
    except BaseException:
        for item in active.values():
            terminate_process_group(
                item["process"], grace_seconds=grace_seconds,
                poll_seconds=poll_seconds)
            if not item["stdout_handle"].closed:
                item["stdout_handle"].close()
            if not item["stderr_handle"].closed:
                item["stderr_handle"].close()
        raise

    order = {name: index for index, name in enumerate(names)}
    results.sort(key=lambda result: order[result["name"]])
    return {
        "round": round_number,
        "passed": all(result["status"] == "passed" for result in results),
        "commands": results,
    }


def run_stress(commands, rounds, timeout_seconds, output,
               grace_seconds=DEFAULT_GRACE_SECONDS,
               poll_seconds=DEFAULT_POLL_SECONDS,
               native_optimization="0", base_environment=None):
    if rounds <= 0:
        raise ValueError("rounds must be positive")
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    log_root = output.parent / (output.stem + "-logs")
    log_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    round_results = []
    with TemporaryDirectory(prefix="ahpy-parallel-stress-") as work_dir:
        for round_number in range(1, rounds + 1):
            round_results.append(run_round(
                commands, round_number, Path(work_dir), log_root,
                timeout_seconds, grace_seconds=grace_seconds,
                poll_seconds=poll_seconds,
                native_optimization=native_optimization,
                base_environment=base_environment,
            ))
    passed = all(result["passed"] for result in round_results)
    fault_case_counts = []
    fault_output_valid = True
    for round_result in round_results:
        fault_commands = [
            command for command in round_result["commands"]
            if command["name"] == "fault"
        ]
        if not fault_commands:
            continue
        if len(fault_commands) != 1 or fault_commands[0]["status"] != "passed":
            fault_output_valid = False
            continue
        stdout_path = Path(fault_commands[0]["stdout"]["path"])
        matches = _FAULT_RESULT.findall(
            stdout_path.read_text(encoding="utf8", errors="replace"))
        if len(matches) != 1:
            fault_output_valid = False
            continue
        fault_case_counts.append(int(matches[0]))
    has_fault_command = any(
        command.name == "fault" for command in commands)
    if has_fault_command and (
        not fault_output_valid
        or len(fault_case_counts) != rounds
        or len(set(fault_case_counts)) != 1
    ):
        passed = False
        fault_cases_per_round = 0
        expected_fault_cases = 0
    elif fault_case_counts:
        fault_cases_per_round = fault_case_counts[0]
        expected_fault_cases = sum(fault_case_counts)
    else:
        fault_cases_per_round = 0
        expected_fault_cases = 0
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "implementation": platform.python_implementation(),
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "configuration": {
            "rounds": rounds,
            "timeout_seconds": timeout_seconds,
            "grace_seconds": grace_seconds,
            "poll_seconds": poll_seconds,
            "native_optimization": native_optimization,
            "fault_cases_per_round": fault_cases_per_round,
            "expected_fault_cases": expected_fault_cases,
            "fault_case_counts": fault_case_counts,
        },
        "passed": passed,
        "duration_seconds": round(time.monotonic() - started, 6),
        "round_results": round_results,
    }
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return report


def _resolve_python(parser, value):
    path = Path(value)
    if path.exists():
        return os.path.abspath(value)
    resolved = shutil.which(value)
    if resolved is None:
        parser.error("Python interpreter not found: %s" % value)
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--timeout-seconds", type=float,
                        default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--grace-seconds", type=float,
                        default=DEFAULT_GRACE_SECONDS)
    parser.add_argument("--poll-seconds", type=float,
                        default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--fuzz-cases", type=int, default=48)
    parser.add_argument(
        "--native-optimization", choices=("default", "0", "1", "2", "3"),
        default="0",
        help="stress-only native optimization appended after build defaults")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "stress-results" / "parallel-hpy.json")
    args = parser.parse_args()
    if args.fuzz_cases <= 0:
        parser.error("--fuzz-cases must be positive")
    python = _resolve_python(parser, args.python)
    report = run_stress(
        build_commands(python, fuzz_cases=args.fuzz_cases),
        args.rounds,
        args.timeout_seconds,
        args.output,
        grace_seconds=args.grace_seconds,
        poll_seconds=args.poll_seconds,
        native_optimization=args.native_optimization,
    )
    for round_result in report["round_results"]:
        statuses = ", ".join(
            "%s=%s(%.2fs)" %
            (result["name"], result["status"], result["duration_seconds"])
            for result in round_result["commands"])
        print("round %d: %s" % (round_result["round"], statuses))
    print("Parallel HPy stress report: %s" % args.output)
    if not report["passed"]:
        raise SystemExit(1)
    print(
        "Parallel HPy stress passed: %d rounds, %d fault selectors" %
        (args.rounds, report["configuration"]["expected_fault_cases"]))


if __name__ == "__main__":
    main()
