#!/usr/bin/env python3
"""Report deterministic Python line coverage for the focused aHPy surface."""

from __future__ import annotations

import argparse
import ast
import dis
import importlib.abc
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import trace
from types import CodeType
import unittest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKEND_FILES = (
    "Cython/Compiler/HPyModuleWriter.py",
    "Cython/Compiler/HandleModel.py",
    "Cython/Compiler/RuntimeAPI.py",
)
FRONTEND_FILES = (
    "Cython/Compiler/Buffer.py",
    "Cython/Compiler/CmdLine.py",
    "Cython/Compiler/Code.py",
    "Cython/Compiler/ExprNodes.py",
    "Cython/Compiler/Main.py",
    "Cython/Compiler/ModuleNode.py",
    "Cython/Compiler/Nodes.py",
    "Cython/Compiler/Options.py",
    "Cython/Compiler/Pipeline.py",
    "Cython/Compiler/PyrexTypes.py",
    "Cython/Compiler/TypeSlots.py",
    "Cython/Compiler/UtilNodes.py",
)

FAMILY_MODULES = (
    ("ownership_model", ("Cython.Compiler.Tests.TestHandleModel",)),
    ("runtime_api", ("Cython.Compiler.Tests.TestRuntimeAPI",)),
    ("universal_emitter", ("Cython.Compiler.Tests.TestHPyModuleWriter",)),
    ("compiler_seams", (
        "Cython.Compiler.Tests.TestCmdLine",
        "Cython.Compiler.Tests.TestCode",
    )),
)

PACKAGING_FILES = (
    "ahpy_build_backend.py",
    "ahpy_build_config.py",
    "ahpy_hpy_compat.py",
    "ahpy_version.py",
)


def utility_files(root=ROOT):
    tool_files = tuple(
        path.relative_to(root).as_posix()
        for path in sorted((root / "Tools" / "ahpy").glob("*.py"))
        if not path.name.startswith("test_")
    )
    packaging_files = tuple(
        filename for filename in PACKAGING_FILES
        if (root / filename).is_file()
    )
    return tool_files + packaging_files


def coverage_areas(root=ROOT):
    return {
        "backend": BACKEND_FILES,
        "frontend_seam": FRONTEND_FILES,
        "quality_tools": utility_files(root),
    }


def measured_source_modules(root=ROOT):
    modules = {}
    for filenames in coverage_areas(root).values():
        for filename in filenames:
            path = root / filename
            source_path = Path(filename)
            if source_path.parts[:2] == ("Cython", "Compiler"):
                modules[".".join(source_path.with_suffix("").parts)] = path
            elif source_path.parts[:2] == ("Tools", "ahpy"):
                modules[source_path.stem] = path
                modules["Tools.ahpy.%s" % source_path.stem] = path
            else:
                modules[source_path.stem] = path
    return modules


class _MeasuredSourceFinder(importlib.abc.MetaPathFinder):
    """Prefer measured .py files over stale in-tree extension artifacts."""

    def __init__(self, root=ROOT):
        self.modules = measured_source_modules(root)

    def find_spec(self, fullname, path=None, target=None):
        source_path = self.modules.get(fullname)
        if source_path is None:
            return None
        return importlib.util.spec_from_file_location(fullname, source_path)


def executable_lines(path):
    source = path.read_text(encoding="utf8")
    code = compile(source, str(path), "exec")
    lines = set()
    pending = [code]
    while pending:
        current = pending.pop()
        lines.update(
            line for _, line in dis.findlinestarts(current)
            if line is not None and line > 0)
        pending.extend(
            value for value in current.co_consts
            if isinstance(value, CodeType)
        )
    return (
        lines
        - excluded_stub_lines(source, str(path))
        - excluded_bootstrap_lines(source, str(path))
    )


def excluded_stub_lines(source, filename="<coverage-source>"):
    """Exclude ellipsis-only interface stubs that have no runtime behavior."""
    tree = ast.parse(source, filename=filename)
    excluded = set()
    function_nodes = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, function_nodes):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        if len(body) != 1:
            continue
        statement = body[0]
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value is Ellipsis
        ):
            excluded.update(range(
                node.lineno + 1,
                getattr(node, "end_lineno", statement.lineno) + 1,
            ))
    return excluded


