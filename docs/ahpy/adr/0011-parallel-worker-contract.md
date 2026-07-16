# ADR 0011: Universal HPy parallel worker contract

- Status: accepted design; fail-closed gate implemented
- Date: 2026-07-16

## Context

Cython's current `prange`/OpenMP generator is CPython-specific at its hardest
boundaries. Worker setup, `with gil`, early exits, exception transport, and
free-threaded synchronization emit `PyThreadState *`, `PyEval_SaveThread`,
`PyGILState_*`, Python exception triples, and CPython mutex utilities.
Universal output cannot reuse that machinery.

HPy 0.9 exposes `HPy_LeavePythonExecution` and
`HPy_ReenterPythonExecution`, but they form a token pair on the originating
thread. The selected headers expose no public operation for attaching an
arbitrary OpenMP worker to the interpreter and no public exception-state
fetch/restore transport for moving a worker's Python error to the caller.

## Decision

1. The frontend must lower parallel semantics into a backend-neutral plan:
   normalized bounds and step, scheduling/chunk policy, thread condition and
   count, private/firstprivate/lastprivate values, reductions, cancellation,
   and structured exit effects. That plan contains no `PyThreadState`, Python
   exception triple, or CPython mutex assumption.
2. The first implementable Universal slice is native-only. All HPy-to-native
   conversions and validation occur on the originating thread before leaving
   execution. One master `HPyThreadState` token surrounds the parallel region;
   workers receive only native values and may not access `HPyContext *`, HPy
   handles/fields/globals, Python-owned state, callbacks, or memoryviews.
3. The initial native slice has no `with gil`, Python errors, worker-raised
   exceptions, object temporaries, early return/break, or cross-thread handle
   cleanup. Native reductions and lastprivate publication complete before the
   master re-enters Python execution; result boxing occurs after re-entry.
4. Builds without OpenMP preserve Cython's sequential semantic fallback while
   retaining the same leave/re-enter and native-only rules. Silently replacing
   an enabled parallel region with an ordinary HPy/Python loop is forbidden.
5. Python-capable workers remain blocked until a selected public HPy version
   defines worker attachment/detachment, context validity, error transport,
   cancellation, and cleanup semantics. A backend-private CPython escape hatch
   is not an acceptable Universal implementation.
6. Free-threading is a separate runtime capability. The backend must not infer
   support from CPython's `Py_GIL_DISABLED` or reuse CPython mutex macros.
   Supported HPy interpreters require their own concurrency and race tests.

## Current gate

`prange` and `cython.parallel.parallel()` fail at their source with one
HPy-0.9-specific diagnostic. No Universal C is emitted, and the diagnostic
explicitly rejects the existing CPython thread-state/exception-triple path.
Ordinary CPython C/C++ parallel code generation is unchanged.

## Implementation order

1. Extract the neutral parallel plan without changing CPython output.
2. Implement a no-error native counted loop, OpenMP-disabled fallback, static
   schedule, and scalar private/lastprivate semantics.
3. Add native reductions, `num_threads`, `chunksize`, and `use_threads_if`,
   each with race/TSan and CPython parity oracles.
4. Add deterministic native status/cancellation transport and re-entry cleanup.
5. Enable Python-capable workers only after the selected HPy API satisfies the
   public worker contract; then test Debug mode, subinterpreters, supported
   free-threaded runtimes, and failure injection independently.
