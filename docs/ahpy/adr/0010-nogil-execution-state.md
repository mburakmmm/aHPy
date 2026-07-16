# ADR 0010: Universal HPy execution-state transitions

- Status: accepted; narrow external-C slice implemented
- Date: 2026-07-16

## Context

Universal HPy code cannot implement Cython's `with nogil` by emitting
`PyEval_SaveThread`, `PyEval_RestoreThread`, or `PyThreadState *`. HPy 0.9 does
provide the public `HPyThreadState`, `HPy_LeavePythonExecution`, and
`HPy_ReenterPythonExecution` surface. That surface is sufficient only when no
Python/HPy operation, handle access, callback, or Python exception inspection
occurs while execution is left.

The existing external-C lane already validates concrete, injection-safe
headers, plain C identifiers, direct scalar signatures, and the absence of a
Cython/Python exception contract. It therefore supplies a bounded first
consumer of the HPy transition API without introducing CPython emulation.

## Decision

1. The initial Universal `with nogil` lane accepts a non-empty sequence of
   discarded, argumentless calls to validated external C functions declared
   `noexcept nogil`.
2. The emitter stores `HPy_LeavePythonExecution(ctx)` in a block-local
   `HPyThreadState`, performs only the admitted native calls, and invokes
   `HPy_ReenterPythonExecution(ctx, token)` before any HPy operation resumes.
   The generated interval contains no handle operation and no error exit. The
   type and transition expressions come from the typed RuntimeAPI contract;
   the syntax node does not select CPython or HPy thread APIs itself.
3. The native library contract is explicit: admitted functions must not call
   Python or HPy, access Python-owned state or handles, invoke a callback that
   does so, raise a C++ exception, or escape through `longjmp`. A concrete
   header cannot prove the implementation, so violating this contract is a
   user/library ABI error.
4. Calls with arguments remain rejected until every Python-to-native
   conversion is completed and checked before leaving execution, with only
   native temporaries live in the interval. Used return values remain rejected
   until the native result is retained and converted to an HPy value only
   after re-entry.
5. Python exception contracts, nested `with gil`, conditional/runtime
   transitions, C callbacks, pointers/buffers, C++/RAII, `prange`, OpenMP, and
   free-threading are independent gates. Re-entry cleanup must be modeled for
   every future native failure or structured-control-flow path before that path
   is enabled.

## Validation

The maintained setuptools example links a native probe, calls it while Python
execution is left, and checks its counter across repeated calls. The exact
generated `.hpy0` passes normal and HPy Debug execution, source-boundary checks,
and undefined-binary-import audits. Focused compiler tests prove the public HPy
spellings and reject argument-bearing and empty blocks without producing C.

## Remaining order

1. Preconvert supported scalar arguments, retain native results, re-enter, and
   only then box results; add conversion-failure and Debug cleanup tests.
2. Model nested transition state and exception reacquisition without CPython
   exception triples.
3. Design `prange`/OpenMP worker context ownership, cancellation, reduction,
   and re-entry separately.
4. Validate supported free-threaded interpreters as a distinct runtime lane;
   leaving execution is not itself a free-threading claim.
