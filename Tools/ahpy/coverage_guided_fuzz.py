#!/usr/bin/env python3
"""Deterministically select and execute aHPy mutations by compiler coverage."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import trace


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Cython.Compiler import Main, Options
from Cython.Compiler.RuntimeAPI import HPY_UNIVERSAL_BACKEND

from artifact_utils import require_universal_binary
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


MODULE_NAME = "guided_surface"
DEFAULT_SEED = 0xC0A4F9
DEFAULT_CANDIDATES = 64

GUIDED_FILES = tuple(
    str((ROOT / path).resolve())
    for path in (
        "Cython/Compiler/HPyModuleWriter.py",
        "Cython/Compiler/HandleModel.py",
        "Cython/Compiler/RuntimeAPI.py",
        "Cython/Compiler/Nodes.py",
        "Cython/Compiler/ExprNodes.py",
    )
)


def generate_candidate(index, rng):
    name = "guided_%03d" % index
    helper = "guided_helper_%03d" % index
    state = "guided_state_%03d" % index
    module_alias = "guided_math_%03d" % index
    values = [rng.randint(1, 12) for _ in range(6)]
    family = index % 16

    if family == 0:
        family_name = "arithmetic"
        source = (
            "def %s():\n"
            "    left = %d\n"
            "    right = %d\n"
            "    return ((left + right) * (right - 1), left < right, left and right)\n"
        ) % (name, values[0], values[1])
    elif family == 1:
        family_name = "containers"
        source = (
            "def %s():\n"
            "    seed = [%d, %d]\n"
            "    mapping = {'seed': seed, 'pair': (seed[0], %d)}\n"
            "    return [mapping, seed[-1], (seed,)]\n"
        ) % (name, values[0], values[1], values[2])
    elif family == 2:
        family_name = "expanded-call"
        source = (
            "def %s(first, second=%d):\n"
            "    return [first, second]\n\n"
            "def %s():\n"
            "    positional = (%d,)\n"
            "    keywords = {'second': %d}\n"
            "    return %s(*positional, **keywords)\n"
        ) % (helper, values[0], name, values[1], values[2], helper)
    elif family == 3:
        family_name = "module-global"
        source = (
            "%s = [%d]\n\n"
            "def %s():\n"
            "    global %s\n"
            "    %s += [%d]\n"
            "    return %s\n"
        ) % (state, values[0], name, state, state, values[1], state)
    elif family == 4:
        family_name = "handled-call-error"
        source = (
            "def %s():\n"
            "    try:\n"
            "        return int('guided-%d')\n"
            "    except (ValueError, TypeError):\n"
            "        return ('caught', %d)\n"
        ) % (name, index, values[0])
    elif family == 5:
        family_name = "while-branch"
        source = (
            "def %s():\n"
            "    counter = %d\n"
            "    result = []\n"
            "    while counter:\n"
            "        if counter %% 2:\n"
            "            result += [counter]\n"
            "        counter -= 1\n"
            "    return result\n"
        ) % (name, 2 + values[0] % 5)
    elif family == 6:
        family_name = "for-control"
        source = (
            "def %s():\n"
            "    result = 0\n"
            "    for item in [%d, %d, %d]:\n"
            "        if item == %d:\n"
            "            continue\n"
            "        result += item\n"
            "    else:\n"
            "        result += %d\n"
            "    return result\n"
        ) % (name, values[0], values[1], values[2], values[1], values[3])
    elif family == 7:
        family_name = "slices"
        source = (
            "def %s():\n"
            "    values = [%d, %d, %d, %d]\n"
            "    values[1:3] = [%d, %d]\n"
            "    return values[::2]\n"
        ) % (name, *values[:6])
    elif family == 8:
        family_name = "comparisons"
        source = (
            "def %s():\n"
            "    left = [%d]\n"
            "    right = [%d]\n"
            "    return [left == right, left is right, %d in right, not left, left or right]\n"
        ) % (name, values[0], values[0], values[0])
    elif family == 9:
        family_name = "import-attribute-call"
        source = (
            "import math as %s\n\n"
            "def %s():\n"
            "    return %s.sqrt(%d)\n"
        ) % (module_alias, name, module_alias, values[0] * values[0])
    elif family == 10:
        family_name = "explicit-raise-handler"
        source = (
            "def %s():\n"
            "    try:\n"
            "        raise ValueError('guided')\n"
            "    except ValueError:\n"
            "        return [%d, %d]\n"
        ) % (name, values[0], values[1])
    elif family == 11:
        family_name = "item-mutation"
        source = (
            "def %s():\n"
            "    mapping = {'first': %d}\n"
            "    mapping['second'] = %d\n"
            "    del mapping['first']\n"
            "    return mapping['second']\n"
        ) % (name, values[0], values[1])
    elif family == 12:
        family_name = "starred-containers"
        source = (
            "def %s():\n"
            "    middle = [%d, %d]\n"
            "    return [0, *middle, %d], (0, *middle, %d)\n"
        ) % (name, values[0], values[1], values[2], values[3])
    elif family == 13:
        family_name = "inplace-operators"
        source = (
            "def %s():\n"
            "    value = %d\n"
            "    value += %d\n"
            "    value *= %d\n"
            "    value ^= %d\n"
            "    return value\n"
        ) % (name, values[0], values[1], 1 + values[2] % 3, values[3])
    elif family == 14:
        family_name = "keyword-call"
        source = (
            "def %s(first, second):\n"
            "    return first - second\n\n"
            "def %s():\n"
            "    return %s(second=%d, first=%d)\n"
        ) % (helper, name, helper, values[0], values[1])
    else:
        family_name = "conditional-expression"
        source = (
            "def %s():\n"
            "    return [%d if [%d] else %d, b'guided\\x00bytes', 'Türkçe']\n"
        ) % (
            name, values[1], values[0], values[2],
        )
    return {
        "id": index,
        "name": name,
        "family": family_name,
        "source": source,
    }


def generate_candidates(seed=DEFAULT_SEED, candidate_count=DEFAULT_CANDIDATES):
    rng = random.Random(seed)
    return [generate_candidate(index, rng) for index in range(candidate_count)]


def greedy_select(candidate_hits):
    selected = []
    covered = set()
    families = set()
    for candidate, hits in candidate_hits:
        new_hits = set(hits) - covered
        new_family = candidate["family"] not in families
        if new_hits or new_family:
            selected.append({
                **candidate,
                "new_coverage_lines": len(new_hits),
            })
            covered.update(hits)
            families.add(candidate["family"])
    return selected, covered


def _guided_hits(counts):
    return {
        (str(Path(filename).resolve()), line)
        for (filename, line), count in counts.items()
        if count and str(Path(filename).resolve()) in GUIDED_FILES
    }


def _compile_with_trace(tracer, source, output):
    diagnostics = io.StringIO()
    with redirect_stderr(diagnostics):
        result = tracer.runfunc(
            Main.compile,
            str(source),
            Options.CompilationOptions(
                output_file=str(output),
                language_level=3,
                runtime_backend=HPY_UNIVERSAL_BACKEND,
            ),
        )
    if result.num_errors:
        raise AssertionError(
            "guided candidate failed compilation:\n%s\n%s" % (
                source.read_text(encoding="utf8"), diagnostics.getvalue()))
    return _guided_hits(tracer.results().counts)


def select_candidates_by_coverage(candidates, temp):
    warmup = temp / "guided_warmup.pyx"
    warmup.write_text("def warmup():\n    return None\n", encoding="utf8")
    Main.compile(
        str(warmup),
        Options.CompilationOptions(
            output_file=str(temp / "guided_warmup.c"),
            language_level=3,
            runtime_backend=HPY_UNIVERSAL_BACKEND,
        ),
    )

    tracer = trace.Trace(count=True, trace=False)
    prior_hits = set()
    candidate_hits = []
    for candidate in candidates:
        source = temp / ("candidate_%03d.pyx" % candidate["id"])
        output = temp / ("candidate_%03d.c" % candidate["id"])
        source.write_text(candidate["source"], encoding="utf8")
        cumulative_hits = _compile_with_trace(tracer, source, output)
        hits = cumulative_hits - prior_hits
        prior_hits = cumulative_hits
        candidate_hits.append((candidate, hits))
    return greedy_select(candidate_hits)


def _runtime_program(source, functions, debug):
    prefix = ""
    suffix = ""
    if debug:
        prefix = (
            "from hpy.debug import LeakDetector\n"
            "detector = LeakDetector()\n"
            "detector.start()\n"
        )
        suffix = "detector.stop()\n"
    return (
        "from pathlib import Path\n"
        "import guided_surface\n" +
        prefix +
        "namespace = {}\n"
        "exec(Path(%r).read_text(encoding='utf8'), namespace)\n" % str(source) +
        "for name in %r:\n" % functions +
        "    actual = getattr(guided_surface, name)()\n"
        "    expected = namespace[name]()\n"
        "    assert type(actual) is type(expected), (name, actual, expected)\n"
        "    assert actual == expected, (name, actual, expected)\n" +
        suffix
    )


def build_and_run(python, seed=DEFAULT_SEED, candidate_count=DEFAULT_CANDIDATES):
    candidates = generate_candidates(seed, candidate_count)
    with TemporaryDirectory(prefix="ahpy-guided-fuzz-") as temp_dir:
        temp = Path(temp_dir)
        selected, covered = select_candidates_by_coverage(candidates, temp)
        if not selected:
            raise AssertionError("coverage guidance selected no candidates")
        source = temp / (MODULE_NAME + ".pyx")
        source.write_text(
            "\n\n".join(candidate["source"] for candidate in selected),
            encoding="utf8",
        )
        functions = [candidate["name"] for candidate in selected]
        generated = temp / (MODULE_NAME + ".c")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        run([
            python, "-m", "cython",
            "--runtime-backend=hpy-universal", "-3",
            "-o", str(generated), str(source),
        ], cwd=ROOT, env=environment)
        verify_source_boundary(
            generated,
            required=("#include <hpy.h>", "HPy_MODINIT", "HPy_mod_exec"),
        )

        setup = temp / "setup.py"
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "from ahpy_hpy_compat import install_hpy_universal_loader_compat\n"
            "install_hpy_universal_loader_compat()\n"
            "setup(name='ahpy-guided-fuzz', version='0.0.0', "
            "packages=[], py_modules=[], "
            "hpy_ext_modules=[Extension('guided_surface', "
            "['guided_surface.c'])])\n",
            encoding="utf8",
        )
        build_root = temp / "build"
        run([
            python, str(setup), "--hpy-abi=universal", "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        binary = require_universal_binary(build_root, MODULE_NAME)
        verify_binary_boundary(binary)

        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(binary.parent)
        run([
            python, "-c", _runtime_program(source, functions, False),
        ], cwd=temp, env=runtime_environment)
        debug_environment = runtime_environment.copy()
        debug_environment["HPY"] = "debug"
        run([
            python, "-c", _runtime_program(source, functions, True),
        ], cwd=temp, env=debug_environment)
    return selected, covered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--seed", type=lambda value: int(value, 0), default=DEFAULT_SEED)
    parser.add_argument(
        "--candidates", type=int, default=DEFAULT_CANDIDATES)
    args = parser.parse_args()
    if args.candidates <= 0:
        parser.error("--candidates must be positive")
    python_path = Path(args.python)
    if python_path.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    selected, covered = build_and_run(python, args.seed, args.candidates)
    print(
        "Generated Universal HPy module: selected %d/%d guided mutations "
        "across %d families and %d compiler lines" % (
            len(selected), args.candidates,
            len({candidate["family"] for candidate in selected}),
            len(covered),
        )
    )


if __name__ == "__main__":
    main()
