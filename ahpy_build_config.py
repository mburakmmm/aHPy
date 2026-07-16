"""Public Universal HPy toolchain contract for external build systems."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess


SCHEMA_VERSION = 1
_C_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_PROBE = r'''
import json
import os
import platform
import sys
import sysconfig
from hpy.devel import HPyDevel
from hpy.devel.abitag import get_hpy_ext_suffix

devel = HPyDevel()
print(json.dumps({
    "python": sys.executable,
    "platform": sys.platform,
    "os_name": os.name,
    "machine": platform.machine(),
    "hpy_version": __import__("importlib.metadata").metadata.version("hpy"),
    "extension_suffix": get_hpy_ext_suffix("universal"),
    "include_dirs": devel.get_extra_include_dirs(),
    "forbid_python_h": str(devel.get_include_dir_forbid_python_h()),
    "runtime_sources": devel.get_extra_sources(),
    "static_libraries": devel.get_static_libs("universal") or [],
    "config": {name: (sysconfig.get_config_var(name) or "") for name in (
        "CC", "CFLAGS", "CCSHARED", "LDSHARED", "LDFLAGS")},
}, sort_keys=True))
'''


def resolve_python(python):
    path = Path(python)
    if path.exists():
        return os.path.abspath(python)
    resolved = shutil.which(python)
    if resolved is None:
        raise ValueError("Python interpreter not found: %s" % python)
    return resolved


def probe_toolchain(python):
    python = resolve_python(python)
    result = subprocess.run(
        [python, "-c", _PROBE], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "selected Python cannot describe its HPy toolchain: %s" %
            (result.stderr or result.stdout).strip())
    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid HPy toolchain probe JSON: %s" % exc) from exc
    probe["python"] = python
    return probe


def validate_module_name(module_name):
    if not _C_IDENTIFIER.match(module_name):
        raise ValueError("module name must be one plain C identifier")
    return module_name


def select_universal_runtime(probe, runtime="auto"):
    if runtime not in ("auto", "static", "sources"):
        raise ValueError("runtime must be auto, static, or sources")
    suffix = probe["extension_suffix"]
    if not suffix.startswith(".hpy0."):
        raise RuntimeError("HPy returned a non-Universal suffix: %s" % suffix)
    static_libraries = list(probe.get("static_libraries") or ())
    if runtime == "static" and len(static_libraries) != 1:
        raise RuntimeError(
            "static Universal runtime requires exactly one library, got %r" %
            static_libraries)
    use_static = runtime == "static" or (
        runtime == "auto" and len(static_libraries) == 1)
    inputs = static_libraries if use_static else list(probe["runtime_sources"])
    if use_static and len(inputs) != 1:
        raise RuntimeError(
            "Universal runtime selection requires exactly one static library")
    for item in inputs:
        if not Path(item).is_file():
            raise ValueError("Universal runtime input does not exist: %s" % item)
    return "static" if use_static else "sources", inputs


def create_contract(probe, module_name, runtime="auto"):
    validate_module_name(module_name)
    runtime_mode, runtime_inputs = select_universal_runtime(probe, runtime)
    include_dirs = [probe["forbid_python_h"]] + list(probe["include_dirs"])
    for path in include_dirs:
        if not Path(path).is_dir():
            raise ValueError("HPy include directory does not exist: %s" % path)
    return {
        "schema_version": SCHEMA_VERSION,
        "abi": "universal",
        "module_name": module_name,
        "initializer": "HPyInit_%s" % module_name,
        "python": probe["python"],
        "hpy_version": probe["hpy_version"],
        "platform": probe["platform"],
        "machine": probe["machine"],
        "is_windows": probe["os_name"] == "nt",
        "extension_suffix": probe["extension_suffix"],
        "name_suffix": probe["extension_suffix"].removeprefix("."),
        "definitions": ["HPY", "HPY_ABI_UNIVERSAL"],
        "include_dirs": include_dirs,
        "runtime_mode": runtime_mode,
        "runtime_library": runtime_inputs[0] if runtime_mode == "static" else "",
        "runtime_sources": runtime_inputs if runtime_mode == "sources" else [],
    }


def _cmake_quote(value):
    value = str(value)
    if "\n" in value or "\r" in value or ";" in value:
        raise ValueError("CMake contract path contains unsupported characters")
    return '"%s"' % value.replace("\\", "/").replace('"', '\\"')


def render_cmake(contract):
    def scalar(name, value):
        return "set(%s %s)" % (name, _cmake_quote(value))

    def array(name, values):
        if not values:
            return "set(%s)" % name
        return "set(%s\n  %s\n)" % (
            name, "\n  ".join(_cmake_quote(value) for value in values))

    lines = [
        "# Generated by aHPy ahpy_build_config; do not edit.",
        scalar("AHPY_ABI", contract["abi"]),
        scalar("AHPY_MODULE_NAME", contract["module_name"]),
        scalar("AHPY_INITIALIZER", contract["initializer"]),
        scalar("AHPY_EXTENSION_SUFFIX", contract["extension_suffix"]),
        scalar("AHPY_RUNTIME_MODE", contract["runtime_mode"]),
        scalar("AHPY_RUNTIME_LIBRARY", contract["runtime_library"]),
        scalar("AHPY_WINDOWS", "TRUE" if contract["is_windows"] else "FALSE"),
        array("AHPY_DEFINITIONS", contract["definitions"]),
        array("AHPY_INCLUDE_DIRS", contract["include_dirs"]),
        array("AHPY_RUNTIME_SOURCES", contract["runtime_sources"]),
    ]
    return "\n".join(lines) + "\n"


def _meson_quote(value):
    value = str(value)
    if "\n" in value or "\r" in value:
        raise ValueError("Meson contract path contains a newline")
    return "'%s'" % value.replace("\\", "\\\\").replace("'", "\\'")


def render_meson(contract):
    def scalar(name, value):
        return "%s = %s" % (name, _meson_quote(value))

    def array(name, values):
        return "%s = [%s]" % (
            name, ", ".join(_meson_quote(value) for value in values))

    lines = [
        "# Generated by aHPy ahpy_build_config; do not edit.",
        scalar("ahpy_abi", contract["abi"]),
        scalar("ahpy_module_name", contract["module_name"]),
        scalar("ahpy_initializer", contract["initializer"]),
        scalar("ahpy_name_suffix", contract["name_suffix"]),
        scalar("ahpy_runtime_mode", contract["runtime_mode"]),
        scalar("ahpy_runtime_library", contract["runtime_library"]),
        "ahpy_windows = %s" % ("true" if contract["is_windows"] else "false"),
        array("ahpy_definitions", contract["definitions"]),
        array("ahpy_include_dirs", contract["include_dirs"]),
        array("ahpy_runtime_sources", contract["runtime_sources"]),
    ]
    return "\n".join(lines) + "\n"
