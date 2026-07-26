# ADR 0010: Universal HPy execution-state transitions

- Status: accepted; scalar-argument/result/errno external-C slice implemented
- Date: 2026-07-16

## Context

Universal HPy code cannot implement Cython's `with nogil` by emitting
`PyEval_SaveThread`, `PyEval_RestoreThread`, or `PyThreadState *`. HPy 0.9 does
provide the public `HPyThreadState`, `HPy_LeavePythonExecution`, and
`HPy_ReenterPythonExecution` surface. That surface is sufficient only when no
Python/HPy operation, handle access, callback, or Python exception inspection
occurs while execution is left.

The existing external-C lane already validates concrete, injection-safe
headers, plain C identifiers, direct scalar signatures, and either no exception
contract or the exact signed-integer `except -1` errno contract defined below.
It therefore supplies a bounded first consumer of the HPy transition API
without introducing CPython emulation.

## Decision

1. The Universal `with nogil` lane accepts a non-empty sequence of zero- or
   scalar-argument calls to validated external C functions declared `noexcept
   nogil` or with the exact signed-integer `except -1 nogil` errno contract.
   Calls may be discarded or assign one supported scalar result to a Python
   local/global, attribute, item, or slice target.
2. For each call, the emitter completes its argument preparation, stores
   `HPy_LeavePythonExecution(ctx)` in a local `HPyThreadState`, performs only
   that admitted native call, and invokes
   `HPy_ReenterPythonExecution(ctx, token)` before the next statement begins.
   Per-call intervals preserve statement interleaving when later argument
   conversion has observable Python behavior. Each generated interval contains
   no handle operation and no error exit. The type and transition expressions
   come from the typed RuntimeAPI contract; the syntax node does not select
   CPython or HPy thread APIs itself.
3. The native library contract is explicit: admitted functions must not call
   Python or HPy, access Python-owned state or handles, invoke a callback that
   does so, raise a C++ exception, or escape through `longjmp`. A concrete
   header cannot prove the implementation, so violating this contract is a
   user/library ABI error.
4. Portable scalar literals are rendered directly. Every other supported
   argument completes source-ordered Python-to-native conversion and error
   checking before execution is left, and its temporary HPy handle is closed
   before the transition. Only native values remain live in the interval.
   A used scalar return is retained in a native temporary during the interval,
   converted to an owned HPy value only after re-entry, and then moved into its
   validated target. Python attribute/item argument expressions are evaluated
   and converted before leaving execution; Python attribute/item/slice result
   targets are evaluated and written only after re-entry.
5. For an admitted `except -1` function, the emitter sets `errno` to zero
   immediately before the native call and snapshots it immediately after the
   result, before any re-entry operation. After re-entry, a `-1` result restores
   the snapshot and calls public `HPyErr_SetFromErrno` with `OSError`; a zero
   snapshot raises a deterministic `RuntimeError` naming the broken native
   function. This applies to held-execution, retained-result, and discarded
   calls. `except?`, `except *`, unsigned returns, and non-`-1` sentinels remain
   rejected because they either require Python exception inspection or define a
   different native ABI contract.
6. Other Python exception contracts, nested `with gil`, conditional/runtime
   transitions, C callbacks, pointers/buffers, C++/RAII, `prange`, OpenMP, and
   free-threading are independent gates. Re-entry cleanup must be modeled for
   every future native failure or structured-control-flow path before that path
   is enabled.

## Validation

The maintained setuptools example links zero- and scalar-argument native
probes, calls them while Python execution is left, and checks their counter
across repeated calls. A raising `__index__` argument proves conversion failure
occurs before native entry, while an observing `__index__` proves a preceding
native statement completes before the next statement's conversion. The exact
generated `.hpy0` passes normal, HPy Trace, and HPy Debug execution, source-boundary
checks, and undefined-binary-import audits.
Focused compiler tests prove per-statement leave/call/re-entry,
conversion/close/leave/call/re-entry, and native-result/re-entry/HPy-box
ordering, including attribute/item arguments before leave and local/global,
attribute, item, and slice result writes after re-entry. Expanded arguments,
compound/destructuring result targets, and empty blocks are rejected without
producing C. The linked errno oracle proves held/released/discarded success,
`EDOM` conversion to `OSError`, unchanged native state on failure, and the
unset-errno `RuntimeError` path in normal/Trace/Debug and installed-wheel
execution.

## Remaining order

1. Independently evaluate compound/destructuring result targets and any native
   failure protocol beyond the exact `except -1` errno lane.
2. Model nested transition state and exception reacquisition without CPython
   exception triples.
3. Design `prange`/OpenMP worker context ownership, cancellation, reduction,
   and re-entry separately.
4. Validate supported free-threaded interpreters as a distinct runtime lane;
   leaving execution is not itself a free-threading claim.
