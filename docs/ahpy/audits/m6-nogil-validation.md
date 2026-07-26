# M6 `nogil` execution-state validation record

Date: 2026-07-26
Status: scalar-argument/result external-C slice green; broader family open

ADR 0010 limits the Universal `with nogil` implementation to discarded calls
or Python local/global, attribute, item, and slice result assignments whose
concrete external-C declaration
passed the existing Python-independent scalar validator and is additionally
marked `noexcept nogil`. Portable literal
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
behind later argument preparation in normal and HPy Debug modes. Its generated
source and `.hpy0` undefined imports are audited by the same integration gate.

This is not a claim for general `nogil`, compound/destructuring result targets,
native failure protocols, callbacks, Python exception reacquisition, nested `with gil`,
`prange`, OpenMP, synchronization, or free-threaded interpreter support. Each
remains an independent ownership and runtime gate.

Post-change local gates pass all 566 focused coverage tests: 65 ownership-model,
56 Runtime API, 240 Universal-emitter, 62 compiler-seam, and 143 quality-tool
tests (two expected platform/tool availability skips on macOS). CPython 3.11
reports 9303/9303 backend lines (100.00%), 15500/33946 frontend-seam lines
(45.66%), and 2088/5016 quality-tool lines (41.63%); CPython 3.14.6 independently
reports 9190/9190 (100.00%), 15598/34053 (45.81%), and 2082/5010 (41.56%).
The linked external-C module additionally passes source, binary, normal-runtime,
HPy Debug, wheel-build, and installed-wheel execution gates.
