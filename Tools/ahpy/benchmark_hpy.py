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
import shlex
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
CLASSIC_NAME = "ahpy_benchmark_classic"
GENERATED_SOURCE = ROOT / "tests" / "ahpy" / "benchmark_generated.pyx"
REFERENCE_SOURCE = ROOT / "tests" / "ahpy" / "benchmark_reference.c"
EXTERNAL_SOURCE = ROOT / "tests" / "ahpy" / "benchmark_external.c"
BENCHMARK_INCLUDE = ROOT / "tests" / "ahpy"
LARGE_TYPE_SOURCE = ROOT / "tests" / "ahpy" / "bootstrap_types.pyx"
DEFAULT_BUDGETS = ROOT / "tests" / "ahpy" / "performance-budgets.toml"
OPERATIONS = (
    "identity", "arithmetic", "container", "attribute", "call", "exception",
    "type_create", "type_method", "external_c",
)
TRACE_ITERATIONS = 1000


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
    large_type = data.get("large_type_compile", {})
    if not isinstance(large_type.get("timeout_seconds"), (int, float)) or \
            large_type["timeout_seconds"] <= 0:
        raise ValueError("large_type_compile.timeout_seconds must be positive")
    if not isinstance(large_type.get("enforce_o3"), bool):
        raise ValueError("large_type_compile.enforce_o3 must be boolean")
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
    large_type = report["large_type_compile"]
    if large_type["o3"]["timed_out"] and \
            budgets["large_type_compile"]["enforce_o3"]:
        violations.append("large_type_compile.o3 exceeded timeout budget")
    if large_type["o0"]["timed_out"]:
        violations.append("large_type_compile.o0 exceeded timeout budget")
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
    functions = {
        "identity": module.identity,
        "arithmetic": module.add,
        "container": module.make_pair,
        "attribute": module.get_value,
        "call": module.call_zero,
        "exception": module.raise_value,
        "type_create": module.BenchmarkBox,
        "external_c": module.external_add,
    }
    box = None
    if operation == "type_method":
        box = module.BenchmarkBox(marker)
        function = box.identity
    else:
        function = functions[operation]
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
    elif operation == "type_create":
        for _ in range(iterations):
            function(marker)
    elif operation == "type_method":
        for _ in range(iterations):
            function()
    elif operation == "external_c":
        for _ in range(iterations):
            function()
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
    box = module.BenchmarkBox(marker)
    if box.identity() is not marker:
        raise AssertionError("extension type semantic mismatch")
    if module.external_add() != 42:
        raise AssertionError("external C semantic mismatch")
    positional_only_calls = (
        (module.identity, {"value": marker}),
        (module.add, {"left": 20, "right": 22}),
        (module.make_pair, {"left": marker, "right": marker}),
        (module.get_value, {"value": holder}),
        (module.call_zero, {"callable_object": lambda: marker}),
        (module.BenchmarkBox, {"value": marker}),
    )
    for function, keywords in positional_only_calls:
        try:
            function(**keywords)
        except TypeError:
            pass
        else:
            raise AssertionError("positional-only semantic mismatch")
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


