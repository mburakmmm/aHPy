# ADR 0008: Buffer producer and consumer ownership model

- Status: fixed native producer subset implemented; consumer blocked on HPy 0.9
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
2. The implemented subset accepts Cython's exact `Py_buffer` frontend spelling
   only as a validated descriptor for a writable one-dimensional fixed native
   scalar or private, positive, compile-time-sized native C-array field. The
   backend emits only `HPy_buffer` and public producer slots. Shape and stride
   are private object-owned `Py_ssize_t` fields, so their addresses remain
   valid while the exported view retains the object. General array member
   access/exposure and nested arrays remain outside this layout contract.
3. On success, `view->obj` owns exactly one `HPy_Dup` of the exporter. On
   failure no owned handle escapes. HPy's trampoline/runtime owns conversion
   and closing of that handle; the allocation-free `releasebuffer` body is a
   no-op and must not close `view->obj` a second time. No context or auxiliary
   allocation survives either slot call.
4. Consumer acquisition cannot be approximated with attribute calls,
   `memoryview()`, indexing, legacy conversion, or CPython `PyObject_GetBuffer`.
   Typed buffer and memoryview arguments remain rejected on HPy 0.9.
5. Universal declaration analysis rejects those arguments before CPython
   MemoryView utility injection. An early HPy-only abort preserves one accurate
   diagnostic; the CPython pipeline is unchanged.

## Enablement gates

The fixed native producer subset has all 13 enabled integer/float format
mappings for scalar and array layouts, Normal/Trace/Debug `long`, `double`, and
four-element `long` array export, writable mutation, native format/itemsize,
object-owned shape/stride storage, retained-view lifetime, ordinary
derived-type slot inheritance, source/binary audits, strict malformed-
descriptor rejection, CPython frontend compatibility, and scalar-plus-array
injected-dup failure/one-past coverage. Readonly exporters remain blocked
because HPy 0.9 exposes no named public writable-request flag;
multidimensional/general array-field, auxiliary-allocation, custom-release,
subinterpreter, and hosted platform evidence remain separate enablement gates.
Consumer and typed-memoryview support also requires selected public
acquire/release APIs plus slicing/indexing, negative strides, casts,
contiguity, exception exits, and `nogil` lifetime tests.

## Consequences

- Pure-type buffer producers are partial: the fixed writable scalar/private
  fixed-array contract is implemented and every broader descriptor fails
  closed.
- Typed memoryviews remain externally blocked for HPy 0.9.
- No `Py_buffer` spelling or CPython memoryview utility may enter Universal C.
