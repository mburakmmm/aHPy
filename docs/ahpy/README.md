# aHPy project contract

aHPy adds an explicitly selected Universal HPy code-generation backend to
Cython. The backend aims to compile the supported subset of `.py` and `.pyx`
sources into C that includes `hpy.h`, does not include `Python.h`, and can be
built as an HPy Universal extension.

The project is developed as a downstream Cython fork so that syntax parsing,
semantic analysis, type inference, optimisations, and the existing test corpus
remain available. Changes are structured as small upstreamable refactors.

## Non-negotiable behavior

1. `hpy-universal` is a module-level compiler/build choice.
2. Universal mode never silently falls back to a legacy or Hybrid ABI.
3. Direct Python C-API dependencies are diagnosed at their source location.
4. Handle ownership and lifetime are correctness properties, not text-level C
   substitutions.
5. Existing CPython code generation remains covered by the full Cython test
   suite.
6. A feature is supported only after its semantic, failure-path, HPy Debug Mode,
   cross-interpreter, and ABI-audit tests pass.

The normative implementation order and completion criteria are in
`TODO.md`. The current compatibility claims are in `support-matrix.md`.

Validate a development environment before compiling:

```console
python3 Tools/ahpy/doctor.py --python .venv-hpy09/bin/python
python3 Tools/ahpy/doctor.py --python .venv-hpy09/bin/python --json
```

The doctor preserves virtual-environment symlink paths, verifies the exact
stable or pinned development HPy version and Python lane, checks `hpy.h`, and
requires both a C compiler and a supported binary-symbol reader. `--strict`
also makes an otherwise valid development early-warning pin fail, which keeps
stable release jobs from silently using it.

Design and implementation references:

- [Runtime API seam](runtime-api.md)
- [Handle storage and ownership model](handle-model.md)
- [HPyContext propagation model](context-model.md)
- [Support matrix](support-matrix.md)
- [Validation matrix and release gates](validation-matrix.md)
- [Source compatibility scanner](migration-scanner.md)
- [Universal diagnostics catalog](diagnostics.md)
- [Setuptools/cythonize example](../../examples/ahpy_setuptools/README.md)
- [Direct non-setuptools build contract](direct-build.md)
- [Isolated PEP 517 build contract](pep517.md)
- [CMake, Meson, and scikit-build-core](build-systems.md)
- [Clean release-artifact onboarding](onboarding.md)
- [Python-independent external C contract](external-c.md)
- [M9 ABI performance baseline](audits/m9-abi-performance-baseline.md)
- [Architecture decisions](adr/)
- [Audits](audits/)

## Initial scope

The first vertical slice covers module-level functions, primitive conversions,
basic containers, calls, imports, and exceptions. Pure HPy extension types,
garbage collection, generators, coroutines, buffers, memoryviews, C++ support,
and third-party Python C APIs are later gated phases.

The project does not claim that arbitrary Cython code is automatically
Universal-compatible. In particular, source code or dependencies that expose
`PyObject *`, include `Python.h`, cimport `cpython.*`, or depend on a CPython-only
third-party C API require a separate port or produce a compiler diagnostic.

## Current generated-code tier

The enabled bootstrap tier accepts simple-identifier modules containing
undecorated `def` functions with required untyped ordinary, multiple, and
positional-only arguments. Its strict statement subset includes linear local
assignment/reassignment and one-clause conditional early returns; its value
subset is recorded in the support matrix. It emits public HPy-only C with
`HPyFunc_NOARGS`, `HPyFunc_O`, `HPyFunc_KEYWORDS`, deterministic definition
arrays, `HPyModuleDef`, and `HPy_MODINIT`. Unsupported forms are rejected at
their source position; there is no CPython fallback.

`Tools/ahpy/test_generated_hpy.py` generates this tier from Cython source,
scans the C boundary, builds a Universal `.hpy0` artifact, and runs it in normal
and HPy Debug Mode with explicit leak detection.
