#!/usr/bin/env python3
"""Generate a deterministic typed NOX facade from a validated manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import nox_integration_policy
import nox_manifest


NOX_KEYWORDS = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "defer", "del", "elif", "else",
    "except", "extern", "finally", "for", "from", "if", "import", "in",
    "is", "lambda", "lowlevel", "not", "or", "pass", "protocol", "raise",
    "retains", "return", "spawn", "try", "while", "with", "with_rt",
})
PLATFORM_RESERVED_NAMES = frozenset({
    "aux", "clock$", "con", "nul", "prn",
    *("com%d" % index for index in range(1, 10)),
    *("lpt%d" % index for index in range(1, 10)),
})
PACKAGE_HELPERS = frozenset({
    "Package", "close", "host_abi", "host_profile", "open_package",
    "package_root", "self",
})
OBJECT_HELPERS = frozenset({
    "close", "object", "self", "__enter__", "__exit__", "__init__",
})
NOX_TYPE_NAMES = {
    "bool": "bool",
    "bytes": "list[int]",
    "float64": "float",
    "int64": "int",
    "none": "None",
    "unicode": "str",
    "void": "None",
}


class NoxFacadeError(ValueError):
    """The validated package cannot be represented by host-v1 source."""


def _reject(diagnostic, message):
    raise NoxFacadeError("%s: %s" % (diagnostic, message))


def _quoted(value):
    return json.dumps(value, ensure_ascii=False)


def _check_name(name, context, reserved=()):
    if (name in NOX_KEYWORDS or name in reserved or name.startswith("__nox_")
            or name.casefold() in PLATFORM_RESERVED_NAMES):
        _reject("AHPY_NOX005", "%s %r collides with NOX facade names" % (
            context, name))


def _check_output_path(output):
    for part in Path(output).parts:
        normalized = part.rstrip(" .").split(".", 1)[0].casefold()
        if (part != part.rstrip(" .") or
                normalized in PLATFORM_RESERVED_NAMES):
            _reject(
                "AHPY_NOX005",
                "facade output uses a platform-reserved path component %r" % part,
            )


def _nox_type(kind, context):
    try:
        return NOX_TYPE_NAMES[kind]
    except KeyError:
        _reject(
            "AHPY_NOX008",
            "%s has no nominal NOX type in manifest schema v1" % context,
        )


def _signature_parameters(parameters, context):
    rendered = []
    for parameter in parameters:
        name = parameter["name"]
        _check_name(name, "%s parameter" % context, {"self"})
        rendered.append("%s: %s" % (
            name, _nox_type(parameter["kind"], context)))
    return ", ".join(rendered)


def _call_kind_comment(parameters):
    if not parameters:
        return None
    return "# aHPy call-kinds: " + ", ".join(
        "%s=%s" % (item["name"], item["call_kind"])
        for item in parameters
    )


def _module_call(export):
    name = export["name"]
    parameters = export["parameters"]
    result = export["result"]["kind"]
    kinds = tuple(item["kind"] for item in parameters)
    call_kinds = tuple(item["call_kind"] for item in parameters)
    arguments = [item["name"] for item in parameters]

    if not parameters:
        method = {
            "bool": "call_bool",
            "float64": "call_float",
            "int64": "call_int",
            "unicode": "call_str",
            "opaque-object": "call_object",
        }.get(result)
        if method:
            return "self._module.%s(%s)" % (method, _quoted(name))
    elif len(parameters) == 1:
        if call_kinds == ("keyword-only",) and kinds == ("int64",) and result == "int64":
            return "self._module.call_int_keyword(%s, %s, %s)" % (
                _quoted(name), _quoted(parameters[0]["name"]), arguments[0])
        method = {
            (("int64",), "int64"): "call_int_arg",
            (("float64",), "float64"): "call_float_arg",
            (("unicode",), "unicode"): "call_str_arg",
            (("bytes",), "bytes"): "call_bytes",
        }.get((kinds, result))
        if method and call_kinds[0] != "keyword-only":
            return "self._module.%s(%s, %s)" % (
                method, _quoted(name), arguments[0])
    _reject(
        "AHPY_NOX007",
        "module export %r has no nox-hpy-host-v1 call primitive" % name,
    )


def _constructor_call(export):
    parameters = export["parameters"]
    if (len(parameters) == 1 and parameters[0]["kind"] == "int64" and
            parameters[0]["call_kind"] != "keyword-only"):
        return "self._module.construct(%s, %s)" % (
            _quoted(export["name"]), parameters[0]["name"])
    _reject(
        "AHPY_NOX007",
        "constructor %r has no nox-hpy-host-v1 call primitive" % export["name"],
    )


def _method_call(export, method_name):
    parameters = export["parameters"]
    result = export["result"]["kind"]
    if not parameters and result == "int64":
        return "self._object.call(%s)" % _quoted(method_name)
    if (len(parameters) == 1 and parameters[0]["kind"] == "int64" and
            parameters[0]["call_kind"] != "keyword-only" and
            result == "int64"):
        return "self._object.call_int(%s, %s)" % (
            _quoted(method_name), parameters[0]["name"])
    _reject(
        "AHPY_NOX007",
        "method %r has no nox-hpy-host-v1 call primitive" % export["name"],
    )


def _validated_surface(manifest):
    policy = nox_integration_policy.load_policy()
    try:
        nox_manifest.validate_manifest(manifest, policy=policy)
    except nox_manifest.NoxManifestError as exc:
        raise NoxFacadeError(str(exc)) from exc
    package_name = manifest["package"]["name"]
    constructors = {}
    methods = {}
    functions = []
    package_members = set(PACKAGE_HELPERS)
    for export in manifest["exports"]:
        kind = export["kind"]
        name = export["name"]
        if kind == "constructor":
            if "." in name:
                _reject("AHPY_NOX005", "constructor name must be a class identifier")
            if name == package_name:
                _reject("AHPY_NOX005", "class collides with package name")
            _check_name(name, "class", PACKAGE_HELPERS)
            constructors[name] = export
            member_name = "new_%s" % name
            _check_name(member_name, "constructor facade", package_members)
            package_members.add(member_name)
        elif kind == "method":
            parts = name.split(".")
            if len(parts) != 2:
                _reject(
                    "AHPY_NOX005",
                    "method %r must use Class.method identity" % name,
                )
            class_name, method_name = parts
            _check_name(method_name, "method", OBJECT_HELPERS)
            class_methods = methods.setdefault(class_name, {})
            class_methods[method_name] = export
        else:
            if name == package_name:
                _reject("AHPY_NOX005", "module export collides with package name")
            _check_name(name, "module export", package_members)
            package_members.add(name)
            functions.append(export)

    orphan_classes = sorted(set(methods) - set(constructors))
    if orphan_classes:
        _reject(
            "AHPY_NOX005",
            "methods have no constructor export: %s" % ", ".join(orphan_classes),
        )
    return constructors, methods, functions


def _render_object_class(class_name, methods):
    lines = [
        "class %s:" % class_name,
        "    def __init__(self: %s, object: _ahpy_hpy.Object) -> None:" % class_name,
        "        self._object = object",
        "",
        "    def close(self: %s) -> None:" % class_name,
        "        self._object.close()",
        "",
        "    def __enter__(self: %s) -> %s:" % (class_name, class_name),
        "        return self",
        "",
        "    def __exit__(self: %s) -> None:" % class_name,
        "        self.close()",
    ]
    for method_name in sorted(methods):
        export = methods[method_name]
        parameters = export["parameters"]
        result_type = _nox_type(export["result"]["kind"], export["name"])
        signature = _signature_parameters(parameters, export["name"])
        suffix = (", " + signature) if signature else ""
        comment = _call_kind_comment(parameters)
        call = _method_call(export, method_name)
        lines.extend([""])
        if comment:
            lines.append("    " + comment)
        lines.extend([
            "    def %s(self: %s%s) -> %s:" % (
                method_name, class_name, suffix, result_type),
            "        try:",
            "            return %s" % call,
            "        except HPyError as error:",
            "            raise _export_error(%s, error)" % _quoted(export["name"]),
        ])
    return lines


def generate_facade(manifest):
    constructors, methods, functions = _validated_surface(manifest)
    lines = [
        "# Generated by aHPy from canonical nox-hpy schema v1; do not edit.",
        "# Package: %s %s" % (
            manifest["package"]["name"], manifest["package"]["version"]),
        "import nox.hpy as _ahpy_hpy",
        "",
        "def _export_error(identity: str, error: HPyError) -> HPyError:",
        "    return HPyError(\"aHPy export \" + identity + \": \" + error.message)",
    ]
    for class_name in sorted(constructors):
        lines.extend([""] + _render_object_class(
            class_name, methods.get(class_name, {})))

    lines.extend([
        "",
        "class Package:",
        "    def __init__(self: Package, package_root: str) -> None:",
        "        if _ahpy_hpy.host_profile() != %s:" % _quoted(
            manifest["host"]["profile"]),
        "            raise HPyError(\"AHPY_NOX003: incompatible NOX HPy host profile\")",
        "        if _ahpy_hpy.host_abi() != %s:" % _quoted(
            manifest["host"]["hpy_abi"]),
        "            raise HPyError(\"AHPY_NOX003: incompatible HPy ABI\")",
        "        self._module = _ahpy_hpy.load_package(package_root)",
        "",
        "    def close(self: Package) -> None:",
        "        self._module.close()",
        "",
        "    def __enter__(self: Package) -> Package:",
        "        return self",
        "",
        "    def __exit__(self: Package) -> None:",
        "        self.close()",
    ])

    for class_name in sorted(constructors):
        export = constructors[class_name]
        parameters = export["parameters"]
        signature = _signature_parameters(parameters, export["name"])
        suffix = (", " + signature) if signature else ""
        comment = _call_kind_comment(parameters)
        call = _constructor_call(export)
        lines.append("")
        if comment:
            lines.append("    " + comment)
        lines.extend([
            "    def new_%s(self: Package%s) -> %s:" % (
                class_name, suffix, class_name),
            "        try:",
            "            return %s(%s)" % (class_name, call),
            "        except HPyError as error:",
            "            raise _export_error(%s, error)" % _quoted(export["name"]),
        ])

    for export in sorted(functions, key=lambda item: item["name"]):
        name = export["name"]
        parameters = export["parameters"]
        signature = _signature_parameters(parameters, name)
        suffix = (", " + signature) if signature else ""
        result_type = _nox_type(export["result"]["kind"], name)
        comment = _call_kind_comment(parameters)
        call = _module_call(export)
        lines.append("")
        if comment:
            lines.append("    " + comment)
        lines.extend([
            "    def %s(self: Package%s) -> %s:" % (
                name, suffix, result_type),
            "        try:",
            "            return %s" % call,
            "        except HPyError as error:",
            "            raise _export_error(%s, error)" % _quoted(name),
        ])

    lines.extend([
        "",
        "def open_package(package_root: str) -> Package:",
        "    return Package(package_root)",
        "",
    ])
    return ("\n".join(lines)).encode("utf8")


def write_facade(manifest, output, check=False):
    rendered = generate_facade(manifest)
    output = Path(output)
    _check_output_path(output)
    if check:
        try:
            existing = output.read_bytes()
        except OSError as exc:
            raise NoxFacadeError("cannot read facade %s: %s" % (
                output, exc)) from exc
        if existing != rendered:
            raise NoxFacadeError("%s is stale or non-canonical" % output)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
    return rendered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(argv)
    if options.check and options.output is None:
        parser.error("--check requires --output")
    try:
        manifest = nox_manifest.load_manifest(options.manifest)
        if options.output is None:
            sys.stdout.buffer.write(generate_facade(manifest))
        else:
            write_facade(manifest, options.output, check=options.check)
    except (NoxFacadeError, nox_manifest.NoxManifestError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
