# HPyContext propagation model

`HPyContext *` is a call-scoped execution capability, not module state and not
a process-global singleton. aHPy models its need separately from C/C++ output
language and handle ownership.

## Backend contract

The CPython Runtime API has no context parameter. The HPy Runtime APIs expose a
non-persistable, call-scoped contract with type `HPyContext *` and conventional
name `ctx`. Every HPy runtime operation that needs context rejects an empty
context operand.

## Generated-function classification

| Function kind | Context policy |
| --- | --- |
| provably pure C | no hidden context |
| Python-interacting helper | hidden `HPyContext *ctx` required |
| callback | rejected pending entry policy |
| closure | rejected pending environment policy |
| generator/coroutine | rejected pending resume policy |
| public C API | rejected pending ABI policy |

A Python-interacting caller propagates its `ctx` to another
Python-interacting helper and passes nothing to a pure-C helper. A pure-C caller
cannot reach a context-requiring helper without first being reclassified. Any
attempt to store `ctx` in a field, global, closure, or other long-lived storage
is a compiler-model error.

Bootstrap Universal emission (`UniversalHPyModuleWriter`) already threads
call-scoped `ctx` through generated `*_impl` wrappers, `HPy_mod_exec`, and
every public-HPy runtime operation it emits. It does **not** load or rewrite
`Cython/Utility/*.c` helpers: those remain CPython-codegen assets. Until a
utility family is explicitly ported to HPy, Universal mode must keep emitting
direct public HPy calls rather than injecting `__Pyx_*` utilities. Provably
pure-C helpers used by the bootstrap emitter (for example traverse visitors
without Python operations) stay context-free by construction.
