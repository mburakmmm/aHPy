#!/usr/bin/env python3
"""Generate, directly build, audit, and load a Universal HPy artifact."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from direct_build import create_build_plan, execute_build_plan, probe_toolchain


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests" / "ahpy" / "bootstrap_answer.pyx"


def _runtime_program(artifact, mode):
    debug = mode == "debug"
    return (
        "from importlib.machinery import ModuleSpec\n"
        "import hpy.universal as universal\n" +
        ("from hpy.debug import LeakDetector\n"
         "detector = LeakDetector()\n"
         "detector.start()\n" if debug else "") +
        "path = %r\n" % str(artifact) +
        "spec = ModuleSpec('bootstrap_answer', None, origin=path)\n"
        "module = universal.load('bootstrap_answer', path, spec, %s)\n" % (
            "universal.MODE_DEBUG" if debug else "universal.MODE_UNIVERSAL") +
        "assert module.answer() == 42\n"
        "assert module.make_list() == [1, None, 2]\n" +
        ("detector.stop()\n" if debug else "")
    )


def build_and_run(python):
    python = probe_toolchain(python)["python"]
    with TemporaryDirectory(prefix="ahpy-direct-build-") as temp_dir:
        temp = Path(temp_dir)
        generated = temp / "bootstrap_answer.c"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        subprocess.run([
            python, "-m", "cython", "--runtime-backend=hpy-universal",
            "-3", "-o", str(generated), str(SOURCE),
        ], cwd=ROOT, env=environment, check=True)
        probe = probe_toolchain(python)
        plan = create_build_plan(
            probe,
            "bootstrap_answer",
            generated,
            temp / "artifact",
            temp / "objects",
            runtime="auto",
            compiler=os.environ.get("CC"),
            cflags=("-O0",) if probe["os_name"] != "nt" else ("/Od",),
        )
        manifest = execute_build_plan(plan)
        artifact = Path(plan["artifact"])
        try:
            execute_build_plan(plan)
        except RuntimeError as exc:
            if "refusing to overwrite" not in str(exc):
                raise
        else:
            raise AssertionError("direct build overwrote an existing artifact")
        for mode in ("normal", "debug"):
            subprocess.run(
                [python, "-c", _runtime_program(artifact, mode)],
                cwd=temp, env=environment, check=True)
        if manifest["abi"] != "universal":
            raise AssertionError("direct build manifest changed ABI")
        return artifact.name, manifest["runtime_mode"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    artifact, runtime_mode = build_and_run(args.python)
    print("aHPy direct Universal build passed: %s runtime=%s" % (
        artifact, runtime_mode))


if __name__ == "__main__":
    main()
