#!/usr/bin/env python3
"""Compile-scan Cython sources and emit actionable aHPy migration reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tokenize
import io


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+):(?P<column>\d+): "
    r"aHPy bootstrap backend: (?P<message>.+)$",
    re.MULTILINE,
)

STATIC_RULES = (
    (
        "direct-cpython-cimport",
        re.compile(r"(?m)^\s*(?:from\s+cpython(?:\.|\s)|cimport\s+cpython(?:\.|\s))"),
        "direct cpython.* dependency detected by source scan",
        "Replace direct cpython.* declarations with Python-independent C APIs "
        "or an explicitly designed public HPy boundary.",
    ),
    (
        "python-header",
        re.compile(r"(?m)^\s*cdef\s+extern\s+from\s+[\"']Python\.h[\"']"),
        "Python.h dependency detected by source scan",
        "Remove Python.h from the Universal translation-unit boundary and port "
        "the dependency to public HPy or a Python-independent C shim.",
    ),
    (
        "direct-pyobject-pointer",
        re.compile(r"\b(?:PyObject|cpy_PyObject)\s*\*"),
        "direct PyObject pointer detected by source scan",
        "Remove PyObject pointer storage from the Universal boundary; keep the "
        "value as an owned/borrowed HPy handle or isolate it in an explicitly "
        "non-Universal component.",
    ),
    (
        "legacy-hpy-conversion",
        re.compile(r"\b(?:HPy_FromPyObject|HPy_AsPyObject)\s*\("),
        "legacy HPy/PyObject conversion detected by source scan",
        "Remove the legacy conversion and carry the value through public HPy "
        "handles for its complete lifetime; Universal mode cannot expose a "
        "PyObject pointer escape hatch.",
    ),
)

ACTION_RULES = (
    (
        "parallel-worker-contract",
        (
            "public HPy worker-thread attach", "prange/parallel requires",
            "CPython PyThreadState/exception triples",
        ),
        "Keep parallel work outside the Universal subset for now, or isolate "
        "a native-only loop according to ADR 0011 until the neutral parallel "
        "plan and selected HPy worker contract are implemented.",
    ),
    (
        "nogil-transition",
        (
            "inside with nogil", "with nogil blocks",
            "with nogil may call", "HPy execution-state transition",
        ),
        "Keep the native interval argumentless, noexcept, and independent of "
        "Python/HPy state as documented by ADR 0010, or move the operation "
        "outside with nogil until its transition subgate is implemented.",
    ),
    (
        "buffer-consumer-api",
        ("buffer acquire/release consumer API", "CPython Py_buffer utilities"),
        "Keep the boundary as an ordinary Python object or a Python-independent "
        "C pointer/length API until the selected HPy version exposes public "
        "buffer acquisition and release operations.",
    ),
    (
        "set-construction",
        ("set construction", "SetType context constant"),
        "Use a supported list/tuple/dict representation for now, or wait for a "
        "selected HPy API with public set construction and insertion.",
    ),
    (
        "generic-iteration",
        ("generic iterator API", "GetIter", "IterNext",
         "generator expressions cannot drive for-loops"),
        "Use a sequence-index iterable (list/tuple/str or any object that "
        "supports HPy_Length/HPy_GetItem_i), or defer generator/iterator-"
        "protocol loops until the selected HPy version exposes GetIter/IterNext.",
    ),
    (
        "exception-handlers",
        (
            "TryExceptStatNode", "ReraiseStatNode", "handler-state",
            "try/except", "exception handler", "except targets",
            "active-handler state",
        ),
        "Refactor the handler boundary outside the compiled subset for now; "
        "public HPy 0.9 exception-state support is not yet sufficient here.",
    ),
    (
        "control-flow-lifetime",
        ("continuing loop", "continuing conditional branch", "not initialized"),
        "Restructure the branch/loop so every continuing path has the same "
        "initialized locals and move termination to a supported outer boundary.",
    ),
    (
        "unsupported-source-node",
        ("is not implemented",),
        "Consult docs/ahpy/support-matrix.md and isolate this construct behind "
        "a supported Python or HPy boundary until its feature gate is complete.",
    ),
)


def migration_action(message):
    for action_id, markers, action in ACTION_RULES:
        if any(marker in message for marker in markers):
            return {"id": action_id, "text": action}
    return {
        "id": "unsupported-universal-construct",
        "text": "Consult docs/ahpy/support-matrix.md, preserve the Universal "
        "diagnostic, and avoid CPython/Hybrid fallback.",
    }


def parse_diagnostics(output):
    diagnostics = []
    for match in DIAGNOSTIC_RE.finditer(output):
        message = match.group("message")
        diagnostics.append({
            "path": match.group("path"),
            "line": int(match.group("line")),
            "column": int(match.group("column")),
            "message": message,
            "action": migration_action(message),
        })
    return diagnostics


def _mask_comments_and_strings(source_text):
    """Preserve offsets/newlines while hiding lexical comments and strings."""
    masked = list(source_text)
    line_offsets = [0]
    for match in re.finditer("\n", source_text):
        line_offsets.append(match.end())

    def offset(position):
        line, column = position
        return line_offsets[line - 1] + column

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source_text).readline)
        for token in tokens:
            if token.type not in (tokenize.COMMENT, tokenize.STRING):
                continue
            start = offset(token.start)
            end = offset(token.end)
            for index in range(start, end):
                if masked[index] not in ("\n", "\r"):
                    masked[index] = " "
    except (IndentationError, tokenize.TokenError):
        # The compiler remains authoritative for malformed input.  Findings
        # already masked before a tokenizer failure are still safe to use.
        pass
    return "".join(masked)


def static_findings(path, source_text):
    findings = []
    code_mask = _mask_comments_and_strings(source_text)
    for action_id, pattern, message, action in STATIC_RULES:
        for match in pattern.finditer(source_text):
            if not code_mask[match.start():match.end()].strip():
                continue
            line = source_text.count("\n", 0, match.start()) + 1
            column = match.start() - source_text.rfind("\n", 0, match.start())
            findings.append({
                "path": str(path),
                "line": line,
                "column": column,
                "message": message,
                "action": {"id": action_id, "text": action},
            })
    return findings


def scan_source(python, source, temp, root=ROOT):
    source = Path(source)
    findings = static_findings(source, source.read_text(encoding="utf8"))
    source_id = hashlib.sha256(
        os.path.abspath(source).encode("utf8")).hexdigest()[:12]
    output = temp / (source.stem + "-" + source_id + ".c")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root)
    result = subprocess.run([
        python,
        "-m", "cython",
        "--runtime-backend=hpy-universal",
        "-3",
        "-o", str(output),
        str(source),
    ], cwd=root, env=environment, capture_output=True, text=True)
    compiler_output = result.stdout + result.stderr
    diagnostics = parse_diagnostics(compiler_output)
    diagnostics.extend(findings)
    status = "compatible" if result.returncode == 0 and not findings else "rejected"
    if result.returncode != 0 and not diagnostics:
        status = "compiler-error"
        diagnostics.append({
            "path": str(source),
            "line": None,
            "column": None,
            "message": compiler_output.strip() or "compiler exited without diagnostics",
            "action": {
                "id": "compiler-error",
                "text": "Report this output as a compiler bug; do not treat a "
                "traceback or internal error as an expected compatibility rejection.",
            },
        })
    if status == "compatible":
        generated = output.read_text(encoding="utf8")
        if "#include <hpy.h>" not in generated or "#include <Python.h>" in generated:
            status = "compiler-error"
            diagnostics.append({
                "path": str(source),
                "line": None,
                "column": None,
                "message": "generated source violated the Universal header boundary",
                "action": {
                    "id": "report-backend-boundary-bug",
                    "text": "Preserve the generated file and report aHPy's Universal "
                    "boundary violation.",
                },
            })
    return {
        "path": str(source),
        "status": status,
        "diagnostics": diagnostics,
    }


def scan_sources(python, sources, root=ROOT):
    with TemporaryDirectory(prefix="ahpy-compatibility-scan-") as temp_dir:
        temp = Path(temp_dir)
        reports = [scan_source(python, source, temp, root=root) for source in sources]
    counts = {
        status: sum(report["status"] == status for report in reports)
        for status in ("compatible", "rejected", "compiler-error")
    }
    return {
        "schema_version": 1,
        "backend": "hpy-universal",
        "sources": reports,
        "summary": {"total": len(reports), **counts},
    }


def render_text(report):
    lines = [
        "aHPy compatibility scan: {compatible} compatible, {rejected} rejected, "
        "{compiler-error} compiler errors".format(**report["summary"])
    ]
    for source in report["sources"]:
        lines.append("[%s] %s" % (source["status"].upper(), source["path"]))
        for diagnostic in source["diagnostics"]:
            location = diagnostic["path"]
            if diagnostic["line"] is not None:
                location += ":%d:%d" % (
                    diagnostic["line"], diagnostic["column"])
            lines.append("  %s: %s" % (location, diagnostic["message"]))
            lines.append(
                "  action %s: %s" %
                (diagnostic["action"]["id"], diagnostic["action"]["text"]))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--allow-rejected", action="store_true",
        help="return success when sources are rejected but no compiler error occurs",
    )
    args = parser.parse_args()
    selected = Path(args.python)
    if selected.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    missing = [source for source in args.sources if not Path(source).is_file()]
    if missing:
        parser.error("source file not found: %s" % ", ".join(missing))
    report = scan_sources(python, args.sources, root=args.root)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    if report["summary"]["compiler-error"]:
        return 2
    if report["summary"]["rejected"] and not args.allow_rejected:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
