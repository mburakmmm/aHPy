#!/usr/bin/env python3
"""Benchmark generated Universal HPy against an equivalent handwritten module."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import tomllib

from test_generated_hpy import verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
GENERATED_NAME = "ahpy_benchmark_generated"
REFERENCE_NAME = "ahpy_benchmark_reference"
GENERATED_SOURCE = ROOT / "tests" / "ahpy" / "benchmark_generated.pyx"
REFERENCE_SOURCE = ROOT / "tests" / "ahpy" / "benchmark_reference.c"
DEFAULT_BUDGETS = ROOT / "tests" / "ahpy" / "performance-budgets.toml"
OPERATIONS = (
    "identity", "arithmetic", "container", "attribute", "call", "exception",
)


def load_budgets(path):
    data = tomllib.loads(Path(path).read_text(encoding="utf8"))
    if data.get("schema_version") != 1:
        raise ValueError("performance budget schema_version must be 1")
    runtime = data.get("runtime_ratio", {})
    missing = sorted(set(OPERATIONS) - set(runtime))
    unknown = sorted(set(runtime) - set(OPERATIONS))
    if missing or unknown:
        raise ValueError(
            "runtime ratio keys differ: missing=%r unknown=%r" %
            (missing, unknown))
    for group in (runtime, data.get("footprint", {})):
        for name, value in group.items():
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValueError("budget %s must be positive" % name)
    measurement = data.get("measurement", {})
    for name in ("iterations", "warmups", "repeats"):
        value = measurement.get(name)
        if not isinstance(value, int) or value < 0:
            raise ValueError("measurement %s must be a non-negative integer" % name)
    if measurement["iterations"] == 0 or measurement["repeats"] < 3:
        raise ValueError("measurement requires iterations > 0 and repeats >= 3")
    return data


def check_thresholds(report, budgets):
    violations = []
    runtime_budgets = budgets["runtime_ratio"]
    for operation in OPERATIONS:
        ratio = report["runtime"][operation]["ratio"]
        limit = runtime_budgets[operation]
        if not math.isfinite(ratio) or ratio > limit:
            violations.append(
                "runtime.%s ratio %.3f exceeds %.3f" %
                (operation, ratio, limit))

    footprint = report["footprint"]
    footprint_budgets = budgets["footprint"]
    for metric in ("generated_c_bytes", "generated_binary_bytes"):
        value = footprint[metric]
        limit = footprint_budgets[metric]
        if value > limit:
            violations.append(
                "footprint.%s %d exceeds %d" % (metric, value, limit))
    ratio = footprint["binary_to_reference_ratio"]
    limit = footprint_budgets["binary_to_reference_ratio"]
    if not math.isfinite(ratio) or ratio > limit:
        violations.append(
            "footprint.binary_to_reference_ratio %.3f exceeds %.3f" %
            (ratio, limit))
    return violations


def check_environment(report, budgets):
    expected = budgets["environment"]
    actual = report["environment"]
    fields = {
        "hpy": "hpy_version",
        "python_implementation": "python_implementation",
    }
    violations = []
    if expected.get("abi") != "universal":
        violations.append("budget ABI must be universal")
    for expected_name, actual_name in fields.items():
        if expected.get(expected_name) != actual.get(actual_name):
            violations.append(
                "environment.%s %r does not match budget %r" %
                (expected_name, actual.get(actual_name), expected.get(expected_name)))
    return violations


class _Holder:
    def __init__(self, value):
        self.value = value


def _time_operation(module, operation, iterations):
    marker = object()
    function = {
        "identity": module.identity,
        "arithmetic": module.add,
        "container": module.make_pair,
        "attribute": module.get_value,
        "call": module.call_zero,
        "exception": module.raise_value,
    }[operation]
    start = time.perf_counter_ns()
    if operation == "identity":
        for _ in range(iterations):
            function(marker)
    elif operation == "arithmetic":
        for _ in range(iterations):
            function(20, 22)
    elif operation == "container":
        for _ in range(iterations):
            function(marker, marker)
    elif operation == "attribute":
        holder = _Holder(marker)
        for _ in range(iterations):
            function(holder)
    elif operation == "call":
        callable_object = marker.__repr__
        for _ in range(iterations):
            function(callable_object)
    else:
        for _ in range(iterations):
            try:
                function()
            except ValueError:
                pass
    return (time.perf_counter_ns() - start) / iterations


def _verify_semantics(module):
    marker = object()
    holder = _Holder(marker)
    if module.identity(marker) is not marker:
        raise AssertionError("identity semantic mismatch")
    if module.add(20, 22) != 42:
        raise AssertionError("arithmetic semantic mismatch")
    pair = module.make_pair(marker, marker)
    if pair != [marker, marker]:
        raise AssertionError("container semantic mismatch")
    if module.get_value(holder) is not marker:
        raise AssertionError("attribute semantic mismatch")
    if module.call_zero(lambda: marker) is not marker:
        raise AssertionError("call semantic mismatch")
    try:
        module.raise_value()
    except ValueError as error:
        if str(error) != "aHPy benchmark":
            raise AssertionError("exception message mismatch") from error
    else:
        raise AssertionError("exception benchmark did not raise")


def measure_loaded_modules(build_lib, iterations, warmups, repeats):
    sys.path.insert(0, str(build_lib))
    try:
        modules = {
            "generated": importlib.import_module(GENERATED_NAME),
            "reference": importlib.import_module(REFERENCE_NAME),
        }
        for module in modules.values():
            _verify_semantics(module)
        for operation in OPERATIONS:
            for module in modules.values():
                for _ in range(warmups):
                    _time_operation(module, operation, max(100, iterations // 10))

        samples = {
            operation: {name: [] for name in modules}
            for operation in OPERATIONS
        }
        for repeat in range(repeats):
            order = ("generated", "reference")
            if repeat % 2:
                order = tuple(reversed(order))
            for operation in OPERATIONS:
                for name in order:
                    samples[operation][name].append(
                        _time_operation(modules[name], operation, iterations))
        runtime = {}
        for operation in OPERATIONS:
            generated = statistics.median(samples[operation]["generated"])
            reference = statistics.median(samples[operation]["reference"])
            runtime[operation] = {
                "generated_ns_per_call": round(generated, 3),
                "reference_ns_per_call": round(reference, 3),
                "ratio": round(generated / reference, 6),
                "generated_samples": [round(value, 3) for value in
                                      samples[operation]["generated"]],
                "reference_samples": [round(value, 3) for value in
                                      samples[operation]["reference"]],
            }
        return {
            "runtime": runtime,
            "environment": {
                "python_implementation": platform.python_implementation(),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "hpy_version": importlib.metadata.version("hpy"),
            },
        }
    finally:
        sys.path.pop(0)


def debug_check_loaded_modules(build_lib):
    sys.path.insert(0, str(build_lib))
    try:
        from hpy.debug import LeakDetector

        modules = (
            importlib.import_module(GENERATED_NAME),
            importlib.import_module(REFERENCE_NAME),
        )
        detector = LeakDetector()
        detector.start()
        try:
            for module in modules:
                _verify_semantics(module)
        finally:
            detector.stop()
    finally:
        sys.path.pop(0)


def _compiler_identity(environment):
    command = environment.get("CC") or "cc"
    executable = shutil.which(command) or command
    result = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=False)
    first_line = (result.stdout or result.stderr).splitlines()
    return first_line[0] if first_line else command


def _run(command, **kwargs):
    try:
        return subprocess.run(command, check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        details = error.stderr or error.stdout or ""
        raise RuntimeError(
            "command failed (%d): %s\n%s" %
            (error.returncode, " ".join(map(str, command[:3])), details.rstrip())) from None


def build_and_measure(python, budgets, budget_path, output):
    measurement = budgets["measurement"]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    with TemporaryDirectory(prefix="ahpy-benchmark-") as temp_dir:
        temp = Path(temp_dir)
        generated_input = temp / (GENERATED_NAME + ".pyx")
        shutil.copyfile(GENERATED_SOURCE, generated_input)
        generated = temp / (GENERATED_NAME + ".c")
        cython_start = time.perf_counter()
        _run([
            python, "-m", "cython", "--runtime-backend=hpy-universal", "-3",
            "-o", str(generated), str(generated_input),
        ], cwd=ROOT, env=environment, capture_output=True, text=True)
        cython_seconds = time.perf_counter() - cython_start
        verify_source_boundary(
            generated,
            required=("#include <hpy.h>", "HPyDef_METH", "HPy_Add",
                      "HPyListBuilder_New", "HPy_GetAttr_s", "HPy_Call",
                      "HPyErr_SetString", "HPy_MODINIT"),
        )

        setup = temp / "setup.py"
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "setup(name='ahpy-benchmark', version='0.0.0', packages=[], "
            "py_modules=[], hpy_ext_modules=[\n"
            " Extension(%r, [%r]),\n" % (GENERATED_NAME, str(generated)) +
            " Extension(%r, [%r]),\n" % (REFERENCE_NAME, str(REFERENCE_SOURCE)) +
            "])\n",
            encoding="utf8",
        )
        build_root = temp / "build"
        build_start = time.perf_counter()
        _run([
            python, str(setup), "--hpy-abi=universal", "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        build_seconds = time.perf_counter() - build_start

        generated_binaries = list(build_root.rglob(GENERATED_NAME + "*.hpy0.*"))
        reference_binaries = list(build_root.rglob(REFERENCE_NAME + "*.hpy0.*"))
        if len(generated_binaries) != 1 or len(reference_binaries) != 1:
            raise AssertionError(
                "expected one generated and reference binary, got %r / %r" %
                (generated_binaries, reference_binaries))
        generated_binary = generated_binaries[0]
        reference_binary = reference_binaries[0]
        verify_binary_boundary(generated_binary)
        verify_binary_boundary(reference_binary)
        build_lib = generated_binary.parent
        if reference_binary.parent != build_lib:
            raise AssertionError("benchmark modules were built into different roots")

        child = _run([
            python, str(Path(__file__).resolve()),
            "--run-built", str(build_lib),
            "--iterations", str(measurement["iterations"]),
            "--warmups", str(measurement["warmups"]),
            "--repeats", str(measurement["repeats"]),
        ], cwd=temp, env=environment, capture_output=True, text=True)
        report = json.loads(child.stdout)
        debug_environment = environment.copy()
        debug_environment["HPY"] = "debug"
        _run([
            python, str(Path(__file__).resolve()),
            "--debug-check", str(build_lib),
        ], cwd=temp, env=debug_environment, capture_output=True, text=True)
        reference_size = reference_binary.stat().st_size
        report.update({
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "measurement": dict(measurement),
            "build": {
                "cython_seconds": round(cython_seconds, 6),
                "native_build_seconds": round(build_seconds, 6),
                "compiler": _compiler_identity(environment),
            },
            "footprint": {
                "generated_c_bytes": generated.stat().st_size,
                "reference_c_bytes": REFERENCE_SOURCE.stat().st_size,
                "generated_binary_bytes": generated_binary.stat().st_size,
                "reference_binary_bytes": reference_size,
                "binary_to_reference_ratio": round(
                    generated_binary.stat().st_size / reference_size, 6),
            },
            "budget_source": str(Path(budget_path).resolve()),
            "debug_leak_check": "passed",
        })
        report["violations"] = (
            check_environment(report, budgets) + check_thresholds(report, budgets))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "performance-results" / "benchmark.json")
    parser.add_argument("--run-built", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--debug-check", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--iterations", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--warmups", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--repeats", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.debug_check is not None:
        debug_check_loaded_modules(args.debug_check)
        return

    if args.run_built is not None:
        if not all(value is not None for value in
                   (args.iterations, args.warmups, args.repeats)):
            parser.error("internal benchmark measurement arguments are incomplete")
        report = measure_loaded_modules(
            args.run_built, args.iterations, args.warmups, args.repeats)
        print(json.dumps(report, sort_keys=True))
        return

    python = shutil.which(args.python) if not Path(args.python).exists() else os.path.abspath(args.python)
    if python is None:
        parser.error("Python interpreter not found: %s" % args.python)
    budgets = load_budgets(args.budgets)
    report = build_and_measure(python, budgets, args.budgets, args.output)
    if report["violations"]:
        for violation in report["violations"]:
            print("performance regression: " + violation, file=sys.stderr)
        raise SystemExit(1)
    ratios = ", ".join(
        "%s=%.2fx" % (name, report["runtime"][name]["ratio"])
        for name in OPERATIONS)
    print("Universal HPy performance budgets passed: " + ratios)
    print("History record: %s" % args.output)


if __name__ == "__main__":
    main()
