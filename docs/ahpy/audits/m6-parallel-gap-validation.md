# M6 parallel/OpenMP HPy 0.9 gap validation

Date: 2026-07-16
Status: design accepted; fail-closed gate green; implementation open

The HPy 0.9 header audit finds only the originating-thread
`HPy_LeavePythonExecution`/`HPy_ReenterPythonExecution` pair. It finds no public
OpenMP-worker attach/detach operation and no public Python exception-state
fetch/restore transport. The current Cython `ParallelStatNode` family, by
contrast, directly emits CPython thread states, GIL-state calls, exception
triples, and free-threaded mutex helpers.

ADR 0011 therefore defines a backend-neutral parallel plan and a staged
native-only first implementation. Focused Universal inputs cover both
`prange(..., nogil=True)` and `with nogil, parallel()`; each fails with one
source-located HPy 0.9 worker-contract diagnostic, produces no C, and explicitly
forbids the CPython path.

This record does not claim OpenMP, sequential `prange` fallback, reductions,
private/lastprivate behavior, scheduling, cancellation, worker Python access,
or free-threaded runtime support. Those gates remain open in the order defined
by ADR 0011.

Post-gate local evidence passes 345 focused compiler tests, 70 quality-tool
tests (one expected macOS Valgrind availability skip), and 415 traced tests at
73.69% backend, 28.75% frontend-seam, and 40.62% quality-tool coverage. The
upstream `sequential_parallel` runtime corpus passes all 74 C/C++ tests,
including fallback, reductions, private state, early exits, and exception
paths, confirming that the Universal rejection hook did not alter CPython
parallel semantics.
