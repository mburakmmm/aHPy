#!/usr/bin/env python3
"""Build, audit, and load maintained CMake and Meson Universal examples."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_system_config import (
    create_contract,
    render_cmake,
    render_meson,
)
from direct_build import probe_toolchain
from test_generated_hpy import verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = {
    "cmake": (ROOT / "examples" / "ahpy_cmake", "ahpy_cmake_example"),
    "meson": (ROOT / "examples" / "ahpy_meson", "ahpy_meson_example"),
}


def _run(command, *, cwd=None, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _runtime_program(module_name, artifact, debug):
    return (
        "from importlib.machinery import ModuleSpec\n"
        "import hpy.universal as universal\n" +
        ("from hpy.debug import LeakDetector\n"
         "detector = LeakDetector()\n"
         "detector.start()\n" if debug else "") +
        "name = %r\n" % module_name +
        "path = %r\n" % str(artifact) +
        "spec = ModuleSpec(name, None, origin=path)\n"
        "module = universal.load(name, path, spec, %s)\n" % (
            "universal.MODE_DEBUG" if debug else "universal.MODE_UNIVERSAL") +
        "assert module.answer() == 42\n"
        "marker = object()\n"
        "box = module.Box(marker)\n"
        "assert box.value is marker\n"
        "assert box.identity() is marker\n"
        "del box\n" +
        ("detector.stop()\n" if debug else "")
    )


def _tool(name, python):
    adjacent = Path(python).parent / (name + (".exe" if os.name == "nt" else ""))
    if adjacent.is_file():
        return str(adjacent)
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise RuntimeError("required build tool is not installed: %s" % name)


def _prepare(system, python, temp, environment):
    example, module_name = EXAMPLES[system]
    project = temp / (system + "-source")
    shutil.copytree(example, project)
    generated = project / (module_name + ".c")
    _run([
        python, "-m", "cython", "--runtime-backend=hpy-universal",
        "-3", "-o", str(generated), str(project / (module_name + ".pyx")),
    ], cwd=ROOT, env=environment)
    verify_source_boundary(
        generated,
        required=("#include <hpy.h>", "HPyType_FromSpec", "HPy_MODINIT"),
    )
    contract = create_contract(probe_toolchain(python), module_name)
    if system == "cmake":
        config = temp / "ahpy-config.cmake"
        config.write_text(render_cmake(contract), encoding="utf8")
    else:
        config = project / "ahpy_config" / "meson.build"
        config.parent.mkdir()
        config.write_text(render_meson(contract), encoding="utf8")
    return project, generated, contract, config


def _build_cmake(python, temp, environment):
    project, generated, contract, config = _prepare(
        "cmake", python, temp, environment)
    build = temp / "cmake-build"
    cmake = _tool("cmake", python)
    _run([
        cmake, "-S", str(project), "-B", str(build),
        "-DAHPY_CONFIG=%s" % config,
        "-DCMAKE_BUILD_TYPE=Release",
    ], env=environment)
    _run([cmake, "--build", str(build), "--config", "Release"], env=environment)
    return generated, contract, build


def _build_meson(python, temp, environment):
    project, generated, contract, _config = _prepare(
        "meson", python, temp, environment)
    build = temp / "meson-build"
    meson = _tool("meson", python)
    _tool("ninja", python)
    meson_environment = environment.copy()
    meson_environment["PATH"] = str(Path(python).parent) + os.pathsep + os.environ.get(
        "PATH", "")
    _run([meson, "setup", str(build), str(project)], env=meson_environment)
    _run([meson, "compile", "-C", str(build)], env=meson_environment)
    return generated, contract, build


def build_and_run(python, systems=("cmake", "meson"), report_path=None):
    python = probe_toolchain(python)["python"]
    environment = os.environ.copy()
    environment.pop("HPY", None)
    environment["PYTHONPATH"] = str(ROOT)
    reports = []
    with TemporaryDirectory(prefix="ahpy-build-systems-") as temp_dir:
        temp = Path(temp_dir)
        for system in systems:
            if system == "cmake":
                generated, contract, build = _build_cmake(
                    python, temp, environment)
            elif system == "meson":
                generated, contract, build = _build_meson(
                    python, temp, environment)
            else:
                raise ValueError("unknown build system: %s" % system)
            matches = sorted(build.rglob(
                contract["module_name"] + contract["extension_suffix"]))
            if len(matches) != 1:
                raise AssertionError(
                    "%s produced %d Universal artifacts" % (system, len(matches)))
            artifact = matches[0]
            verify_source_boundary(
                generated,
                required=("#include <hpy.h>", "HPyType_FromSpec", "HPy_MODINIT"),
            )
            verify_binary_boundary(artifact)
            for debug in (False, True):
                _run([
                    python, "-c", _runtime_program(
                        contract["module_name"], artifact, debug),
                ], cwd=temp, env=environment)
            reports.append({
                "system": system,
                "abi": contract["abi"],
                "hpy_version": contract["hpy_version"],
                "artifact": artifact.name,
                "runtime_mode": contract["runtime_mode"],
                "runtime_modes": ["normal", "debug"],
            })
    report = {"schema_version": 1, "results": reports}
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--system", choices=("all", "cmake", "meson"), default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    systems = ("cmake", "meson") if args.system == "all" else (args.system,)
    report = build_and_run(args.python, systems, args.output)
    print("aHPy build-system integrations passed: %s" % ", ".join(
        item["system"] for item in report["results"]))


if __name__ == "__main__":
    main()
