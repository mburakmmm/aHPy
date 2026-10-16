#!/usr/bin/env python3
"""Run compiler-owned aHPy NOX export analysis and emit canonical JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Cython.Compiler import Main, Options  # noqa: E402
from Cython.Compiler.RuntimeAPI import HPY_UNIVERSAL_BACKEND  # noqa: E402


class NoxExportCommandError(RuntimeError):
    """Compiler export analysis failed without producing partial metadata."""


def canonical_analysis_bytes(analysis):
    return (json.dumps(
        analysis, ensure_ascii=False, sort_keys=True, separators=(",", ":")) +
        "\n").encode("utf8")


def analyze_source(source, module_name=None):
    source = Path(source).resolve()
    if not source.is_file():
        raise NoxExportCommandError("source does not exist: %s" % source)
    if module_name is None:
        module_name = source.stem
    with TemporaryDirectory(prefix="ahpy-nox-export-") as temp_dir:
        output = Path(temp_dir) / (source.stem + ".c")
        result = Main.compile(
            str(source),
            Options.CompilationOptions(
                output_file=str(output),
                language_level=3,
                runtime_backend=HPY_UNIVERSAL_BACKEND,
                nox_export_analysis=True,
            ),
            full_module_name=module_name,
        )
    if result.num_errors:
        raise NoxExportCommandError(
            "compiler rejected the NOX export surface with %d error(s)" %
            result.num_errors)
    if result.nox_export_analysis is None:
        raise NoxExportCommandError("compiler returned no NOX export analysis")
    return result.nox_export_analysis


def write_analysis(analysis, output, check=False):
    rendered = canonical_analysis_bytes(analysis)
    output = Path(output)
    if check:
        try:
            existing = output.read_bytes()
        except OSError as exc:
            raise NoxExportCommandError(
                "cannot read export analysis %s: %s" % (output, exc)) from exc
        if existing != rendered:
            raise NoxExportCommandError(
                "%s is stale or non-canonical" % output)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
    return rendered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--module-name")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(argv)
    if options.check and options.output is None:
        parser.error("--check requires --output")
    try:
        analysis = analyze_source(options.source, options.module_name)
        if options.output is None:
            sys.stdout.buffer.write(canonical_analysis_bytes(analysis))
        else:
            write_analysis(analysis, options.output, check=options.check)
    except NoxExportCommandError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
