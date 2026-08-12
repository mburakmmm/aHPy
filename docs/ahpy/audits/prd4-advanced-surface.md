# PRD-4 advanced-surface closure

Date: 2026-07-29
Product envelope: unpublished aHPy preview
Machine-readable source:
[`tests/ahpy/advanced-surface.toml`](../../../tests/ahpy/advanced-surface.toml)

An advanced family is accepted only when its executable subset is fully tested
or its unsupported boundary fails closed with a source-located diagnostic and
migration guidance. No row below authorizes CPython, Hybrid, or private HPy
fallback.

| Family | Preview status | Decision and migration |
|---|---|---|
| Generic iterator protocol and pure-type iterator slots | blocked | HPy 0.9 lacks public generic iterator operations and iterator-next slots; use sequence-index loops or documented inlined consumers |
| Generators and `yield` protocols | blocked | ADR 0006 records the missing iterator/exception-state prerequisites; keep suspension in Python |
| Native coroutine and async generators | blocked | ADR 0007 records missing async slots and error-state ownership; keep orchestration in Python |
| Buffer producer | partial | ADR 0008's writable one-dimensional fixed native-scalar or private fixed native C-array subset emits public HPy producer slots, compiles all 13 enabled integer/float format mappings for both layouts, and passes `long`/`double`, four-element `long` array, derived-slot, retained-view Normal/Trace/Debug and scalar-plus-array duplication-failure oracles. HPy 0.9 has no named public writable-request flag for readonly exporters; multidimensional/general array-field, auxiliary-allocation, and custom-release exporters remain rejected |
| Buffer consumer and typed memoryview | blocked | HPy 0.9 has no public acquire/release consumer API; acquire in Python or a non-Universal boundary |
| Fused types | rejected | The preview compiler rejects CPython fused dispatch; publish explicit non-fused entry points |
| General `nogil` and re-entry | partial | Only ADR 0010's external scalar calls and explicit `with gil` islands are enabled |
| `prange`, OpenMP, synchronization, free-threading | blocked | HPy 0.9 has no public worker attach/error transport; keep workers Python-independent |
| C callbacks carrying Python state | rejected | Only callbacks invoked after validated explicit re-entry are allowed; no callback crosses the C boundary with HPy state |
| Capsules and cross-module public/C API | rejected | No preview exported Universal contract is defined; use Python calls or a handle-free external library |
| C++/STL/RAII | rejected | `--cplus` fails before output; isolate C++ behind a Python-independent C wrapper |
| Generated profiling/tracing/signatures/annotation/C-line traceback | rejected | Non-default instrumentation options fail before output; use external process-level tools or a CPython backend |
| Pickling, signatures, annotations, code objects | blocked | HPy 0.9 module methods lack Python function/code-object identity; publish explicit Python metadata wrappers |
| Embedding and multiple embedded HPy modules | rejected | Entry/context lifetime policy is not validated for the preview; use the supported CPython 3.11 HPy loader |
| NumPy and CPython-only third-party APIs | blocked | The dependency must expose a public HPy or Python-independent C API |
| Set construction/mutation | blocked | HPy 0.9 lacks the required public set APIs and `SetType`; construct outside the Universal subset |
| General exception state | blocked | `except as`, bare reraise, traceback/cause/chaining, `else`/`finally`, and nesting need public exception-state APIs |
| HPy method function-object introspection | blocked | `__defaults__`, signatures, code objects, and related metadata require explicit published objects |

## Evidence

- ADRs 0006–0011 freeze generator, async, buffer, fused, `nogil`, and parallel
  ownership/enablement contracts.
- The M6 gap audits prove one source-located diagnostic, no generated C, and
  preserved CPython regression behavior for blocked families.
- The enabled ADR 0010 slice passes source/binary audits, normal/Trace/Debug,
  installed-wheel execution, conversion/errno failures, and explicit GIL-
  island callback success/failure.
- ADR 0008's enabled fixed native producer translates the exact Cython frontend
  descriptor to `HPy_buffer`, keeps shape/stride storage object-owned, transfers
  one exporter handle to the runtime, and passes all 13 formats for scalar and
  private fixed-array layouts plus writable `long`/`double`, four-element
  `long` array, derived-slot, retained-view Normal/Trace/Debug and both Dup
  failure paths without `Python.h` or `Py_buffer` in output.
- `TestHPyModuleWriter` rejects C++ output, annotation, `profile`, `linetrace`,
  `embedsignature`, and C-line traceback instrumentation before output.
- The diagnostic catalog and support matrix assign all remaining source
  families a stable fail-closed boundary; the manifest test prevents an
  advanced family from becoming unclassified.

The current focused gates pass 441 compiler/seam tests and 530 quality-tool
tests (two expected platform/tool skips), generated normal/Trace/Debug
execution, 150 isolated fault selectors, the diagnostic catalog, and the
38-case CPython C/C++ oracle.
