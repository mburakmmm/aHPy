"""Compiler-owned export analysis for the aHPy -> NOX package contract."""

from __future__ import annotations

import re

from . import Nodes, PyrexTypes
from .Errors import CompileError


PROTOCOL = "ahpy-nox-export-analysis-v1"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_BASE_CAPABILITIES = {
    "call-positional",
    "error-take",
    "extension-object",
    "module-close",
    "module-open",
    "object-close",
}


def _reject(node, diagnostic, message):
    raise CompileError(
        getattr(node, "pos", None),
        "aHPy NOX export [%s]: %s" % (diagnostic, message),
    )


def _value_kind(value_type, node):
    """Map an analysed Cython type to the closed NOX host-v1 vocabulary."""
    value_type = value_type.resolve()
    if value_type.is_memoryviewslice or value_type.is_buffer:
        _reject(node, "AHPY_NOX008", "memoryview/buffer types are unsupported")
    if value_type.is_ptr or value_type.is_array or value_type.is_cfunction:
        _reject(node, "AHPY_NOX008", "pointer, array, and callback types are unsupported")
    if value_type.is_fused:
        _reject(node, "AHPY_NOX008", "fused/overloaded types are unsupported")
    if value_type.is_pytuple_type or value_type.is_pylist_type or value_type.is_pydict_type:
        _reject(node, "AHPY_NOX008", "container types are unsupported")
    if value_type.is_pybool_type or value_type is PyrexTypes.c_bint_type:
        return "bool"
    if value_type.is_pyint_type or value_type is PyrexTypes.c_longlong_type:
        return "int64"
    if value_type.is_pyfloat_type or value_type is PyrexTypes.c_double_type:
        return "float64"
    if value_type.is_pystr_type:
        return "unicode"
    if value_type.is_pybytes_type:
        return "bytes"
    if value_type.is_void:
        return "void"
    if value_type.is_extension_type or value_type is PyrexTypes.py_object_type:
        return "opaque-object"
    _reject(node, "AHPY_NOX008", "type %r is outside nox-hpy-host-v1" % value_type)


def _parameter(argument, capabilities):
    if argument.default is not None:
        _reject(
            argument,
            "AHPY_NOX007",
            "default arguments are not representable by manifest v1",
        )
    name = str(argument.name)
    if not _IDENTIFIER.fullmatch(name):
        _reject(argument, "AHPY_NOX005", "parameter names must be ASCII identifiers")
    kind = _value_kind(argument.type, argument)
    if argument.kw_only:
        call_kind = "keyword-only"
        capabilities.add("call-keywords")
    elif argument.pos_only:
        call_kind = "positional-only"
    else:
        call_kind = "positional-or-keyword"
        capabilities.add("call-keywords")
    if kind == "bytes":
        capabilities.add("bytes")
    return {
        "name": name,
        "kind": kind,
        "call_kind": call_kind,
        "ownership": "borrowed" if kind == "opaque-object" else "value",
    }


def _callable_export(node, kind, name, capabilities, skip_receiver=False):
    if node.star_arg is not None or node.starstar_arg is not None:
        _reject(node, "AHPY_NOX007", "variadic exports are unsupported")
    if not all(_IDENTIFIER.fullmatch(part) for part in name.split(".")):
        _reject(node, "AHPY_NOX005", "export names must be dotted ASCII identifiers")
    arguments = node.args[1:] if skip_receiver else node.args
    parameters = [_parameter(argument, capabilities) for argument in arguments]
    if kind == "constructor":
        result = {"kind": "opaque-object", "ownership": "owned"}
    else:
        result_kind = _value_kind(node.return_type, node)
        if result_kind == "void":
            result = {"kind": "void", "ownership": "value"}
        else:
            result = {
                "kind": result_kind,
                "ownership": "owned" if result_kind == "opaque-object" else "value",
            }
        if result_kind == "bytes":
            capabilities.add("bytes")
    return {
        "kind": kind,
        "name": name,
        "parameters": parameters,
        "result": result,
    }


def analyze_hpy_exports(module_node, methods, extension_types):
    """Return a deterministic descriptor derived only from analysed AST data."""
    capabilities = set(_BASE_CAPABILITIES)
    exports = []
    for method in methods:
        if not method.name.startswith("_"):
            exports.append(_callable_export(
                method, "module-function", str(method.name), capabilities))
    for extension_type in extension_types:
        class_name = str(extension_type.class_name)
        if class_name.startswith("_"):
            continue
        if not _IDENTIFIER.fullmatch(class_name):
            _reject(
                extension_type,
                "AHPY_NOX005",
                "extension type names must be ASCII identifiers",
            )
        type_methods = extension_type.body.stats
        public_fields = [
            field for field in extension_type.entry.type.scope.var_entries
            if field.visibility in ("public", "readonly")
        ]
        properties = [
            member for member in type_methods
            if type(member) is Nodes.PropertyNode
        ]
        if public_fields or properties:
            _reject(
                properties[0] if properties else public_fields[0],
                "AHPY_NOX007",
                "manifest v1 cannot represent extension properties or public fields",
            )
        constructors = [
            method for method in type_methods
            if type(method) is Nodes.DefNode
            and method.name in ("__cinit__", "__init__")
        ]
        if len(constructors) > 1:
            _reject(
                constructors[1],
                "AHPY_NOX007",
                "a type cannot export both __cinit__ and __init__ in manifest v1",
            )
        if constructors:
            exports.append(_callable_export(
                constructors[0], "constructor", class_name, capabilities,
                skip_receiver=True))
        else:
            exports.append({
                "kind": "constructor",
                "name": class_name,
                "parameters": [],
                "result": {"kind": "opaque-object", "ownership": "owned"},
            })
        for method in type_methods:
            if type(method) is not Nodes.DefNode:
                continue
            method_name = method.name
            if method_name.startswith("_"):
                continue
            exports.append(_callable_export(
                method,
                "method",
                "%s.%s" % (class_name, method_name),
                capabilities,
                skip_receiver=True,
            ))
    export_keys = [(item["kind"], item["name"]) for item in exports]
    if len(export_keys) != len(set(export_keys)):
        _reject(module_node, "AHPY_NOX005", "duplicate export identity")
    exports.sort(key=lambda item: (item["kind"], item["name"]))
    module_name = str(module_node.full_module_name)
    return {
        "protocol": PROTOCOL,
        "module": {
            "name": module_name,
            "init_symbol": "HPyInit_%s" % module_name.rsplit(".", 1)[-1],
        },
        "required_capabilities": sorted(capabilities),
        "exports": exports,
    }
