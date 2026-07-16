# M6 fused dispatch validation record

Date: 2026-07-16
Status: design accepted; fail-closed gate green; implementation open

Focused Universal inputs declare an `int`/`double` fused type and exercise both
`def` and `cpdef`. Each produces one source-located diagnostic requiring a pure
HPy dispatcher, typed conversions, and interpreter-owned signature metadata;
the diagnostic prohibits CPython `__Pyx_FusedFunction` dispatch and no C file
is written.

ADR 0009 specifies the neutral descriptor, callable/subscriptable dispatcher,
candidate cleanup, ambiguity ordering, metadata, defaults, and staged
module-function-to-method enablement plan. The 38-test focused CPython C/C++
oracle remains green, demonstrating that ordinary specialization was not
disabled to satisfy the Universal gate.

This is not a fused-type support claim. Runtime semantics, Debug/fault cleanup,
explicit specialization, subinterpreters, ABI audits, methods, and cross-module
dispatch remain required before closing the family.
