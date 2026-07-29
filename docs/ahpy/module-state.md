# Universal HPy module state

The bootstrap Universal backend executes Python module statements in a real
`HPy_mod_exec` slot. It never persists an `HPyContext *` and never stores a
Python object in a C global. HPy 0.9's `HPyGlobal` representation is process
shared and its runtime rejects positive-size module state, so neither mechanism
can provide isolated mutable state. Generated state therefore lives on the
interpreter-created module object and `HPyModuleDef.globals` remains `NULL`.

## Implemented lifecycle

Module execution initializes supported module assignments, absolute imports,
`from ... import ...` bindings, referenced module functions, and referenced
builtins. A newly created handle is checked before publication. Module values
are published with `HPy_SetAttr_s`, and then the local owned handle is closed.
Reassignment replaces the module attribute, whose owning interpreter controls
its lifetime. The builtins module is stored under a private module attribute.

Every known global read tests and loads the attribute on the module handle
received as the HPy method receiver. If it is absent, the same operation tests
and loads the name from the module-private builtins object. Absence in both
namespaces raises `NameError`; this avoids manufacturing and clearing an
intermediate `AttributeError`, which triggered an HPy 0.9 debug/runtime
teardown failure. Each loaded result is an owned, call-scoped handle registered
with the normal cleanup tracker and closed exactly once. Function-level
assignment, in-place update, and deletion publish through the same module
receiver, so external rebinding remains visible. A failed `HPy_mod_exec`
returns `-1` only after all currently owned handles and builders have been
released and every published generated method has been removed. Removing the
methods breaks the module/function cycle before HPy 0.9 releases its
loader-owned module definition; without that ordering, later cyclic GC can
traverse a stale `PyModuleDef` after a failed import.

Function Unicode, bytes, and recursively immutable tuple literals are
deduplicated by value. `HPy_mod_exec` constructs each cache entry once and
publishes it under a reserved `__pyx_hpy_const_` module attribute. Functions
load an owned handle from that interpreter's module and feed it into the normal
cleanup tracker. No cache is stored in static `HPy`/`HPyGlobal` memory. The
prefix is compiler-reserved; generated source cannot declare a colliding name,
and application code must treat these private attributes as implementation
state.

Supported argument defaults use the same ownership rule without deduplication:
each definition's scalar/list/tuple/dict default—including effectful expressions
such as `len([...])`—is evaluated once during `HPy_mod_exec` in source-safe
order and stored under a reserved `__pyx_hpy_default_` attribute. Omitted calls
load an owned handle to that object, preserving mutable-default identity within
an interpreter. Provided arguments are duplicated out of the HPy parser tracker
before the tracker closes. Python `__defaults__` / `__kwdefaults__`
introspection remains blocked on HPy 0.9 because module methods are not Python
function objects.

HPy 0.9 does not expose usable positive-size module state: its runtime rejects
`HPyModuleDef.size > 0`. The backend therefore keeps `.size = 0` and emits no
`HPyGlobal`. Migration to native module state
requires a stable public accessor plus equivalent traversal, teardown,
subinterpreter, and debug-mode tests; private context fields are not acceptable.

## Isolation and concurrency contract

The executable gate imports and destroys the same generated binary in multiple
CPython subinterpreters, mutates a returned module-global dictionary in each,
and proves that the main interpreter's dictionary remains unchanged. It also covers
reload, removal from `sys.modules`, repeated import, interpreter teardown, and
32 concurrent imports. Concurrent module initialization relies on the
interpreter import lock; generated object access requires a valid call-scoped
context and is never emitted in `nogil` code.

Failed initialization is tested with a second generated extension. Its first
absolute `from` import deliberately fails after acquiring the dependency
module. The gate asserts that import machinery removed it from `sys.modules`,
collects HPy 0.9's failed loader state, and then proves that a corrected retry
succeeds. HPy Debug Mode runs the failed path and collection boundary under
`LeakDetector`; generated-method removal also makes later cyclic-GC teardown
deterministic despite HPy 0.9's loader-owned module-definition lifetime.
Immediate retry without that explicit collection boundary is a documented
HPy 0.9 / loader lifetime upstream gap: stress has reproduced intermittent
loader `SystemError` even after the failed module was already absent from
`sys.modules`. aHPy therefore keeps the collection gate in
`Tools/ahpy/test_generated_hpy.py` (`retry_case`) and does not claim
GC-free immediate retry as supported Universal behavior.

Module initialization also maintains a source-ordered publication transaction
for backend-generated module attributes. Each successful publication is
recorded once. If a later allocation or attribute publication fails with a
positively matched `MemoryError`, live temporaries close, published attributes
roll back in reverse order, and `MemoryError` is re-established after cleanup.
This last step is required because HPy 0.9 attribute deletion may clear the
active error and exposes no public exception fetch/restore API. Non-memory
errors follow the ordinary propagation path and are never speculatively
replaced. A 128-process normal/Debug fault matrix exercises every generated
type creation and publication position.

## Deliberately unsupported or unsafe patterns

The strict emitter rejects these patterns instead of approximating them:

- relative and star imports;
- class-namespace lookup;
- custom module-level `__getattr__` semantics: HPy 0.9 exposes public
  attribute operations but no direct module-dictionary lookup, so generated
  modules must not install a custom module `__getattr__` until an exact public
  namespace access path is available;
- application mutation of reserved `__pyx_hpy_const_*` or
  `__pyx_hpy_default_*` implementation attributes;
- persisting a local `HPy`, an `HPyContext *`, or an unregistered Python object
  in static storage;
- access from `nogil` code or unsynchronized native threads; and
- richer extension-type caches and code-object caches; current pure HPy type
  objects, including generic `HPyField` layouts, ordinary methods, and the
  initial `HPy_tp_init` slice, are interpreter-owned module attributes, while
  HPy 0.9 has no public code-object construction API; and
- effectful defaults, Unicode, bytes, scalar, imaginary, recursively immutable
  tuple, and supported container defaults are interpreter-owned and evaluated
  once in source-safe `HPy_mod_exec` order.

These restrictions keep the current subset deterministic. Ordinary generated
modules preserve module-then-builtins lookup, external rebinding, builtin
shadowing/fallback, and missing-name behavior through public HPy APIs.
