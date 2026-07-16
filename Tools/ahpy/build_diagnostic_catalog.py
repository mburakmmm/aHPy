#!/usr/bin/env python3
"""Build the machine-readable catalog of strict aHPy diagnostics."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

from scan_compatibility import migration_action


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "Cython/Compiler/ModuleNode.py",
    "Cython/Compiler/Nodes.py",
    "Cython/Compiler/ExprNodes.py",
    "Cython/Compiler/HPyModuleWriter.py",
)


def _message_expression(node, source):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _message_expression(node.left, source)
        right = _message_expression(node.right, source)
        return left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _message_expression(node.left, source)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append("{expression}")
        return "".join(parts)
    return ast.get_source_segment(source, node) or ast.unparse(node)


def catalog_source(root, relative_path):
    path = Path(root) / relative_path
    source = path.read_text(encoding="utf8")
    tree = ast.parse(source, filename=str(path))
    entries = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function = node.func
        is_unsupported = (
            isinstance(function, ast.Attribute)
            and function.attr == "unsupported"
        )
        is_ahpy_error = (
            isinstance(function, ast.Name)
            and function.id == "error"
            and len(node.args) >= 2
            and "aHPy bootstrap backend:" in _message_expression(
                node.args[-1], source)
        )
        if not (is_unsupported or is_ahpy_error):
            continue
        message_node = node.args[-1]
        message = _message_expression(message_node, source)
        entries.append({
            "id": "%s:%d" % (relative_path, node.lineno),
            "source": relative_path,
            "line": node.lineno,
            "message_template": message,
            "migration_action": migration_action(message),
        })
    return entries


def build_catalog(root=ROOT):
    entries = []
    for relative_path in SOURCES:
        entries.extend(catalog_source(root, relative_path))
    entries.sort(key=lambda entry: (entry["source"], entry["line"]))
    return {
        "schema_version": 1,
        "backend_prefix": "aHPy bootstrap backend:",
        "source_files": list(SOURCES),
        "diagnostic_count": len(entries),
        "diagnostics": entries,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.check and args.output:
        parser.error("--check and --output are mutually exclusive")
    catalog = build_catalog(args.root)
    rendered = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
    if args.check:
        expected = args.check.read_text(encoding="utf8")
        if rendered != expected:
            print(
                "diagnostic catalog is stale; regenerate with "
                "Tools/ahpy/build_diagnostic_catalog.py",
                file=sys.stderr,
            )
            return 1
    elif args.output:
        args.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