def excluded_bootstrap_lines(source, filename="<coverage-source>"):
    """Exclude behavior-free CLI dispatch and repository import bootstraps.

    The called ``main()`` functions and repository imports remain measured;
    only top-level wiring that the in-process tracer cannot observe when
    subprocess entrypoint tests run is excluded.
    """
    tree = ast.parse(source, filename=filename)
    excluded = set()
    for node in tree.body:
        if not isinstance(node, ast.If) or node.orelse or len(node.body) != 1:
            continue
        statement = node.body[0]
        main_guard = (
            isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "__main__"
        )
        call = statement.value if isinstance(statement, ast.Expr) else None
        if isinstance(statement, ast.Raise):
            call = statement.exc
        repository_path_insert = (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "insert"
            and isinstance(call.func.value, ast.Attribute)
            and isinstance(call.func.value.value, ast.Name)
            and call.func.value.value.id == "sys"
            and call.func.value.attr == "path"
        )
        if (main_guard and isinstance(call, ast.Call)) or repository_path_insert:
            excluded.update(range(
                statement.lineno,
                getattr(statement, "end_lineno", statement.lineno) + 1,
            ))
    return excluded


def collapse_line_ranges(lines):
    """Return stable, compact ranges for a collection of source lines."""
    ranges = []
    for line in sorted(set(lines)):
        if not ranges or line > ranges[-1][1] + 1:
            ranges.append([line, line])
        else:
            ranges[-1][1] = line
    return [
        str(start) if start == end else "%d-%d" % (start, end)
        for start, end in ranges
    ]


def _load_family_suite(loader, modules):
    return loader.loadTestsFromNames(modules)


def _load_quality_suite(loader, root=ROOT):
    return loader.discover(
        str(root / "Tools" / "ahpy"),
        pattern="test_*.py",
        top_level_dir=str(root / "Tools" / "ahpy"),
    )


def _load_suite_under_trace(tracer, loader, modules, root=ROOT):
    previous_trace = sys.gettrace()
    try:
        if modules is None:
            return tracer.runfunc(_load_quality_suite, loader, root)
        return tracer.runfunc(_load_family_suite, loader, modules)
    finally:
        # trace.Trace.runfunc() unconditionally installs None when it returns.
        # Preserve an outer coverage tracer when this helper is itself tested
        # from inside the quality-tool coverage suite.
        sys.settrace(previous_trace)


def _run_suite_under_trace(tracer, runner, suite):
    """Trace test-created threads as part of the same coverage result."""
    previous_trace = sys.gettrace()
    get_thread_trace = getattr(threading, "gettrace", lambda: None)
    previous_thread_trace = get_thread_trace()
    thread_trace = getattr(tracer, "globaltrace", None)
    try:
        if thread_trace is not None:
            threading.settrace(thread_trace)
        return tracer.runfunc(runner.run, suite)
    finally:
        # Preserve an outer tracer when report_coverage tests itself from the
        # quality suite, just as suite discovery does above.
        sys.settrace(previous_trace)
        threading.settrace(previous_thread_trace)


def run_traced_tests(root=ROOT, stream=None):
    loader = unittest.defaultTestLoader
    tracer = trace.Trace(count=True, trace=False)
    families = []
    success = True
    family_loaders = list(FAMILY_MODULES) + [("quality_tools", None)]
    source_finder = _MeasuredSourceFinder(root)
    sys.meta_path.insert(0, source_finder)
    try:
        for family_name, modules in family_loaders:
            # Discovery imports the test modules and, transitively, much of the
            # measured implementation.  Keep that work inside the tracer so
            # import-time executable lines are not permanently reported
            # missing. Prefer the measured Python sources over stale in-tree
            # extension artifacts from another validation lane.
            suite = _load_suite_under_trace(tracer, loader, modules, root)
            test_count = suite.countTestCases()
            family_stream = stream if stream is not None else io.StringIO()
            runner = unittest.TextTestRunner(
                stream=family_stream, verbosity=0, buffer=True)
            result = _run_suite_under_trace(tracer, runner, suite)
            family_success = result.wasSuccessful()
            success = success and family_success
            families.append({
                "name": family_name,
                "tests": test_count,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                "passed": family_success,
            })
    finally:
        sys.meta_path.remove(source_finder)
    return success, families, tracer.results().counts


