# M6 generator HPy 0.9 gap validation record

Date: 2026-07-16
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
HPy: `0.9.0` Universal ABI
Status: design accepted; implementation externally blocked

The selected headers contain no public iterator-next type slots or generic
iterator operations. ADR 0006 therefore forbids reuse of CPython coroutine
utilities and defines the future field-backed suspended-state model.

Focused compiler tests cover a top-level `yield`, `yield from`, a returned real
generator expression, and lambda closure. Each produces exactly one
source-located Universal diagnostic, emits no C file, and contains no internal
traceback. Sequence-safe generator expressions consumed by the existing
inlined `list`/`dict`/`any`/`all` transformations remain independently tested
supported surface because they never publish a generator object.

After the change, 337 focused compiler tests and 70 quality-tool tests pass;
focused coverage traces 407 tests at 73.83% backend, 27.11% frontend seam, and
40.13% quality tools. The diagnostic catalog, compileall, workflow YAML, and
`git diff --check` gates are clean.

No generator-support checkbox is closed. Enablement requires a selected HPy
version with the ADR's public slot/iterator/exception prerequisites, followed
by resume, close, failure, GC, Debug, subinterpreter, ABI, and CPython parity
evidence.
