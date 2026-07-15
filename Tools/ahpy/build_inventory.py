#!/usr/bin/env python3
"""Build a deterministic inventory of Cython's Python runtime dependencies.

The inventory is deliberately conservative. Symbols that are not in a reviewed
mapping are classified as unsupported until a focused design review proves a
Universal HPy implementation. This prevents an unknown CPython dependency from
being mistaken for a direct HPy mapping.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess


API_CALL_RE = re.compile(r"\b((?:_?Py|PY)[A-Za-z_][A-Za-z0-9_]*)\s*\(")
TYPE_RE = re.compile(
    r"\b(PyObject|PyTypeObject|PyThreadState|PyFrameObject|PyCodeObject|"
    r"Py_buffer|Py_ssize_t)\b"
)
TAG_RE = re.compile(r"^\s*#\s*tag\s*:\s*(.+?)\s*$", re.MULTILINE)

SCANNED_SUFFIXES = {".py", ".pyx", ".pxd", ".pxi", ".c", ".h"}

ABSTRACTION_MARKERS = (
    "CYTHON_COMPILING_IN_LIMITED_API",
    "CYTHON_AVOID_BORROWED_REFS",
    "CYTHON_OPAQUE_OBJECTS",
    "CYTHON_USE_MODULE_STATE",
    "CYTHON_USE_TYPE_SPECS",
    "CYTHON_COMPILING_IN_CPYTHON_FREETHREADING",
)

DIRECT_PREFIXES = (
    "PyBool_",
    "PyBytes_",
    "PyComplex_",
    "PyDict_",
    "PyErr_",
    "PyFloat_",
    "PyImport_",
    "PyIter_",
    "PyList_",
    "PyLong_",
    "PyNumber_",
    "PySequence_",
    "PySet_",
    "PySlice_",
    "PyTuple_",
    "PyType_",
    "PyUnicode_",
)

STRUCTURAL_PREFIXES = (
    "PyArg_",
    "PyBuffer_",
    "PyEval_",
    "PyGILState_",
    "PyList_SET",
    "PyModule_",
    "PyObject_Call",
    "PyObject_GC",
    "PyThread_",
    "PyTuple_SET",
    "PyType_From",
)

STRUCTURAL_SYMBOLS = {
    "Py_CLEAR",
    "Py_DECREF",
    "Py_INCREF",
    "Py_NewRef",
    "Py_SETREF",
    "Py_XDECREF",
    "Py_XINCREF",
    "Py_XNewRef",
}

LEGACY_PREFIXES = ("_Py", "__Py", "PY_VECTORCALL_ARGUMENTS_OFFSET")


def classify(symbol: str) -> tuple[str, str, str]:
    """Return category, owner phase, and conservative rationale."""
    if symbol.startswith(LEGACY_PREFIXES):
        return (
            "legacy_only",
            "M3-universal-enforcement",
            "Private/implementation-specific CPython surface.",
        )
    if symbol in STRUCTURAL_SYMBOLS or symbol.startswith(STRUCTURAL_PREFIXES):
        return (
            "structurally_different",
            "M1-M2-runtime-and-ownership",
            "HPy requires a different signature, builder, storage, or ownership shape.",
        )
    if symbol.startswith(DIRECT_PREFIXES):
        return (
            "directly_mappable",
            "M3-core-runtime",
            "A public HPy operation family exists; ownership still requires review.",
        )
    if symbol.startswith(("PyMem_", "PyObject_Malloc", "PyObject_Free")):
        return (
            "backend_independent_replacement",
            "M1-runtime-seam",
            "Universal code must use a validated runtime-independent allocation path.",
        )
    return (
        "unsupported_by_validated_hpy",
        "M6-capability-review",
        "No reviewed public HPy mapping is recorded; reject until validated.",
    )


def iter_source_files(root: Path):
    for relative_root in (Path("Cython/Compiler"), Path("Cython/Utility")):
        directory = root / relative_root
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in SCANNED_SUFFIXES:
                yield path


def git_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def build_inventory(root: Path) -> dict:
    symbol_counts = Counter()
    symbol_files = defaultdict(set)
    type_counts = Counter()
    type_files = defaultdict(set)
    python_header_files = set()
    marker_counts = Counter()
    marker_files = defaultdict(set)
    scanned_files = []

    for path in iter_source_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        scanned_files.append(relative)
        if "Python.h" in text:
            python_header_files.add(relative)
        for symbol in API_CALL_RE.findall(text):
            symbol_counts[symbol] += 1
            symbol_files[symbol].add(relative)
        for type_name in TYPE_RE.findall(text):
            type_counts[type_name] += 1
            type_files[type_name].add(relative)
        for marker in ABSTRACTION_MARKERS:
            count = text.count(marker)
            if count:
                marker_counts[marker] += count
                marker_files[marker].add(relative)

    api_symbols = []
    category_counts = Counter()
    for symbol in sorted(symbol_counts):
        category, owner, rationale = classify(symbol)
        category_counts[category] += 1
        api_symbols.append(
            {
                "symbol": symbol,
                "occurrences": symbol_counts[symbol],
                "files": sorted(symbol_files[symbol]),
                "category": category,
                "owner": owner,
                "classification_reviewed": False,
                "rationale": rationale,
            }
        )

    object_types = []
    for type_name in sorted(type_counts):
        object_types.append(
            {
                "type": type_name,
                "occurrences": type_counts[type_name],
                "files": sorted(type_files[type_name]),
            }
        )

    suite_counts = Counter()
    suffix_counts = Counter()
    tag_counts = Counter()
    tests_root = root / "tests"
    for path in sorted(tests_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(tests_root)
        suite_counts[relative.parts[0]] += 1
        suffix_counts[path.suffix or "<none>"] += 1
        if path.suffix in SCANNED_SUFFIXES or path.suffix == ".srctree":
            text = path.read_text(encoding="utf-8", errors="replace")
            for tag_line in TAG_RE.findall(text):
                for tag in re.split(r"[\s,]+", tag_line.strip()):
                    if tag:
                        tag_counts[tag] += 1

    return {
        "schema_version": 1,
        "cython_revision": git_revision(root),
        "classification_policy": (
            "Conservative heuristic baseline; every entry starts unreviewed and "
            "unknown symbols are unsupported until validated."
        ),
        "source_summary": {
            "files_scanned": len(scanned_files),
            "api_symbol_count": len(api_symbols),
            "api_call_occurrences": sum(symbol_counts.values()),
            "category_counts": dict(sorted(category_counts.items())),
            "python_header_files": sorted(python_header_files),
        },
        "api_symbols": api_symbols,
        "python_object_types": object_types,
        "existing_abstractions": [
            {
                "marker": marker,
                "occurrences": marker_counts[marker],
                "files": sorted(marker_files[marker]),
            }
            for marker in ABSTRACTION_MARKERS
        ],
        "test_summary": {
            "suite_file_counts": dict(sorted(suite_counts.items())),
            "suffix_counts": dict(sorted(suffix_counts.items())),
            "tag_counts": dict(sorted(tag_counts.items())),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    args = parser.parse_args()
    print(json.dumps(build_inventory(args.root.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