def measure_single_loaded_module(
        build_lib, module_name, iterations, warmups, repeats):
    sys.path.insert(0, str(build_lib))
    try:
        module = importlib.import_module(module_name)
        _verify_semantics(module)
        for operation in OPERATIONS:
            for _ in range(warmups):
                _time_operation(module, operation, max(100, iterations // 10))
        runtime = {}
        for operation in OPERATIONS:
            samples = [
                _time_operation(module, operation, iterations)
                for _ in range(repeats)
            ]
            runtime[operation] = {
                "ns_per_call": round(statistics.median(samples), 3),
                "samples": [round(value, 3) for value in samples],
            }
        return {"runtime": runtime}
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


def _peak_rss_bytes():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.PeakWorkingSetSize)

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux and the BSDs report KiB; Darwin reports bytes.
    return int(peak if sys.platform == "darwin" else peak * 1024)


def peak_memory_loaded_module(build_lib, implementation, iterations):
    names = {
        "generated": GENERATED_NAME,
        "reference": REFERENCE_NAME,
        "classic": CLASSIC_NAME,
    }
    if implementation not in names:
        raise ValueError("unknown benchmark implementation: %s" % implementation)
    if iterations <= 0:
        raise ValueError("peak-memory iterations must be positive")
    sys.path.insert(0, str(build_lib))
    try:
        module = importlib.import_module(names[implementation])
        _verify_semantics(module)
        for operation in OPERATIONS:
            _time_operation(module, operation, iterations)
        return {
            "implementation": implementation,
            "iterations_per_operation": iterations,
            "peak_rss_bytes": _peak_rss_bytes(),
        }
    finally:
        sys.path.pop(0)


def _trace_count_delta(before, after):
    return {
        name: after.get(name, 0) - before.get(name, 0)
        for name in sorted(set(before) | set(after))
        if after.get(name, 0) > before.get(name, 0)
    }


def trace_loaded_modules(build_lib, iterations, get_counts=None):
    if iterations <= 0:
        raise ValueError("trace iterations must be positive")
    if get_counts is None:
        from hpy import trace as hpy_trace
        get_counts = hpy_trace.get_call_counts
    sys.path.insert(0, str(build_lib))
    try:
        modules = {
            "generated": importlib.import_module(GENERATED_NAME),
            "reference": importlib.import_module(REFERENCE_NAME),
        }
        for module in modules.values():
            _verify_semantics(module)
        operations = {}
        for operation in OPERATIONS:
            operations[operation] = {}
            for name, module in modules.items():
                before = dict(get_counts())
                _time_operation(module, operation, iterations)
                after = dict(get_counts())
                counts = _trace_count_delta(before, after)
                total = sum(counts.values())
                operations[operation][name] = {
                    "api_calls": counts,
                    "total_api_calls": total,
                    "api_calls_per_iteration": round(total / iterations, 6),
                    "handle_churn": {
                        "dup": counts.get("ctx_Dup", 0),
                        "close": counts.get("ctx_Close", 0),
                    },
                }
        return {"iterations": iterations, "operations": operations}
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


def _find_extension(build_root, module_name, universal=None):
    candidates = [
        path for path in build_root.rglob(module_name + "*")
        if path.is_file() and path.suffix.lower() in (".so", ".pyd", ".dll")
    ]
    if universal is True:
        candidates = [path for path in candidates if ".hpy0." in path.name]
    elif universal is False:
        candidates = [path for path in candidates if ".hpy0." not in path.name]
    if len(candidates) != 1:
        raise AssertionError(
            "expected one %s extension binary, got %r" %
            (module_name, candidates))
    return candidates[0]


def _native_compile_command(compiler, optimization, include_dir, source, output):
    parts = shlex.split(compiler)
    if os.name == "nt" and Path(parts[0]).name.lower() in ("cl", "cl.exe"):
        flag = "/Od" if optimization == 0 else "/O2"
        return parts + [
            "/nologo", "/c", flag, "/DHPY_ABI_UNIVERSAL",
            "/I" + str(include_dir), str(source), "/Fo" + str(output),
        ]
    return parts + [
        "-c", "-fPIC", "-DHPY_ABI_UNIVERSAL", "-O%d" % optimization,
        "-I" + str(include_dir), str(source), "-o", str(output),
    ]


def measure_large_type_compile(python, temp, environment, timeout_seconds):
    generated = temp / "bootstrap_types_large.c"
    frontend_start = time.perf_counter()
    _run([
        python, "-m", "cython", "--runtime-backend=hpy-universal", "-3",
        "-o", str(generated), str(LARGE_TYPE_SOURCE),
    ], cwd=ROOT, env=environment, capture_output=True, text=True)
    frontend_seconds = time.perf_counter() - frontend_start
    include_result = _run([
        python, "-c",
        "from hpy.devel import HPyDevel; print(HPyDevel().include_dir)",
    ], env=environment, capture_output=True, text=True)
    include_dir = Path(include_result.stdout.strip())
    compiler = environment.get("CC") or ("cl" if os.name == "nt" else "cc")
    results = {}
    for optimization in (0, 3):
        command = _native_compile_command(
            compiler, optimization, include_dir, generated,
            temp / ("bootstrap_types_o%d.o" % optimization))
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True,
                timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            results["o%d" % optimization] = {
                "seconds": round(time.perf_counter() - started, 6),
                "timed_out": True,
            }
            continue
        seconds = time.perf_counter() - started
        if completed.returncode:
            raise RuntimeError(
                "large type compile failed (%d): %s" %
                (completed.returncode, completed.stderr.rstrip()))
        results["o%d" % optimization] = {
            "seconds": round(seconds, 6), "timed_out": False,
        }
    with generated.open(encoding="utf8", errors="replace") as stream:
        generated_lines = sum(1 for _ in stream)
    results.update({
        "frontend_seconds": round(frontend_seconds, 6),
        "generated_c_bytes": generated.stat().st_size,
        "generated_c_lines": generated_lines,
        "timeout_seconds": timeout_seconds,
        "compiler": _compiler_identity(environment),
    })
    if not results["o0"]["timed_out"] and not results["o3"]["timed_out"]:
        results["o3_to_o0_ratio"] = round(
            results["o3"]["seconds"] / results["o0"]["seconds"], 6)
    return results


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
                      "HPyErr_SetString", "HPyType_FromSpec",
                      "ahpy_benchmark_external_add", "HPy_MODINIT"),
        )

        setup = temp / "setup.py"
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "setup(name='ahpy-benchmark', version='0.0.0', packages=[], "
            "py_modules=[], hpy_ext_modules=[\n"
            " Extension(%r, [%r, %r], include_dirs=[%r]),\n" % (
                GENERATED_NAME, str(generated), str(EXTERNAL_SOURCE),
                str(BENCHMARK_INCLUDE)) +
            " Extension(%r, [%r, %r], include_dirs=[%r]),\n" % (
                REFERENCE_NAME, str(REFERENCE_SOURCE), str(EXTERNAL_SOURCE),
                str(BENCHMARK_INCLUDE)) +
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

        generated_binary = _find_extension(build_root, GENERATED_NAME, True)
        reference_binary = _find_extension(build_root, REFERENCE_NAME, True)
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
        peak_iterations = min(10000, measurement["iterations"])
        peak_memory = {}
        for implementation in ("generated", "reference"):
            peak_child = _run([
                python, str(Path(__file__).resolve()),
                "--peak-memory", str(build_lib),
                "--implementation", implementation,
                "--iterations", str(peak_iterations),
            ], cwd=temp, env=environment, capture_output=True, text=True)
            peak_memory[implementation] = json.loads(peak_child.stdout)
        peak_memory["generated_to_reference_ratio"] = round(
            peak_memory["generated"]["peak_rss_bytes"] /
            peak_memory["reference"]["peak_rss_bytes"], 6)
        report["peak_memory"] = peak_memory

        hpy_cpython_root = temp / "build-hpy-cpython"
        hpy_cpython_start = time.perf_counter()
        _run([
            python, str(setup), "--hpy-abi=cpython", "build",
            "--build-base", str(hpy_cpython_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        hpy_cpython_seconds = time.perf_counter() - hpy_cpython_start
        hpy_cpython_generated = _find_extension(
            hpy_cpython_root, GENERATED_NAME, False)
        hpy_cpython_reference = _find_extension(
            hpy_cpython_root, REFERENCE_NAME, False)
        if hpy_cpython_generated.parent != hpy_cpython_reference.parent:
            raise AssertionError("HPy CPython benchmark modules use different roots")
        hpy_cpython_child = _run([
            python, str(Path(__file__).resolve()),
            "--run-built", str(hpy_cpython_generated.parent),
            "--iterations", str(measurement["iterations"]),
            "--warmups", str(measurement["warmups"]),
            "--repeats", str(measurement["repeats"]),
        ], cwd=temp, env=environment, capture_output=True, text=True)
        hpy_cpython_report = json.loads(hpy_cpython_child.stdout)
        hpy_cpython_peak = {}
        for implementation in ("generated", "reference"):
            peak_child = _run([
                python, str(Path(__file__).resolve()),
                "--peak-memory", str(hpy_cpython_generated.parent),
                "--implementation", implementation,
                "--iterations", str(peak_iterations),
            ], cwd=temp, env=environment, capture_output=True, text=True)
            hpy_cpython_peak[implementation] = json.loads(peak_child.stdout)
        hpy_cpython_peak["generated_to_reference_ratio"] = round(
            hpy_cpython_peak["generated"]["peak_rss_bytes"] /
            hpy_cpython_peak["reference"]["peak_rss_bytes"], 6)
        hpy_cpython_report.update({
            "abi": "cpython",
            "native_build_seconds": round(hpy_cpython_seconds, 6),
            "generated_binary_bytes": hpy_cpython_generated.stat().st_size,
            "reference_binary_bytes": hpy_cpython_reference.stat().st_size,
            "peak_memory": hpy_cpython_peak,
        })

        classic_input = temp / (CLASSIC_NAME + ".pyx")
        shutil.copyfile(GENERATED_SOURCE, classic_input)
        classic_c = temp / (CLASSIC_NAME + ".c")
        classic_cython_start = time.perf_counter()
        _run([
            python, "-m", "cython", "-3", "-o", str(classic_c),
            str(classic_input),
        ], cwd=ROOT, env=environment, capture_output=True, text=True)
        classic_cython_seconds = time.perf_counter() - classic_cython_start
        classic_setup = temp / "setup_classic.py"
        classic_setup.write_text(
            "from setuptools import Extension, setup\n"
            "setup(name='ahpy-benchmark-classic', version='0.0.0', "
            "packages=[], py_modules=[], ext_modules=[\n"
            " Extension(%r, [%r, %r], include_dirs=[%r]),\n" % (
                CLASSIC_NAME, str(classic_c), str(EXTERNAL_SOURCE),
                str(BENCHMARK_INCLUDE)) +
            "])\n",
            encoding="utf8",
        )
        classic_root = temp / "build-classic"
        classic_build_start = time.perf_counter()
        _run([
            python, str(classic_setup), "build",
            "--build-base", str(classic_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        classic_build_seconds = time.perf_counter() - classic_build_start
        classic_binary = _find_extension(classic_root, CLASSIC_NAME, False)
        classic_child = _run([
            python, str(Path(__file__).resolve()),
            "--run-single", str(classic_binary.parent),
            "--module-name", CLASSIC_NAME,
            "--iterations", str(measurement["iterations"]),
            "--warmups", str(measurement["warmups"]),
            "--repeats", str(measurement["repeats"]),
        ], cwd=temp, env=environment, capture_output=True, text=True)
        classic_report = json.loads(classic_child.stdout)
        classic_peak_child = _run([
            python, str(Path(__file__).resolve()),
            "--peak-memory", str(classic_binary.parent),
            "--implementation", "classic",
            "--iterations", str(peak_iterations),
        ], cwd=temp, env=environment, capture_output=True, text=True)
        classic_report.update({
            "abi": "classic-cython-cpython",
            "cython_seconds": round(classic_cython_seconds, 6),
            "native_build_seconds": round(classic_build_seconds, 6),
            "generated_c_bytes": classic_c.stat().st_size,
            "binary_bytes": classic_binary.stat().st_size,
            "peak_memory": json.loads(classic_peak_child.stdout),
        })
        report["abi_matrix"] = {
            "hpy_universal": {
                "abi": "universal",
                "runtime": report["runtime"],
            },
            "hpy_cpython": hpy_cpython_report,
            "classic_cython": classic_report,
        }
        report["large_type_compile"] = measure_large_type_compile(
            python, temp, environment,
            budgets["large_type_compile"]["timeout_seconds"])
        report["large_type_compile"]["enforced_profiles"] = (
            ["o0", "o3"]
            if budgets["large_type_compile"]["enforce_o3"]
            else ["o0"]
        )
        debug_environment = environment.copy()
        debug_environment["HPY"] = "debug"
        _run([
            python, str(Path(__file__).resolve()),
            "--debug-check", str(build_lib),
        ], cwd=temp, env=debug_environment, capture_output=True, text=True)
        trace_environment = environment.copy()
        trace_environment["HPY"] = "trace"
        trace_child = _run([
            python, str(Path(__file__).resolve()),
            "--trace-counts", str(build_lib),
            "--iterations", str(min(TRACE_ITERATIONS, measurement["iterations"])),
        ], cwd=temp, env=trace_environment, capture_output=True, text=True)
        report["trace"] = json.loads(trace_child.stdout)
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
    parser.add_argument("--run-single", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--module-name", help=argparse.SUPPRESS)
    parser.add_argument("--debug-check", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--trace-counts", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--peak-memory", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--implementation", choices=("generated", "reference", "classic"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--iterations", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--warmups", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--repeats", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.debug_check is not None:
        debug_check_loaded_modules(args.debug_check)
        return

    if args.trace_counts is not None:
        if args.iterations is None:
            parser.error("internal trace measurement requires iterations")
        report = trace_loaded_modules(args.trace_counts, args.iterations)
        print(json.dumps(report, sort_keys=True))
        return

    if args.peak_memory is not None:
        if args.iterations is None or args.implementation is None:
            parser.error(
                "internal peak-memory measurement requires implementation "
                "and iterations")
        report = peak_memory_loaded_module(
            args.peak_memory, args.implementation, args.iterations)
        print(json.dumps(report, sort_keys=True))
        return

    if args.run_built is not None:
        if not all(value is not None for value in
                   (args.iterations, args.warmups, args.repeats)):
            parser.error("internal benchmark measurement arguments are incomplete")
        report = measure_loaded_modules(
            args.run_built, args.iterations, args.warmups, args.repeats)
        print(json.dumps(report, sort_keys=True))
        return

    if args.run_single is not None:
        if args.module_name is None or not all(
                value is not None for value in
                (args.iterations, args.warmups, args.repeats)):
            parser.error("internal single benchmark arguments are incomplete")
        report = measure_single_loaded_module(
            args.run_single, args.module_name, args.iterations,
            args.warmups, args.repeats)
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
