# ADR 0005: Closure capture ownership model

- Status: accepted for Universal HPy nested-def slice
- Date: 2026-07-16

## Context

Cython's CPython backend builds nested `def` callables with CyFunction,
code objects, and a synthetic closure class of `PyObject *` fields.
HPy 0.9 exposes no public code-object constructor, and Universal mode forbids
CPython emulation. Closures therefore need an owned-handle capture model that
never stores `HPyContext *` in long-lived storage.

## Decision

1. Nested `def` (same module, one nesting level) is emitted as a pure HPy
   callable extension type whose `HPy_tp_call` runs a static nested impl.
2. Captured Python locals live in a synthesized env type as `HPyField`s.
   Loads and stores use `HPyField_Load` / `HPyField_Store` with the same
   ownership rules as ordinary extension object fields. Sibling nested
   functions share the deterministic union of all captures; a capture-free
   callable still retains an empty owned environment object.
3. The nested callable holds one `HPyField` referencing its env. Outer
   assignment into a captured name updates the shared env field so later
   nested reads observe the mutation.
4. `HPyContext *ctx` remains call-scoped only. Cells, env structs, callables,
   module state, and caches must never store `ctx`.
5. Explicitly rejected until separately gated M6 families or HPy API:
   nested-nested closures, `lambda`, nested defaults, `*args`/`**kwargs`,
   generators/`yield`, async, `nogil` capture, cdef-typed cells, decorators
   on nested defs, and code-object / `__code__` introspection claims.
6. No default-enabled half surface: unsupported forms raise actionable
   Universal diagnostics; supported forms pass normal/Debug cleanup.

## Consequences

- Closures move from planned to partial only with linked tests and matrix
  wording matching this slice.
- Generators remain a later family (resume policy) even when they share
  capture machinery ideas.
- Buffer/memoryview work stays independent (ADR-external M6 item 4).
