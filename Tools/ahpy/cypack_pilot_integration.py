#!/usr/bin/env python3
"""Build and execute the pinned cypack PRD-8 Universal HPy pilot port."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import zipfile

from artifact_utils import require_universal_binary
from pilot_performance import read_performance
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "ahpy" / "pilot_ports" / "cypack"
MODULES = ("cypack.utils", "cypack.answer", "cypack.fibonacci")
UPSTREAM_COMMIT = "7dfb3905259c5c7a82770806e5e558999eef79ce"
EXPECTED_ZEN_MD5 = hashlib.md5(
    (FIXTURE / "src" / "cypack" / "data" / "zen.txt").read_bytes()
).hexdigest()


def _runtime_program(debug=False):
    prefix = ""
    suffix = ""
    if debug:
        prefix = (
            "from hpy.debug import LeakDetector\n"
            "detector = LeakDetector()\n"
            "detector.start()\n"
        )
        suffix = "detector.stop()\n"
    return (
        "from cypack.answer import the_answer, zen_hash\n"
        "from cypack.fibonacci import fib\n"
        "from cypack.utils import axpy\n" +
        prefix +
        "assert the_answer() == 42\n"
        "assert axpy(4, 10, 2) == 42\n"
        "assert fib(0) == 0\n"
        "assert fib(1) == 1\n"
        "assert fib(7) == 13\n"
        f"assert zen_hash() == {EXPECTED_ZEN_MD5!r}\n" +
        suffix
    )


def _performance_program():
    return """\
import gc
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import time

from cypack.fibonacci import fib as compiled_fib
from cypack.utils import axpy as compiled_axpy

def python_axpy(a, x, y):
    return a * x + y

def python_fib(n):
    a = 0
    b = 1
    for _ in range(n):
        a, b = b, a + b
    return a

def measure(function, arguments, iterations, repeats=7):
    for _ in range(1000):
        function(*arguments)
    samples = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        checksum = 0
        for _ in range(iterations):
            checksum ^= function(*arguments)
        elapsed = time.perf_counter_ns() - started
        if checksum not in (0, function(*arguments)):
            raise AssertionError("unexpected performance checksum")
        samples.append(elapsed / iterations)
    return statistics.median(samples)

gc.disable()
workloads = {}
for name, compiled, reference, arguments, iterations in (
    ("axpy", compiled_axpy, python_axpy, (4, 10, 2), 100000),
    ("fibonacci", compiled_fib, python_fib, (100,), 20000),
):
    assert compiled(*arguments) == reference(*arguments)
    compiled_ns = measure(compiled, arguments, iterations)
    reference_ns = measure(reference, arguments, iterations)
    workloads[name] = {
        "iterations": iterations,
        "repeats": 7,
        "compiled_ns_per_call": compiled_ns,
        "python_reference_ns_per_call": reference_ns,
        "compiled_to_python_ratio": compiled_ns / reference_ns,
    }
with open(os.environ["AHPY_PILOT_PERFORMANCE_OUTPUT"], "w", encoding="utf8") as stream:
    json.dump({
        "schema_version": 1,
        "environment": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "hpy_version": importlib.metadata.version("hpy"),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "workloads": workloads,
    }, stream, indent=2, sort_keys=True)
    stream.write("\\n")