def build_report(counts, families, root=ROOT):
    normalized_counts = {}
    for (filename, line), count in counts.items():
        try:
            filename = str(Path(filename).resolve())
        except OSError:
            continue
        normalized_counts[(filename, line)] = count

    areas = []
    for area_name, filenames in coverage_areas(root).items():
        files = []
        area_executable = 0
        area_covered = 0
        for filename in filenames:
            path = root / filename
            executable = executable_lines(path)
            covered = {
                line for line in executable
                if normalized_counts.get((str(path.resolve()), line), 0) > 0
            }
            missing = executable - covered
            file_report = {
                "path": filename,
                "executable_lines": len(executable),
                "covered_lines": len(covered),
                "missing_lines": sorted(missing),
                "missing_ranges": collapse_line_ranges(missing),
                "percent": (
                    round(100.0 * len(covered) / len(executable), 2)
                    if executable else 100.0
                ),
            }
            files.append(file_report)
            area_executable += len(executable)
            area_covered += len(covered)
        areas.append({
            "name": area_name,
            "executable_lines": area_executable,
            "covered_lines": area_covered,
            "percent": (
                round(100.0 * area_covered / area_executable, 2)
                if area_executable else 100.0
            ),
            "files": files,
        })
    return {
        "schema_version": 2,
        "areas": areas,
        "feature_families": families,
        "total_tests": sum(family["tests"] for family in families),
    }


def render_markdown(report):
    lines = [
        "# aHPy focused coverage",
        "",
        "| Area | Covered | Executable | Coverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for area in report["areas"]:
        lines.append(
            "| %s | %d | %d | %.2f%% |" % (
                area["name"], area["covered_lines"],
                area["executable_lines"], area["percent"],
            )
        )
    lines.extend((
        "",
        "| File | Covered | Executable | Coverage | Missing ranges |",
        "| --- | ---: | ---: | ---: | --- |",
    ))
    for area in report["areas"]:
        for file_report in area["files"]:
            missing = ", ".join(file_report.get("missing_ranges", ())) or "-"
            lines.append(
                "| `%s` | %d | %d | %.2f%% | %s |" % (
                    file_report["path"], file_report["covered_lines"],
                    file_report["executable_lines"], file_report["percent"],
                    missing,
                )
            )
    lines.extend((
        "",
        "| Feature family | Tests | Failures | Errors | Skipped | Passed |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ))
    for family in report["feature_families"]:
        lines.append(
            "| %s | %d | %d | %d | %d | %s |" % (
                family["name"], family["tests"], family["failures"],
                family["errors"], family["skipped"],
                "yes" if family["passed"] else "no",
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_thresholds(values):
    thresholds = {}
    for value in values:
        try:
            name, percent_text = value.split("=", 1)
            percent = float(percent_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "coverage thresholds must use AREA=PERCENT") from exc
        if not name or percent < 0.0 or percent > 100.0:
            raise argparse.ArgumentTypeError(
                "coverage thresholds must use AREA=PERCENT within 0..100")
        thresholds[name] = percent
    return thresholds


def check_thresholds(report, thresholds):
    actual = {area["name"]: area["percent"] for area in report["areas"]}
    failures = []
    for name, minimum in thresholds.items():
        if name not in actual:
            failures.append("unknown coverage area: %s" % name)
        elif actual[name] < minimum:
            failures.append(
                "%s coverage %.2f%% is below %.2f%%" % (
                    name, actual[name], minimum))
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--fail-under", action="append", default=[], metavar="AREA=PERCENT")
    args = parser.parse_args()
    try:
        thresholds = parse_thresholds(args.fail_under)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    success, families, counts = run_traced_tests(ROOT, stream=sys.stderr)
    report = build_report(counts, families, ROOT)
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown_text = render_markdown(report)
    if args.json_output:
        args.json_output.write_text(json_text, encoding="utf8")
    if args.markdown_output:
        args.markdown_output.write_text(markdown_text, encoding="utf8")
    if not args.json_output and not args.markdown_output:
        sys.stdout.write(markdown_text)

    failures = check_thresholds(report, thresholds)
    if not success:
        failures.append("one or more focused feature families failed")
    if failures:
        for failure in failures:
            print("coverage gate: %s" % failure, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
