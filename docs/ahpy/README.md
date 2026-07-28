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
- [Machine-readable CI policy](ci-policy.md)
- [Production branch ruleset](../../.github/rulesets/production-branches.json)
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

## Implemented scope

The implemented subset now covers module-level functions, the documented
expression/container/call/control-flow surface, module state and imports,
restricted current-error handlers, pure HPy extension types with HPy fields,
native scalar fields, GC, strict same-module single inheritance, supported
slots/properties, one-level closures, Python-independent external C calls, and
a strict native-only `with nogil` slice. Generators, coroutines, buffer
consumers and typed memoryviews, broad C++, and CPython-only third-party APIs
remain blocked, planned, or rejected as recorded in the support matrix.

The project does not claim that arbitrary Cython code is automatically
Universal-compatible. In particular, source code or dependencies that expose
`PyObject *`, include `Python.h`, cimport `cpython.*`, or depend on a CPython-only
third-party C API require a separate port or produce a compiler diagnostic.

## Current generated-code tier

The enabled tier accepts the explicitly documented partial surfaces for module
functions and pure HPy extension types. It emits public HPy-only C through the
typed runtime API/emitter seam, including exact HPy function/slot signatures,
interpreter-owned module/type state, deterministic definition arrays,
`HPyModuleDef`, and `HPy_MODINIT`. The support matrix is authoritative for each
supported, partial, blocked, and rejected family. Unsupported forms are
rejected at their source position; there is no CPython or Hybrid fallback.

`Tools/ahpy/test_generated_hpy.py` generates the maintained function and type
corpora from Cython source, scans the C boundary, builds Universal `.hpy0`
artifacts, and runs them in normal, Trace, and HPy Debug modes with explicit
leak detection. Focused compiler, failure-injection, fuzz, sanitizer,
portability, packaging, and CPython C/C++ regression gates complement that
runtime oracle.
