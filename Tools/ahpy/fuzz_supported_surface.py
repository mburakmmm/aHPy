#!/usr/bin/env python3
"""Deterministically fuzz the executable supported aHPy source surface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from artifact_utils import require_universal_binary
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "fuzz_surface"
DEFAULT_SEED = 0xA4F9
DEFAULT_CASES = 48

REJECTED_CASES = (
    (
        "set-literal",
        "def rejected():\n    return {1, 2}\n",
        "neither public set construction/add operations",
    ),
    (
        "generic-iteration",
        "def rejected():\n"
        "    result = []\n"
        "    for value in (item for item in (1, 2)):\n"
        "        result += [value]\n"
        "    return result\n",
        "generator expressions cannot drive for-loops",
    ),
    (
        "except-as",
        "def rejected(value, /):\n"
        "    try:\n"
        "        raise ValueError(value)\n"
        "    except ValueError as exc:\n"
        "        return exc\n",
        "except targets require a public exception-state API",
    ),
    (
        "nonterminal-try",
        "def rejected(value, /):\n"
        "    try:\n"
        "        value = [value]\n"
        "    except ValueError:\n"
        "        value = None\n"
        "    return value\n",
        "requires a terminating return or raise",
    ),
    (
        "generator-yield",
        "def rejected():\n"
        "    yield 1\n",
        "HPy 0.9 lacks the public iterator-next API",
    ),
    (
        "nested-nested-def",
        "def rejected():\n"
        "    def inner():\n"
        "        def deepest():\n"
        "            return 1\n"
        "        return deepest\n"
        "    return inner\n",
        "nested nested def closures are not implemented",
    ),
    (
        "nested-def-default",
        "def rejected(base, /):\n"
        "    def inner(arg=base):\n"
        "        return arg\n"
        "    return inner\n",
        "default arguments on nested def are not implemented",
    ),
    (
        "nested-def-starargs",
        "def rejected():\n"
        "    def inner(*args):\n"
        "        return args\n"
        "    return inner\n",
        "star arguments on nested def are not implemented",
    ),
    (
        "nested-def-yield",
        "def rejected():\n"
        "    def inner():\n"
        "        yield 1\n"
        "    return inner\n",
        "generators and yield in nested def are not implemented",
    ),
    (
        "freelist-directive",
        "cimport cython\n"
        "@cython.freelist(4)\n"
        "cdef class RejectedFreelist:\n"
        "    pass\n",
        "pure Universal HPy @cython.freelist is not implemented",
    ),
    (
        "multiple-inheritance",
        "cdef class RejectedBaseA:\n"
        "    pass\n\n"
        "cdef class RejectedBaseB:\n"
        "    pass\n\n"
        "cdef class RejectedDerived(RejectedBaseA, RejectedBaseB):\n"
        "    pass\n",
        "Only one extension type base class allowed",
    ),
    (
        "metaclass",
        "class RejectedMetaclass(metaclass=type):\n"
        "    pass\n",
        "pure Universal HPy metaclass customization is not implemented",
    ),
    (
        "deallocator",
        "cdef class RejectedDealloc:\n"
        "    def __dealloc__(self):\n"
        "        pass\n",
        "pure Universal HPy __dealloc__ is not implemented",
    ),
    (
        "variable-size-layout",
        "cdef class RejectedVarSize:\n"
        "    cdef int items[4]\n",
        "pure Universal HPy variable-size extension layout is not implemented",
    ),
)


def generate_source(seed=DEFAULT_SEED, case_count=DEFAULT_CASES):
    rng = random.Random(seed)
    functions = []
    blocks = []
    for index in range(case_count):
        name = "fuzz_%03d" % index
        functions.append(name)
        values = [rng.randint(0, 20) for _ in range(5)]
        tag = "tag-%d-%d" % (index, rng.randint(0, 9999))
        template = index % 9
        if template == 0:
            body = (
                "    first = [%d, %d]\n"
                "    nested = {'values': first, 'pair': (%d, %r)}\n"
                "    return [nested, first[0], (%d,)]\n"
            ) % (values[0], values[1], values[2], tag, values[3])
        elif template == 1:
            body = (
                "    original = [%d]\n"
                "    if %d < %d:\n"
                "        selected = {'branch': 'left', 'value': original}\n"
                "    else:\n"
                "        selected = {'branch': 'right', 'value': (%d, %d)}\n"
                "    return [selected, original]\n"
            ) % (values[0], values[1], values[2], values[3], values[4])
        elif template == 2:
            count = 1 + values[0] % 5
            body = (
                "    counter = %d\n"
                "    values = []\n"
                "    while counter:\n"
                "        values += [counter]\n"
                "        counter -= 1\n"
                "    return values\n"
            ) % count
        elif template == 3:
            body = (
                "    total = 0\n"
                "    for item in [%d, %d, %d]:\n"
                "        total += item\n"
                "    result = [%d, total, %d, %d]\n"
                "    result[1:3] = [%d, %d]\n"
                "    return [result, item]\n"
            ) % tuple(values[:3] + values[:3] + values[:2])
        elif template == 4:
            body = (
                "    marker = %d\n"
                "    dir()\n"
                "    globals()\n"
                "    return [marker, marker]\n"
            ) % values[0]
        elif template == 5:
            target_index = values[4] % 4
            body = (
                "    values = [%d, %d, %d, %d]\n"
                "    target = values[%d]\n"
                "    return [values.count(target), target]\n"
            ) % (values[0], values[1], values[2], values[3], target_index)
        elif template == 6:
            body = (
                "    values = [%d, %d, %d]\n"
                "    return [type(values).__name__, values.count(%d)]\n"
            ) % (values[0], values[1], values[2], values[3] % 3)
        elif template == 7:
            body = (
                "    seed = %d\n"
                "    def inner():\n"
                "        return seed + %d\n"
                "    return inner()\n"
            ) % (values[1], values[0])
            blocks.append("def %s():\n%s" % (name, body))
            continue
        else:
            body = (
                "    boxed = [%d, %r]\n"
                "    dir()\n"
                "    return [type(boxed).__name__, boxed]\n"
            ) % (values[1], tag)
        blocks.append("def %s():\n%s" % (name, body))
    return "\n\n".join(blocks) + "\n", functions


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
        "import fuzz_surface\n" +
        prefix +
        "namespace = {}\n"
        "exec(Path(%r).read_text(encoding='utf8'), namespace)\n" % str(source) +
        "for name in %r:\n" % functions +
        "    actual = getattr(fuzz_surface, name)()\n"
        "    expected = namespace[name]()\n"
        "    assert type(actual) is type(expected), (name, actual, expected)\n"
        "    assert actual == expected, (name, actual, expected)\n" +
        suffix
    )


def verify_rejected_corpus(python, temp, environment):
    for name, source_text, expected in REJECTED_CASES:
        source = temp / ("rejected_" + name.replace("-", "_") + ".pyx")
        output = temp / ("rejected_" + name.replace("-", "_") + ".c")
        source.write_text(source_text, encoding="utf8")
        result = subprocess.run([
            python,
            "-m", "cython",
            "--runtime-backend=hpy-universal",
            "-3",
            "-o", str(output),
            str(source),
        ], cwd=ROOT, env=environment, capture_output=True, text=True)
        diagnostics = result.stdout + result.stderr
        if result.returncode == 0:
            raise AssertionError("rejected fuzz case compiled: %s" % name)
        if expected not in diagnostics:
            raise AssertionError(
                "rejected fuzz case %s lacked %r diagnostic:\n%s" %
                (name, expected, diagnostics))
        forbidden = ("Traceback (most recent call last)", "InternalError")
        if any(marker in diagnostics for marker in forbidden):
            raise AssertionError(
                "rejected fuzz case %s crashed:\n%s" % (name, diagnostics))


def build_and_run(python, seed=DEFAULT_SEED, case_count=DEFAULT_CASES):
    source_text, functions = generate_source(seed, case_count)
    with TemporaryDirectory(prefix="ahpy-supported-fuzz-") as temp_dir:
        temp = Path(temp_dir)
        source = temp / (MODULE_NAME + ".pyx")
        source.write_text(source_text, encoding="utf8")
        generated = temp / (MODULE_NAME + ".c")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        verify_rejected_corpus(python, temp, environment)
        run([
            python,
            "-m", "cython",
            "--runtime-backend=hpy-universal",
            "-3",
            "-o", str(generated),
            str(source),
        ], cwd=ROOT, env=environment)
        verify_source_boundary(
            generated,
            required=("#include <hpy.h>", "HPy_MODINIT", "HPy_mod_exec"),
        )

        setup = temp / "setup.py"
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "setup(name='ahpy-supported-fuzz', version='0.0.0', "
            "packages=[], py_modules=[], "
            "hpy_ext_modules=[Extension('fuzz_surface', "
            "['fuzz_surface.c'])])\n",
            encoding="utf8",
        )
        build_root = temp / "build"
        run([
            python,
            str(setup),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        binary = require_universal_binary(build_root, MODULE_NAME)
        verify_binary_boundary(binary)

        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(binary.parent)
        program = _runtime_program(source, functions, False)
        run([python, "-c", program], cwd=temp, env=runtime_environment)
        debug_environment = runtime_environment.copy()
        debug_environment["HPY"] = "debug"
        debug_program = _runtime_program(source, functions, True)
        run([python, "-c", debug_program], cwd=temp, env=debug_environment)


class SupportedSurfaceFuzzTest(unittest.TestCase):
    def test_generation_is_deterministic_and_seeded(self):
        first, names = generate_source(17, 12)
        second, second_names = generate_source(17, 12)
        changed, _ = generate_source(18, 12)
        self.assertEqual(first, second)
        self.assertEqual(names, second_names)
        self.assertNotEqual(first, changed)
        self.assertEqual(len(names), 12)
        compile(first, "<ahpy-fuzz>", "exec")

    def test_rejected_corpus_has_unique_names_and_diagnostics(self):
        names = [case[0] for case in REJECTED_CASES]
        self.assertEqual(len(names), len(set(names)))
        for name, source, expected in REJECTED_CASES:
            self.assertTrue(name)
            self.assertTrue(expected)
            if "cimport " in source or "cdef class" in source:
                continue
            compile(source, "<ahpy-rejected-%s>" % name, "exec")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=DEFAULT_SEED)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    args = parser.parse_args()
    if args.cases <= 0:
        parser.error("--cases must be positive")
    python_path = Path(args.python)
    if python_path.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    build_and_run(python, args.seed, args.cases)
    print(
        "Generated Universal HPy module: %d deterministic fuzz cases passed" %
        args.cases)


if __name__ == "__main__":
    main()
