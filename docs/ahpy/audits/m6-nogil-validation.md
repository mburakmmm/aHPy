# M6 `nogil` execution-state validation record

Date: 2026-07-28
Status: scalar-argument/result/errno and explicit GIL-island slice green; broader family open

ADR 0010 limits the Universal `with nogil` implementation to discarded calls
or Python local/global, attribute, item, and slice result assignments whose
concrete external-C declaration
passed the existing Python-independent scalar validator and is additionally
marked `noexcept nogil` or exact signed-integer `except -1 nogil`. Portable literal
arguments become native constants; all other supported arguments complete
source-ordered HPy evaluation, checked conversion, error propagation, and
temporary closure before `HPy_LeavePythonExecution`. Generated code uses only
`HPyThreadState`, `HPy_LeavePythonExecution`, and
`HPy_ReenterPythonExecution`; it does not emit `PyThreadState *` or a CPython
thread-state function.

Focused compiler regressions prove exact per-statement conversion/close/
transition/call/re-entry order, including native-call/next-argument
interleaving, and native-result/re-entry/HPy-box order. Expanded arguments,
compound/destructuring result targets, and empty blocks fail closed with
source-located diagnostics and no generated C. Attribute/item arguments are
evaluated before leave, while global/attribute/item/slice result targets are
boxed and written only after re-entry. The maintained linked setuptools example
increments a native counter through zero- and scalar-argument calls, returns a
retained native result into each supported target family, proves a raising
`__index__` conversion does not enter
the native function, and proves earlier native statements are not reordered
behind later argument preparation in normal, HPy Trace, and HPy Debug modes. Its generated
source and `.hpy0` undefined imports are audited by the same integration gate.
The exact errno lane clears before each native call, snapshots before re-entry,
and raises public-HPy `OSError` only after re-entry; held, retained, and
discarded calls pass success and `EDOM` failure, while a native sentinel without
errno raises the documented `RuntimeError`.
An explicit non-empty `with gil` island may emit an already-supported Python
body between the per-call native intervals, where execution is active. The
linked callback oracle proves native/Python/native ordering and proves a
raising callback propagates its exception without entering the following
native call in normal, HPy Trace, and HPy Debug modes. Implicit,
conditional, and empty islands remain fail-closed.

This is not a claim for general `nogil`, compound/destructuring result targets,
other native failure protocols, callbacks, Python exception reacquisition,
long-lived nested transition state,
`prange`, OpenMP, synchronization, or free-threaded interpreter support. Each
remains an independent ownership and runtime gate.

The current local gates pass all 634 focused coverage tests: 65 ownership-model,
56 Runtime API, 249 Universal-emitter, 62 compiler-seam, and 202 quality-tool
tests (two expected platform/tool availability skips on macOS). CPython 3.11
reports 9408/9408 backend lines (100.00%), 15576/34007 frontend-seam lines
(45.80%), and 2848/5947 quality-tool lines (47.89%); CPython 3.14.6 independently
reports 9295/9295 (100.00%), 15673/34113 (45.94%), and 2853/5952 (47.93%).
The linked external-C module additionally passes source, binary, normal-runtime,
HPy Trace, HPy Debug, wheel-build, and installed-wheel execution gates.
