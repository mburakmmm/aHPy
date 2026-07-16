# ADR 0008: Buffer producer and consumer ownership model

- Status: producer design accepted; consumer blocked on HPy 0.9
- Date: 2026-07-16

## Context

HPy 0.9 defines `HPy_buffer`, `HPy_bf_getbuffer`, and
`HPy_bf_releasebuffer`. Its `HPy_buffer.obj` is an owned handle. The selected
public API does not provide the consumer-side equivalent of acquiring and
releasing an arbitrary object's buffer. Cython's existing buffer and typed
memoryview pipeline is built around `Py_buffer`, CPython utility code, and
Python reference-count operations, so it cannot be reused in Universal output.

## Decision

1. Producer and consumer support are independent. Available producer slots do
   not justify a typed-memoryview or buffer-argument support claim.
2. A future pure-type exporter uses a neutral compiler buffer descriptor that
   the HPy backend renders as `HPy_buffer`. On success, `view->obj` owns exactly
   one handle to the exporter; format/shape/strides/suboffsets storage has an
   explicit owner and remains valid until release.
3. Every failed `getbuffer` path rolls back partially initialized fields and
   closes the owned object handle exactly once. `releasebuffer` is idempotent,
   releases auxiliary native storage, closes `view->obj`, and leaves the view
   inert. It never stores a context beyond the slot call.
4. Consumer acquisition cannot be approximated with attribute calls,
   `memoryview()`, indexing, legacy conversion, or CPython `PyObject_GetBuffer`.
   Typed buffer and memoryview arguments remain rejected on HPy 0.9.
5. Universal declaration analysis rejects those arguments before CPython
   MemoryView utility injection. An early HPy-only abort preserves one accurate
   diagnostic; the CPython pipeline is unchanged.

## Enablement gates

Producer support requires normal/Trace/Debug export, writable/read-only and
format/shape/stride cases, failure at every initialization boundary,
release/deallocation ordering, retained views, GC, subinterpreters, source and
binary audits, and CPython parity. Consumer and typed-memoryview support also
requires selected public acquire/release APIs plus slicing/indexing, negative
strides, casts, contiguity, exception exits, and `nogil` lifetime tests.

## Consequences

- Pure-type buffer producers remain planned and locally actionable through a
  new neutral seam.
- Typed memoryviews remain externally blocked for HPy 0.9.
- No `Py_buffer` spelling or CPython memoryview utility may enter Universal C.
