#!/usr/bin/env python3
"""Report deterministic Python line coverage for the focused aHPy surface."""

from __future__ import annotations

import argparse
import dis
import io
import json
from pathlib import Path
import sys
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
    return lines


def _load_family_suite(loader, modules):
    return loader.loadTestsFromNames(modules)


def _load_quality_suite(loader, root=ROOT):
    return loader.discover(
        str(root / "Tools" / "ahpy"),
        pattern="test_*.py",
        top_level_dir=str(root / "Tools" / "ahpy"),
    )


def run_traced_tests(root=ROOT, stream=None):
    loader = unittest.defaultTestLoader
    tracer = trace.Trace(count=True, trace=False)
    families = []
    success = True
    family_loaders = list(FAMILY_MODULES) + [("quality_tools", None)]
    for family_name, modules in family_loaders:
        suite = (
            _load_quality_suite(loader, root)
            if modules is None else _load_family_suite(loader, modules)
        )
        test_count = suite.countTestCases()
        family_stream = stream if stream is not None else io.StringIO()
        runner = unittest.TextTestRunner(
            stream=family_stream, verbosity=0, buffer=True)
        result = tracer.runfunc(runner.run, suite)
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
            file_report = {
                "path": filename,
                "executable_lines": len(executable),
                "covered_lines": len(covered),
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
        "schema_version": 1,
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
