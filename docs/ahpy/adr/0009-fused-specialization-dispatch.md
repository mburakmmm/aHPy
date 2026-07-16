# ADR 0009: Fused specialization dispatch

- Status: accepted design; implementation planned
- Date: 2026-07-16

## Context

Cython expands fused functions into specialized C implementations and exposes
a Python dispatcher through `__Pyx_FusedFunction`, PyCFunction objects, code
objects, and CPython-owned signature metadata. Universal output cannot publish
those objects or embed their helpers. Merely compiling every C specialization
is insufficient: runtime selection, explicit `func[type]` indexing, conversion
errors, ambiguity ordering, defaults, metadata, and cleanup are observable.

## Decision

1. The frontend produces runtime-neutral specialization descriptors. Each
   descriptor contains a stable signature key, ordered argument conversion
   plan, result conversion plan, and static specialized implementation symbol.
   It contains no PyCFunction/code-object assumptions.
2. Universal mode publishes one pure-HPy callable object per fused function.
   `HPy_tp_call` performs exact Cython-compatible candidate selection and then
   invokes the chosen HPy wrapper. Explicit specialization uses a public HPy
   mapping/subscript slot and the same canonical signature keys.
3. Signature tables and specialization callables are interpreter-owned. They
   live on the defining module/dispatcher through HPy handles or `HPyField`s;
   no mutable static `HPy`, `HPyGlobal`, or context is stored.
4. Candidate probing distinguishes “not this specialization” from an actual
   conversion failure. It closes every temporary created by a rejected
   candidate before trying the next and preserves the exact terminal error.
   Ambiguity and preference order must match the CPython backend.
5. Native scalar conversion reuses a typed, backend-neutral conversion seam;
   it must not duplicate unchecked casts inside the dispatcher. Python-object,
   extension-type, memoryview, fused compound, and pointer families are enabled
   only by their own storage/ownership gates.
6. Defaults are evaluated once at module initialization and referenced through
   interpreter-owned metadata. `__signatures__` and explicit indexing expose
   only the documented supported subset; code-object/function introspection is
   not implied.
7. Fused extension methods, inheritance, overrides, public/API exports, and
   cross-module specializations are separate subgates after module functions.

## Implementation order

1. Extract neutral specialization descriptors while proving byte-identical
   default/explicit CPython output.
2. Add typed scalar argument/result conversion contracts and failure tests.
3. Emit a pure-HPy module-function dispatcher with explicit indexing.
4. Validate runtime selection, ambiguous/no-match cases, defaults, metadata,
   Debug cleanup, allocation failure, subinterpreters, and ABI boundaries.
5. Extend only then to methods and cross-module/public specializations.

## Current gate

Fused `def` and `cpdef` fail at their source in Universal mode with one
actionable diagnostic. No Universal C is emitted and CPython
`__Pyx_FusedFunction`/PyCFunction machinery is never selected. Ordinary Cython
C/C++ specialization remains unchanged.
