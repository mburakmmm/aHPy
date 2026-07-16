# ADR 0006: Generator suspension and resume model

- Status: accepted design; blocked on the selected HPy 0.9 public API
- Date: 2026-07-16

## Context

Cython's CPython backend implements generators with `PyObject *` coroutine
utilities, code objects, exception triples, and CPython iterator slots. None of
that machinery may cross the Universal ABI boundary. HPy 0.9 also lacks the
public iterator-next type slots and generic iterator operations required to
publish and drive a generator object.

## Decision

1. A future Universal generator object owns a pure-HPy state struct with a
   native resume label and `HPyField` storage for every Python value that lives
   across suspension. It never stores `HPyContext *`.
2. Every entry (`next`, `send`, `throw`, or `close`) receives a fresh context.
   A value may cross `yield` only after it is moved into a field or returned as
   an owned result; builders, trackers, borrowed arguments, and unrecorded
   owned temporaries may not remain live across suspension.
3. Traverse/clear visits every suspended field exactly once. Normal
   exhaustion, `GeneratorExit`, close, thrown exceptions, failed resume, and
   deallocation converge on one idempotent cleanup plan.
4. `yield from` additionally requires a public generic iterator protocol and
   sufficient public exception-state operations to distinguish termination,
   propagate failures, and preserve StopIteration values. It is not emulated
   with indexing or private APIs.
5. HPy 0.9 output rejects generator functions, `yield`, `yield from`, and real
   generator expressions with a versioned source diagnostic. Explicitly
   inlined sequence-safe consumers are not generator objects and remain a
   separate supported transformation.
6. Lambdas remain outside the accepted one-level closure slice and receive
   their own actionable diagnostic rather than being mistaken for a generator
   or synthesized through CPython code-object machinery.

## Enablement gate

Implementation may begin only after the selected HPy version provides the
required public type slots and iterator/exception operations, followed by a
version-policy update. The first enabled subset must include normal, Trace,
Debug, allocation-failure, early-close, partial-consumption, GC-cycle,
subinterpreter, source/binary ABI, and CPython-regression tests. Unsupported
`send`/`throw`/`close` or delegation semantics must remain diagnosed; no
default-enabled partial object is permitted.

## Consequences

- M6 generator implementation remains open and externally blocked for HPy 0.9.
- Native coroutines and async generators need an independent ADR and do not
  inherit support from this design.
- The frontend now fails before the CPython `Coroutine.c` utility path can be
  selected for Universal output.