"""


def _read_performance(path):
    return read_performance(path, {"axpy", "fibonacci"})


def _build_root(binary):
    package = binary.parent
    if package.name != "cypack":
        raise AssertionError(f"unexpected cypack binary location: {binary}")
    return package.parent


def _only_wheel(dist):
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        raise AssertionError(f"expected exactly one pilot wheel, got {wheels!r}")
    return wheels[0]


def _audit_wheel(wheel):
    with zipfile.ZipFile(wheel) as archive:
        members = archive.namelist()
        binaries = sorted(
            name for name in members
            if name.startswith("cypack/") and ".hpy0." in name)
        stubs = sorted(
            name for name in members
            if name in {
                "cypack/answer.py",
                "cypack/fibonacci.py",
                "cypack/utils.py",
            })
        data = [name for name in members if name == "cypack/data/zen.txt"]
        metadata = [
            name for name in members if name.endswith(".dist-info/WHEEL")]
        if len(metadata) != 1:
            raise AssertionError(
                f"pilot wheel must contain one WHEEL metadata file: {members!r}")
        tags = sorted(
            line.removeprefix("Tag: ")
            for line in archive.read(metadata[0]).decode("utf8").splitlines()
            if line.startswith("Tag: "))
    if len(binaries) != len(MODULES) or len(stubs) != len(MODULES):
        raise AssertionError(
            "pilot wheel must contain three .hpy0 binaries and loader stubs: "
            f"{members!r}")
    if len(data) != 1:
        raise AssertionError("pilot wheel is missing cypack/data/zen.txt")
    if not tags:
        raise AssertionError("pilot wheel metadata has no compatibility tag")
    return tags


def build_and_run(python, output=None):
    started = time.monotonic()
    with TemporaryDirectory(prefix="ahpy-cypack-pilot-") as temp_dir:
        temp = Path(temp_dir)
        project = temp / "project"
        shutil.copytree(FIXTURE, project)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        build = project / "build"

        build_started = time.monotonic()
        run([
            python,
            str(project / "setup.py"),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build),
        ], cwd=project, env=environment, stdout=subprocess.DEVNULL)
        build_seconds = time.monotonic() - build_started

        generated = [
            project / "src" / "cypack" / (name + ".c")
            for name in ("utils", "answer", "fibonacci")
        ]
        for source in generated:
            verify_source_boundary(source, required=("#include <hpy.h>",))

        binaries = [require_universal_binary(build, name) for name in MODULES]
        for binary in binaries:
            verify_binary_boundary(binary)
        roots = {_build_root(binary) for binary in binaries}
        if len(roots) != 1:
            raise AssertionError(f"pilot binaries span build roots: {roots!r}")
        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(roots.pop())

        mode_seconds = {}
        for mode, hpy_mode, debug in (
            ("normal", None, False),
            ("trace", "trace", False),
            ("debug", "debug", True),
        ):
            selected = runtime_environment.copy()
            if hpy_mode:
                selected["HPY"] = hpy_mode
            mode_started = time.monotonic()
            run([
                python, "-c", _runtime_program(debug),
            ], cwd=project, env=selected)
            mode_seconds[mode] = time.monotonic() - mode_started

        dist = project / "dist"
        wheel_started = time.monotonic()
        run([
            python,
            str(project / "setup.py"),
            "--hpy-abi=universal",
            "bdist_wheel",
            "--dist-dir", str(dist),
        ], cwd=project, env=environment, stdout=subprocess.DEVNULL)
        wheel_seconds = time.monotonic() - wheel_started
        wheel = _only_wheel(dist)
        wheel_tags = _audit_wheel(wheel)

        installed = temp / "installed"
        install_started = time.monotonic()
        run([
            python,
            "-m", "pip", "install",
            "--no-deps",
            "--target", str(installed),
            str(wheel),
        ], cwd=project, env=environment, stdout=subprocess.DEVNULL)
        install_seconds = time.monotonic() - install_started
        installed_environment = environment.copy()
        installed_environment["PYTHONPATH"] = str(installed)
        installed_mode_seconds = {}
        for mode, hpy_mode, debug in (
            ("normal", None, False),
            ("trace", "trace", False),
            ("debug", "debug", True),
        ):
            selected = installed_environment.copy()
            if hpy_mode:
                selected["HPY"] = hpy_mode
            mode_started = time.monotonic()
            run([
                python, "-c", _runtime_program(debug),
            ], cwd=project, env=selected)
            installed_mode_seconds[mode] = time.monotonic() - mode_started

        performance_output = temp / "performance.json"
        performance_environment = runtime_environment.copy()
        performance_environment["AHPY_PILOT_PERFORMANCE_OUTPUT"] = str(
            performance_output)
        performance_started = time.monotonic()
        run([
            python, "-c", _performance_program(),
        ], cwd=project, env=performance_environment)
        performance_seconds = time.monotonic() - performance_started
        performance = _read_performance(performance_output)

        report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pilot": "cypack-pure-cython",
            "upstream_commit": UPSTREAM_COMMIT,
            "backend": "hpy-universal",
            "python": os.path.abspath(python),
            "port_contract": {
                "status": "selected-source-port",
                "selected_modules": list(MODULES),
                "omitted_upstream_surfaces": ["cypack.sub.wrong"],
            },
            "gates": {
                "generate": "pass",
                "port-patch": "pass",
                "native-build": "pass",
                "source-audit": "pass",
                "binary-audit": "pass",
                "tests": "pass",
                "normal": "pass",
                "trace": "pass",
                "debug": "pass",
                "wheel-build": "pass",
                "wheel-audit": "pass",
                "wheel-install": "pass",
                "installed-normal": "pass",
                "installed-trace": "pass",
                "installed-debug": "pass",
                "performance": "pass",
            },
            "artifacts": {
                "generated_sources": [source.name for source in generated],
                "binaries": [binary.name for binary in binaries],
                "wheel": wheel.name,
                "wheel_tags": wheel_tags,
            },
            "performance": {
                "comparison": "compiled-port-to-equivalent-python",
                "budget_enforced": False,
                **performance,
            },
            "timings_seconds": {
                "build": build_seconds,
                **mode_seconds,
                "wheel_build": wheel_seconds,
                "wheel_install": install_seconds,
                "installed_normal": installed_mode_seconds["normal"],
                "installed_trace": installed_mode_seconds["trace"],
                "installed_debug": installed_mode_seconds["debug"],
                "performance": performance_seconds,
                "total": time.monotonic() - started,
            },
        }
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                          encoding="utf8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    selected = Path(options.python)
    python = os.path.abspath(options.python) if selected.exists() else shutil.which(
        options.python)
    if python is None:
        parser.error(f"Python interpreter not found: {options.python}")
    report = build_and_run(python, options.output)
    if options.output is None:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
