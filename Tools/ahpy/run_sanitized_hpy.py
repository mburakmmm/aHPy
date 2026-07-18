#!/usr/bin/env python3
"""Build and execute the generated Universal HPy corpus with sanitizers."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
GENERATED_TEST = ROOT / "Tools" / "ahpy" / "test_generated_hpy.py"

APPLE_PRELOAD_PROBE = r'''
import ctypes
import os

runtime = os.environ["AHPY_ASAN_RUNTIME"]
ctypes.CDLL(runtime, mode=os.RTLD_NOLOAD | os.RTLD_LAZY)
print("Apple ASan runtime preloaded: %s" % runtime)
'''

APPLE_PYTHON_CONFIG_PROBE = r'''
import json
import sysconfig

print(json.dumps({
    "bindir": sysconfig.get_config_var("BINDIR"),
    "version": sysconfig.get_config_var("VERSION"),
}))
'''

APPLE_SANITIZER_LAUNCHER = r'''
#include <Python.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    const char *selected_python = getenv("AHPY_REAL_PYTHON");
    if (selected_python != NULL && selected_python[0] != '\0') {
        argv[0] = (char *)selected_python;
    }
    return Py_BytesMain(argc, argv);
}
'''


def append_flags(environment, variable, flags):
    existing = environment.get(variable, "").strip()
    environment[variable] = " ".join(part for part in (existing, flags) if part)


def sanitizer_environment(cc, sanitizers):
    environment = os.environ.copy()
    flags = (
        "-O0 -g -fno-omit-frame-pointer -fno-sanitize-recover=all "
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
        machine = platform.machine().lower()
        if machine not in ("arm64", "x86_64"):
            raise RuntimeError(
                "unsupported macOS sanitizer architecture: %s" % machine)
        # actions/setup-python may report a universal2 build platform even on
        # a native ARM64 runner.  Distutils honours ARCHFLAGS as the explicit
        # native override for both compilation and linking.
        environment["ARCHFLAGS"] = "-arch " + machine
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
        # Signed Python launchers can discard DYLD_INSERT_LIBRARIES.  The
        # macOS lane therefore links a tiny Python launcher against this exact
        # runtime instead of relying on an ambient dyld environment variable.
        environment.pop("DYLD_INSERT_LIBRARIES", None)
        environment.pop("AHPY_DYLD_INSERT_LIBRARIES", None)
        environment["AHPY_ASAN_RUNTIME"] = runtime

    return environment


@contextmanager
def macos_sanitizer_python(python, cc, sanitizers, environment):
    """Yield an ASan-linked launcher for the selected Python runtime."""
    metadata_result = subprocess.run(
        [python, "-c", APPLE_PYTHON_CONFIG_PROBE],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(metadata_result.stdout)
    config_candidates = (
        Path(metadata["bindir"]) /
        ("python%s-config" % metadata["version"]),
        Path(metadata["bindir"]) / "python-config",
    )
    python_config = next(
        (candidate for candidate in config_candidates if candidate.is_file()),
        None,
    )
    if python_config is None:
        raise RuntimeError(
            "selected Python has no python-config embed helper in %s" %
            metadata["bindir"])
    flags_result = subprocess.run(
        [str(python_config), "--embed", "--cflags", "--ldflags"],
        check=True,
        capture_output=True,
        text=True,
    )
    config_flags = shlex.split(flags_result.stdout)
    native_flags = []
    index = 0
    while index < len(config_flags):
        if config_flags[index] == "-arch" and index + 1 < len(config_flags):
            index += 2
            continue
        native_flags.append(config_flags[index])
        index += 1

    with tempfile.TemporaryDirectory(prefix="ahpy-asan-launcher-") as temp:
        temp_path = Path(temp)
        source = temp_path / "asan_python.c"
        launcher = temp_path / "asan-python"
        source.write_text(APPLE_SANITIZER_LAUNCHER, encoding="utf8")
        command = (
            shlex.split(cc) +
            [str(source), "-o", str(launcher)] +
            native_flags +
            shlex.split(environment["ARCHFLAGS"]) +
            ["-O1", "-g", "-fno-omit-frame-pointer",
             "-fsanitize=" + sanitizers]
        )
        subprocess.run(command, check=True)
        otool = shutil.which("otool")
        if otool is None:
            raise RuntimeError("otool is required for the macOS ASan lane")
        linked = subprocess.run(
            [otool, "-L", str(launcher)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        runtime = environment["AHPY_ASAN_RUNTIME"]
        if os.path.basename(runtime) not in linked:
            raise RuntimeError(
                "sanitizer launcher does not link the selected runtime: %s" %
                runtime)
        environment["AHPY_REAL_PYTHON"] = os.path.abspath(python)
        yield str(launcher)


def verify_macos_preload(python, environment):
    runtime = environment["AHPY_ASAN_RUNTIME"]
    result = subprocess.run(
        [python, "-c", APPLE_PRELOAD_PROBE],
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Apple ASan preload probe failed with exit %d: %s" %
            (result.returncode, (result.stderr or result.stdout).strip()))
    print(result.stdout.strip())
    print(
        "macOS sanitizer contract: arch=%s python=%s" %
        (environment["ARCHFLAGS"], python),
        flush=True,
    )
    return runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"))
    parser.add_argument("--sanitizers", default="address,undefined")
    args = parser.parse_args()

    python = shutil.which(args.python) or args.python
    environment = sanitizer_environment(args.cc, args.sanitizers)
    if sys.platform == "darwin" and "address" in args.sanitizers:
        with macos_sanitizer_python(
            python, args.cc, args.sanitizers, environment,
        ) as sanitizer_python:
            verify_macos_preload(sanitizer_python, environment)
            subprocess.run(
                [sanitizer_python, str(GENERATED_TEST),
                 "--python", sanitizer_python],
                cwd=ROOT,
                env=environment,
                check=True,
            )
    else:
        subprocess.run(
            [python, str(GENERATED_TEST), "--python", python],
            cwd=ROOT,
            env=environment,
            check=True,
        )
    print("Generated Universal HPy module: ASan/UBSan gate passed")


if __name__ == "__main__":
    main()
