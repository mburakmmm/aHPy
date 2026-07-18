#!/usr/bin/env python3
"""Build one generated Universal HPy C file without setuptools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_build_config import (
    probe_toolchain,
    resolve_python,
    select_universal_runtime,
    validate_module_name,
)
from test_generated_hpy import verify_binary_boundary, verify_source_boundary


SCHEMA_VERSION = 1


def _split_flags(value):
    return shlex.split(value or "", posix=os.name != "nt")


def _is_msvc(command, probe):
    if probe["os_name"] != "nt" or not command:
        return False
    return Path(command[0]).name.lower() in ("cl", "cl.exe")


def _validate_inputs(module_name, source, output_dir, build_dir):
    validate_module_name(module_name)
    source = Path(source).absolute()
    if source.suffix.lower() != ".c" or not source.is_file():
        raise ValueError("generated source must be an existing .c file: %s" % source)
    output_dir = Path(output_dir).absolute()
    build_dir = Path(build_dir).absolute()
    if output_dir == build_dir:
        raise ValueError("output and intermediate build directories must differ")
    return source, output_dir, build_dir


def create_build_plan(
    probe,
    module_name,
    source,
    output_dir,
    build_dir,
    *,
    runtime="auto",
    extra_sources=(),
    compiler=None,
    cflags=(),
    ldflags=(),
):
    """Return a serializable, executable direct-build plan."""
    source, output_dir, build_dir = _validate_inputs(
        module_name, source, output_dir, build_dir)
    suffix = probe["extension_suffix"]
    runtime_mode, runtime_inputs = select_universal_runtime(probe, runtime)
    artifact = output_dir / (module_name + suffix)

    compiler_value = compiler or probe["config"]["CC"]
    compiler_command = _split_flags(compiler_value)
    if not compiler_command:
        compiler_command = ["cl" if probe["os_name"] == "nt" else "cc"]
    msvc = _is_msvc(compiler_command, probe)

    use_static = runtime_mode == "static"
    static_libraries = runtime_inputs if use_static else []
    runtime_sources = [] if use_static else runtime_inputs
    sources = [str(source)] + [str(Path(item).absolute()) for item in extra_sources]
    sources.extend(runtime_sources)
    for item in sources:
        if not Path(item).is_file():
            raise ValueError("direct-build source does not exist: %s" % item)

    include_dirs = [probe["forbid_python_h"]] + list(probe["include_dirs"])
    object_suffix = ".obj" if msvc else ".o"
    objects = [
        str(build_dir / ("%03d_%s%s" % (
            index, Path(item).stem, object_suffix)))
        for index, item in enumerate(sources)
    ]

    compile_commands = []
    if msvc:
        base = compiler_command + [
            "/nologo", "/c", "/O2", "/MD", "/DHPY",
            "/DHPY_ABI_UNIVERSAL",
        ]
        base.extend("/I%s" % value for value in include_dirs)
        base.extend(cflags)
        for item, object_path in zip(sources, objects):
            compile_commands.append(base + [item, "/Fo%s" % object_path])
        link_command = compiler_command + ["/nologo", "/LD"] + objects
        if use_static:
            link_command.extend(static_libraries)
        link_command.extend(ldflags)
        link_command.extend([
            "/link", "/EXPORT:HPyInit_%s" % module_name,
            "/OUT:%s" % artifact,
        ])
    else:
        base = compiler_command
        base += _split_flags(probe["config"].get("CFLAGS"))
        base += _split_flags(probe["config"].get("CCSHARED"))
        base += ["-O2", "-fPIC", "-DHPY", "-DHPY_ABI_UNIVERSAL"]
        base += ["-I%s" % value for value in include_dirs]
        base += list(cflags)
        for item, object_path in zip(sources, objects):
            compile_commands.append(base + ["-c", item, "-o", object_path])

        configured_linker = _split_flags(probe["config"].get("LDSHARED"))
        if compiler:
            link_command = compiler_command + configured_linker[1:]
        else:
            link_command = configured_linker or compiler_command + ["-shared"]
        link_command += _split_flags(probe["config"].get("LDFLAGS"))
        link_command += objects
        if use_static:
            link_command.extend(static_libraries)
        link_command += list(ldflags) + ["-o", str(artifact)]

    return {
        "schema_version": SCHEMA_VERSION,
        "abi": "universal",
        "module_name": module_name,
        "python": probe["python"],
        "hpy_version": probe["hpy_version"],
        "platform": probe["platform"],
        "machine": probe["machine"],
        "source": str(source),
        "output_dir": str(output_dir),
        "build_dir": str(build_dir),
        "artifact": str(artifact),
        "include_dirs": include_dirs,
        "runtime_mode": "static" if use_static else "sources",
        "runtime_inputs": static_libraries if use_static else runtime_sources,
        "compile_commands": compile_commands,
        "link_command": link_command,
    }


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_build_plan(plan):
    """Execute a validated plan and return its artifact manifest."""
    source = Path(plan["source"])
    output_dir = Path(plan["output_dir"])
    build_dir = Path(plan["build_dir"])
    artifact = Path(plan["artifact"])
    verify_source_boundary(
        source, required=("#include <hpy.h>", "HPy_MODINIT"))
    if artifact.exists():
        raise RuntimeError("refusing to overwrite direct-build artifact: %s" % artifact)
    if build_dir.exists() and any(build_dir.iterdir()):
        raise RuntimeError(
            "direct-build intermediate directory is not empty: %s" % build_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for command in plan["compile_commands"] + [plan["link_command"]]:
        subprocess.run(command, check=True, env=environment)
    if not artifact.is_file():
        raise RuntimeError("direct linker did not create %s" % artifact)
    verify_binary_boundary(artifact)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "abi": "universal",
        "module_name": plan["module_name"],
        "hpy_version": plan["hpy_version"],
        "artifact": artifact.name,
        "sha256": _file_sha256(artifact),
        "size": artifact.stat().st_size,
        "runtime_mode": plan["runtime_mode"],
    }
    manifest_path = output_dir / (plan["module_name"] + ".direct-build.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--module", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--runtime", choices=("auto", "static", "sources"),
                        default="auto")
    parser.add_argument("--extra-source", type=Path, action="append", default=[])
    parser.add_argument("--cc")
    parser.add_argument("--cflag", action="append", default=[])
    parser.add_argument("--ldflag", action="append", default=[])
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    probe = probe_toolchain(args.python)
    plan = create_build_plan(
        probe, args.module, args.source, args.output_dir, args.build_dir,
        runtime=args.runtime, extra_sources=args.extra_source,
        compiler=args.cc or os.environ.get("CC"),
        cflags=args.cflag, ldflags=args.ldflag)
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf8")
    if args.plan_only:
        if not args.json_output:
            sys.stdout.write(rendered)
        return 0
    manifest = execute_build_plan(plan)
    print("direct Universal HPy artifact built: %s (%s)" % (
        plan["artifact"], manifest["sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
