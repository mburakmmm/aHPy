#!/usr/bin/env python3
"""Build and execute the generated Universal HPy corpus with sanitizers."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
GENERATED_TEST = ROOT / "Tools" / "ahpy" / "test_generated_hpy.py"


def append_flags(environment, variable, flags):
    existing = environment.get(variable, "").strip()
    environment[variable] = " ".join(part for part in (existing, flags) if part)


def sanitizer_environment(cc, sanitizers):
    environment = os.environ.copy()
    flags = (
        "-O1 -g -fno-omit-frame-pointer -fno-sanitize-recover=all "
        "-fsanitize=%s" % sanitizers
    )
    environment["CC"] = cc
    append_flags(environment, "CFLAGS", flags)
    append_flags(environment, "LDFLAGS", "-fsanitize=%s" % sanitizers)
    environment["ASAN_OPTIONS"] = (
        "abort_on_error=1:detect_leaks=0:strict_string_checks=1"
    )
    environment["UBSAN_OPTIONS"] = (
        "halt_on_error=1:print_stacktrace=1"
    )

    if "address" in sanitizers and sys.platform.startswith("linux"):
        result = subprocess.run(
            [cc, "-print-file-name=libasan.so"],
            check=True,
            capture_output=True,
            text=True,
        )
        libasan = result.stdout.strip()
        if not libasan or libasan == "libasan.so" or not Path(libasan).is_file():
            raise RuntimeError("compiler did not report an existing libasan.so")
        previous = environment.get("LD_PRELOAD", "")
        environment["LD_PRELOAD"] = ":".join(
            value for value in (libasan, previous) if value)

    if "address" in sanitizers and sys.platform == "darwin":
        runtime_name = "libclang_rt.asan_osx_dynamic.dylib"
        result = subprocess.run(
            [cc, "-print-file-name=" + runtime_name],
            check=True,
            capture_output=True,
            text=True,
        )
        runtime = result.stdout.strip()
        if not runtime or runtime == runtime_name or not Path(runtime).is_file():
            raise RuntimeError(
                "compiler did not report an existing Apple ASan runtime")
        previous = environment.get("DYLD_INSERT_LIBRARIES", "")
        environment["DYLD_INSERT_LIBRARIES"] = ":".join(
            value for value in (runtime, previous) if value)
        # dyld may consume/remove DYLD_* variables when the first Python
        # process starts. Preserve the value under an application-owned name
        # so the generated test can restore it for every child interpreter.
        environment["AHPY_DYLD_INSERT_LIBRARIES"] = environment[
            "DYLD_INSERT_LIBRARIES"]

    return environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"))
    parser.add_argument("--sanitizers", default="address,undefined")
    args = parser.parse_args()

    python = shutil.which(args.python) or args.python
    environment = sanitizer_environment(args.cc, args.sanitizers)
    subprocess.run(
        [python, str(GENERATED_TEST), "--python", python],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    print("Generated Universal HPy module: ASan/UBSan gate passed")


if __name__ == "__main__":
    main()
