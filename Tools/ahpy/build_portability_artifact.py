#!/usr/bin/env python3
"""Build a CPython-hosted Universal artifact for other interpreters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from artifact_utils import find_universal_binaries
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary
from test_minimal_hpy import verify_source_boundary as verify_minimal_source_boundary


ROOT = Path(__file__).resolve().parents[2]
GENERATED_SOURCES = (
    ("constants_only", ROOT / "tests" / "ahpy" / "constants_only.pyx"),
    (
        "fibonacci",
        ROOT / "tests" / "ahpy" / "pilot_ports" / "cypack" / "src" /
        "cypack" / "fibonacci.pyx",
    ),
    ("bootstrap_answer", ROOT / "tests" / "ahpy" / "bootstrap_answer.pyx"),
    ("bootstrap_types", ROOT / "tests" / "ahpy" / "bootstrap_types.pyx"),
)
HANDWRITTEN_SOURCES = (
    ("ahpy_minimal", ROOT / "tests" / "ahpy" / "minimal_universal.c"),
)
SOURCES = GENERATED_SOURCES + HANDWRITTEN_SOURCES
SMOKE = ROOT / "Tools" / "ahpy" / "portability_smoke.py"


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_flag(environment, variable, flag):
    existing = environment.get(variable, "").strip()
    environment[variable] = " ".join(
        value for value in (existing, flag) if value)


def build_artifact(python, output):
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("artifact output directory is not empty: %s" % output)
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="ahpy-portability-") as temp_dir:
        temp = Path(temp_dir)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        environment["SOURCE_DATE_EPOCH"] = "946684800"
        environment["ZERO_AR_DATE"] = "1"
        reproducible_paths = (
            "-ffile-prefix-map=%s=/ahpy-build "
            "-fdebug-prefix-map=%s=/ahpy-build" % (temp, temp)
        )
        _append_flag(environment, "CFLAGS", reproducible_paths)
        _append_flag(environment, "CXXFLAGS", reproducible_paths)
        generated_sources = []
        for module_name, source in GENERATED_SOURCES:
            generated = temp / (module_name + ".c")
            run([
                python,
                "-m", "cython",
                "--runtime-backend=hpy-universal",
                "-3",
                "-o", str(generated),
                str(source),
            ], cwd=ROOT, env=environment)
            verify_source_boundary(
                generated,
                required=(
                    "#include <hpy.h>",
                    "HPy_mod_exec",
                    "HPy_MODINIT",
                ) + (() if module_name == "constants_only" else (
                    "HPyDef_METH",
                )),
            )
            generated_sources.append(generated)

        for _module_name, source in HANDWRITTEN_SOURCES:
            verify_minimal_source_boundary()
            copied = temp / source.name
            shutil.copy2(source, copied)

        setup = temp / "setup.py"
        setup_sources = (
            tuple((module_name, module_name + ".c")
                  for module_name, _source in GENERATED_SOURCES) +
            tuple((module_name, source.name)
                  for module_name, source in HANDWRITTEN_SOURCES)
        )
        extensions = "\n".join(
            "    Extension(%r, [%r])," % (module_name, source_name)
            for module_name, source_name in setup_sources
        )
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "from ahpy_hpy_compat import install_hpy_universal_loader_compat\n"
            "install_hpy_universal_loader_compat()\n"
            "setup(name='ahpy-portability', version='0.0.0', "
            "packages=[], py_modules=[], hpy_ext_modules=[\n"
            + extensions + "\n"
            "])\n",
            encoding="utf8",
        )
        build_root = temp / "build"
        run([
            python,
            str(setup),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)

        binaries = find_universal_binaries(build_root)
        if len(binaries) != len(SOURCES):
            raise AssertionError(
                "expected %d Universal binaries, got %r" %
                (len(SOURCES), binaries))
        build_lib = binaries[0].parent
        for binary in binaries:
            if binary.parent != build_lib:
                raise AssertionError("Universal binaries used different build dirs")
            verify_binary_boundary(binary)
        artifact_names = []
        for module_name, _ in SOURCES:
            candidates = (
                find_universal_binaries(build_lib, module_name) +
                [build_lib / (module_name + ".py")]
            )
            for candidate in candidates:
                if not candidate.is_file():
                    raise AssertionError("missing artifact file: %s" % candidate)
                destination = output / candidate.name
                shutil.copy2(candidate, destination)
                artifact_names.append(destination.name)
        shutil.copy2(SMOKE, output / SMOKE.name)
        artifact_names.append(SMOKE.name)

    manifest = {
        "schema_version": 1,
        "builder": subprocess.check_output(
            [python, "-c", "import platform; print(platform.python_implementation() + ' ' + platform.python_version())"],
            text=True,
        ).strip(),
        "files": [
            {
                "name": name,
                "sha256": file_sha256(output / name),
                "size": (output / name).stat().st_size,
            }
            for name in sorted(artifact_names)
        ],
    }
    (output / "artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    python_path = Path(args.python)
    if python_path.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    build_artifact(python, args.output.absolute())
    print("Universal HPy portability artifact built: %s" % args.output)


if __name__ == "__main__":
    main()
