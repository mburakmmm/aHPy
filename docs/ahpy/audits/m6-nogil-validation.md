# M6 `nogil` execution-state validation record

Date: 2026-07-16
Status: narrow argumentless external-C slice green; broader family open

ADR 0010 limits the first Universal `with nogil` implementation to discarded,
argumentless calls whose concrete external-C declaration passed the existing
Python-independent scalar validator and is additionally marked
`noexcept nogil`. Generated code uses only `HPyThreadState`,
`HPy_LeavePythonExecution`, and `HPy_ReenterPythonExecution`; it does not emit
`PyThreadState *` or a CPython thread-state function.

Focused compiler regressions prove the exact transition/call/re-entry order.
Argument-bearing calls and empty blocks fail closed with source-located
diagnostics and no generated C. The maintained linked setuptools example
increments a native counter inside the interval and passes repeated-call
semantics in normal and HPy Debug modes. Its generated source and `.hpy0`
undefined imports are audited by the same integration gate.

This is not a claim for general `nogil`, used native return values, typed
arguments, callbacks, Python exception reacquisition, nested `with gil`,
`prange`, OpenMP, synchronization, or free-threaded interpreter support. Each
remains an independent ownership and runtime gate.

Post-change local gates pass 344 focused compiler tests, 70 quality-tool tests
(one expected macOS Valgrind availability skip), and the 38-test CPython C/C++
semantic oracle. Focused coverage traces 414 tests at 73.67% backend, 28.48%
frontend seam, and 40.62% quality tools, above the unchanged release floors.
