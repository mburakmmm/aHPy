# M4 module-state validation record

Date: 2026-07-14  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: interpreter-owned module-namespace subset passes; remaining cache families are
in progress

## Generated structure

The Universal emitter now always defines an `HPy_mod_exec` slot. Supported
module assignments, overwrite, absolute imports, and `from` bindings execute
there. Referenced builtins and generated functions are resolved during module
execution. Each long-lived value is owned by the interpreter-created module;
functions dynamically load known globals from their module receiver. Builtins
are reached through a private module attribute. `.globals` is `NULL` and
`.size` remains zero for HPy 0.9.

Function Unicode, bytes, and recursively immutable tuple literals are
deduplicated into reserved module attributes during `HPy_mod_exec`. Repeated
calls load owned handles to the same interpreter-local objects. Cache
construction uses the ordinary reverse-order handle/builder cleanup path, and
source declarations colliding with the reserved prefix are rejected.
Side-effect-free scalar/list/tuple/dict defaults are likewise evaluated once
into per-definition reserved module attributes. Omitted arguments load the
stored object; provided parser handles are duplicated before tracker close.

No generated static variable has type `HPy`, `HPyGlobal`, or `PyObject *`.
Generated code publishes values and then closes the local handle. Every
function attribute load returns a tracked owned handle. Failed setup returns
`-1` through the same reverse-order cleanup mechanism used by function errors.

## Tests

`Cython.Compiler.Tests.TestHPyModuleWriter` covers emitted slots and the absence
of process-global object storage,
absolute and `from` imports, builtin loading, method caching, overwrite, missing
initialization sources, runtime reads before initialization, function global
set/in-place/delete, builtin fallback, and missing-name diagnostics.

`Tools/ahpy/test_generated_hpy.py` builds real Universal `.hpy0` modules.
The main corpus validates globals, overwrite, cross-function calls, imports,
builtins, reload, removal/reimport, 32 concurrent imports and global reads,
three create/run/destroy subinterpreter cycles, and per-interpreter mutation
isolation. It also exercises external rebinding, global assignment/in-place
update/deletion, missing read/delete `NameError`, positive fallback from a
deleted shadowing global to `builtins`, Unicode/bytes/tuple cache identity, and
positional/keyword-only defaults, mutable-default identity, missing-required
cleanup, and clean process teardown. The retry
corpus fails after importing a dependency but before finding an attribute.
Every module-exec error path removes the already-published generated methods,
breaking the module/function cycle before returning `-1`; normal and Debug
Mode assert removal from `sys.modules`, collect the failed HPy 0.9 loader
state, then fix the dependency and import again successfully. Debug Mode keeps
the failed path, collection boundary, and retry under `LeakDetector`, followed
by the full existing success/error corpus.

The expanded M8 fault gate additionally fails all generated type creations and
all 14 module/type attribute publication positions. Successful module
publications are recorded once and rolled back in reverse order after a
positively matched allocation failure. Since HPy 0.9 cleanup deletion may
clear the current error and offers no public fetch/restore operation, the
emitter re-establishes only the already matched `MemoryError`; other error
classes retain the ordinary non-speculative propagation path. All 128 isolated
normal/Debug processes pass with exact exception identity and clean handles.

The source scanner requires `HPyDef_SLOT`, `HPy_mod_exec`, module attribute
operations, and `HPyImport_ImportModule`; it rejects `HPyGlobal` storage in this
HPy 0.9 lane. All binaries also pass the undefined-symbol audit that rejects
CPython API imports.

The generated-method removal is required for HPy 0.9: its loader-owned
`PyModuleDef` can be released after failed initialization while a
module/function cycle remains pending for cyclic GC. Breaking that cycle on
every error exit prevents later traversal of stale loader memory and makes the
post-collection retry plus process teardown deterministic in both runtime
modes. Stress testing still observes intermittent loader `SystemError` for an
immediate retry without that collection boundary even though the failed module
is absent from `sys.modules`. That HPy 0.9 lifetime limitation is a documented
upstream/loader gap (see `docs/ahpy/module-state.md`); aHPy keeps the
collection gate and does not claim GC-free immediate retry as supported.

## Remaining M4 work

HPy 0.9 cannot supply isolated mutable state through either process-shared
`HPyGlobal` or its rejected positive module size. Unicode, bytes, imaginary,
and recursively immutable tuple caches therefore use module-owned values;
code-object caches remain blocked. Effectful defaults are cached once in
`HPy_mod_exec`. Relative/star imports and custom module `__getattr__` parity
remain rejected or planned. See `docs/ahpy/module-state.md` for the exact
safety boundary.
