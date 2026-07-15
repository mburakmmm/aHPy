# Runtime API seam

The Runtime API is the compiler-owned boundary between Cython syntax code
generation and operations supplied by a Python runtime API. It is selected once
per compilation context and has no mutable process-global selector.

## Backend names

| Name | Status | Intended use |
| --- | --- | --- |
| `cpython` | available, default | Existing Cython CPython C-API output |
| `hpy-universal` | strict bootstrap subset enabled | Universal HPy output |
| `hpy-cpython` | accepted, code generation gated | Test-only HPy CPython ABI lane |
| `hpy-hybrid` | reserved, rejected | Possible future explicitly scoped mode |

An unknown or reserved name is rejected while constructing compiler options.
The Universal name reaches a strict, deliberately incomplete bootstrap emitter;
unsupported syntax fails positionally before CPython code generation can
start. The HPy CPython ABI name remains gated. This prevents an apparently
successful HPy request from silently producing a CPython extension.

The compiler CLI exposes the selection directly:

```console
cython --runtime-backend=cpython module.pyx
```

Programmatic users pass the same value through `CompilationOptions`:

```python
from Cython.Compiler import Main, Options

options = Options.CompilationOptions(runtime_backend="cpython")
result = Main.compile("module.pyx", options=options)
```

The selected name participates in the compilation-cache fingerprint.

## Typed contract

`Cython.Compiler.RuntimeAPI.RuntimeAPI` is a structural protocol. Its first
operation groups are objects, calls, containers, conversions, exceptions,
globals, modules, and types. Backends advertise individual typed capabilities,
and unsupported features raise `RuntimeCapabilityError` with:

- the selected backend;
- the missing capability;
- the Cython source position when available;
- the semantic reason; and
- concrete migration guidance.

`CPythonRuntimeAPI` initially delegates to the existing type-specific code
generation methods. This makes the boundary output-neutral while later changes
can provide HPy implementations without scattering backend-name branches across
compiler nodes.

## First neutralized operations

The central C code writer now obtains its runtime API from the module's
compilation context. Reference duplication, close/clear/set operations, generic
null checks, unbound-value checks, and the generic exception-indicator check go
through that instance. Remaining direct CPython operations are intentionally
left visible and are migrated by the dependency-ordered M1 work items.

The regression guard compiles a representative function both with the default
selection and with explicit `runtime_backend="cpython"`; the generated files
must be byte-identical.

## Call layouts

Calls are represented by their semantic argument layout instead of selecting a
CPython helper directly in expression nodes. The initial layouts are:

- tuple plus optional keyword dictionary;
- no arguments;
- one positional argument;
- a C array with no keywords, a keyword-name tuple, or a keyword dictionary;
- a method C array whose receiver occupies the first argument slot; and
- a no-argument method call.

`RuntimeArrayCall` records the keyword layout, whether the array contains the
receiver, and the backend's selected utility implementation. The CPython
backend preserves all existing fast-call/vectorcall helper choices and rejects
the unsupported receiver-plus-keyword-dictionary combination instead of
guessing an argument layout.

The HPy implementation must follow the public HPy 0.9 call API verified on
2026-07-14:

- `HPy_CallTupleDict(ctx, callable, args, kw)` consumes tuple/dict handles;
- `HPy_Call(ctx, callable, args, nargs, kwnames)` receives positional values
  followed by keyword values, while `nargs` counts positional values only; and
- `HPy_CallMethod(ctx, name, args, nargs, kwnames)` requires the receiver at
  `args[0]` and includes it in `nargs`.

Authoritative references:

- <https://docs.hpyproject.org/en/latest/api-reference/hpy-call.html>
- <https://docs.hpyproject.org/en/latest/porting-guide.html>

## Container construction

Fixed-size list and tuple construction uses `RuntimeSequenceBuilder` metadata
and runtime operations rather than selecting C function names in syntax nodes.
The contract records facts that affect correctness:

- CPython builds directly into a `PyObject *` result, reports allocation
  failure from `PyList_New`/`PyTuple_New`, and its set-item operation steals the
  item reference;
- HPy uses a distinct `HPyListBuilder` or `HPyTupleBuilder`, builder creation
  itself does not report allocation failure, and `Set` does not steal the item
  handle;
- an HPy builder must be completed with `Build`, or released with `Cancel` on
  every failure path; and
- HPy provides `HPyTuple_FromArray` and `HPyTuple_Pack`, but list construction
  must fall back to `HPyListBuilder` where CPython can use a from-array helper.

Dictionary creation and population are also runtime operations. The CPython
backend retains `PyDict_New`, the presized Cython helper, `PyDict_SetItem`,
`PyDict_SetItemString`, and `PyDict_Copy` spellings. The HPy contract maps
these to `HPyDict_New`, `HPy_SetItem`, `HPy_SetItem_s`, and `HPyDict_Copy`;
HPy currently exposes no presized dictionary constructor, so the size hint is
intentionally ignored by that backend.

Constructor keyword parsing is a distinct runtime operation. HPy's
`HPy_tp_init` ABI supplies keywords as a dictionary rather than the tuple-like
name array used by `HPyFunc_KEYWORDS`, so pure HPy initializers call
`HPyArg_ParseKeywordsDict`; the ordinary method/function parser remains
`HPyArg_ParseKeywords`. Keeping both spellings behind the runtime contract
prevents a slot ABI from being accidentally parsed with a method ABI.

The native extension-field conversion boundary is likewise explicit. Owned
Python values convert through signed/unsigned `HPyLong_AsLong` or
`HPyLong_AsLongLong` variants and `HPyFloat_AsDouble`; exact-size slot results
use the separately modeled `HPyLong_AsSsize_t`, with
`HPyErr_Occurred` disambiguating sentinel values; C values materialize owned
results through signed/unsigned `HPyLong_From*` or `HPyFloat_FromDouble`. The
field writer separately checks each narrower target's platform limits before
casting.

The current HPy backends remain gated before code generation. The separate
builder storage and its cleanup paths become executable after the M2 handle
ownership model is in place. A static compiler test prevents the principal C
code emitters from reintroducing direct fixed-size construction calls outside
the runtime boundary.

Authoritative references verified on 2026-07-14:

- <https://docs.hpyproject.org/en/latest/api-reference/builder.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-dict.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-object.html>
- <https://docs.hpyproject.org/en/latest/api-reference/inline-helpers.html>
- <https://docs.hpyproject.org/en/latest/porting-guide.html#creating-lists-and-tuples>

## Primitive conversions

The central native-to-Python and Python-to-native `CType` paths now create an
immutable `RuntimePrimitiveConversion`. It records the direction, native C
type, selected helper, and a semantic kind: boolean, signed integer, unsigned
integer, float, complex, Unicode code point, C string, or custom. This prevents
the HPy emitter from having to infer conversion semantics from a CPython helper
name.

The CPython backend delegates the descriptor to the existing type-specific
emitter and therefore preserves its specialized overflow, enum, string target,
and error-sentinel behavior. The gated HPy backends raise the conversion
capability diagnostic until M2 supplies usable handle/context storage. Their
later implementation can select fixed-width core functions or the official
inline helpers according to the descriptor's native type and signedness.

Specialized memoryview and C-array conversions remain in their feature-specific
emitters. They are not primitive scalar conversions and depend on the M6 buffer
and memoryview model.

Authoritative HPy references verified on 2026-07-14:

- <https://docs.hpyproject.org/en/latest/api-reference/public-api.html>

## Method, slot, type, and module definitions

Definitions are structurally different from ordinary runtime calls and now
have their own contracts. `RuntimeMethodSignature` represents Cython's four
currently emitted method layouts without making emitter nodes select runtime
table syntax. CPython renders `PyMethodDef` entries with the existing casts and
flags; the HPy contract uses `HPyDef_METH` and a null-terminated `HPyDef *`
array. HPy macro definitions additionally require the implementation symbol to
follow the generated `<definition>_impl` convention.

`RuntimeTypeDefinition` distinguishes a CPython `PyType_Spec` plus
`PyType_Slot[]` from a pure `HPyType_Spec` plus `HPyDef *[]`. It records that a
pure HPy layout needs a builtin shape, omits `PyObject_HEAD`, and cannot carry
legacy slots. Verified public HPy slots map to `HPyDef_SLOT`; unsupported
CPython-only slots such as `Py_tp_members` fail the type-definition capability
instead of being renamed mechanically.

Module slot and definition declarations follow the same rule. CPython retains
`PyModuleDef_Slot`, `struct PyModuleDef`, and `PyModuleDef_Init` byte-for-byte.
The HPy contract represents `HPyDef *` arrays and `HPyModuleDef`, but rejects an
expression-style init result because HPy requires `HPy_MODINIT`. Complete HPy
wrapper functions and definition bodies remain M3/M5 work after M2 establishes
their handle signatures and cleanup rules.

Static tests enforce both architectural separations: runtime backend names do
not appear in general emitters, and the Runtime API does not choose C versus
C++ output. Backend semantics and output-language syntax therefore remain
orthogonal dimensions.
- <https://docs.hpyproject.org/en/latest/api-reference/inline-helpers.html>
- <https://docs.hpyproject.org/en/latest/porting-guide.html#direct-c-api-to-hpy-mappings>

## Exception state

Core exception emission now passes through the runtime API. The contract covers
setting an exception from a string, object, or `None`; formatted exceptions;
clearing and out-of-memory reporting; current-error matching; and the Cython
helpers used for raising, reraising, normalizing, saving, resetting, swapping,
fetching, and restoring exception state.

The contract deliberately separates two different models:

- public HPy provides current-error operations such as `HPyErr_SetString`,
  `HPyErr_SetObject`, `HPyErr_Format`, `HPyErr_Clear`, `HPyErr_NoMemory`, and
  `HPyErr_ExceptionMatches`;
- Cython's CPython backend also manipulates CPython's type/value/traceback
  exception triple through `__Pyx_*` helpers.

HPy exposes no public equivalent of that CPython exception triple. The gated
HPy backends therefore raise the `exceptions` capability diagnostic for
fetch/restore, supplied-exception matching, raise/reraise, normalize/get, and
save/reset/swap operations. This is an explicit design boundary, not a silent
CPython fallback or an inferred private-API mapping. M3 must either express a
feature using public HPy current-error semantics or keep that feature rejected
until a validated HPy mechanism exists.

Feature-specific helpers for argument parsing, buffer failures, unpacking, and
C++ exception translation remain owned by their corresponding milestones. A
static compiler test prevents the principal emitters from reintroducing raw
core `PyErr_*` or exception-triple calls outside the runtime boundary.

Authoritative HPy reference verified on 2026-07-14:

- <https://docs.hpyproject.org/en/latest/api-reference/hpy-err.html>

## Name resolution and global storage boundary

Dynamic module-global, builtin, and class-namespace lookups are separate
`RuntimeNameLookup` operations. CPython continues to emit the existing
`__Pyx_GetModuleGlobalName`, `__Pyx_GetBuiltinName`, and
`__Pyx_GetNameInClass` helpers byte-for-byte. A static guard prevents the main
compiler emitters from bypassing this boundary.

These dynamic namespace lookups must not be confused with long-lived cached
objects. In Universal HPy, a Python object held across calls must use a
statically allocated `HPyGlobal` registered in `HPyModuleDef.globals` (or a
separately validated public module-state mechanism). `HPyGlobal_Load` produces
a local handle for use in the current context, so its ownership and eventual
close must participate in M2's control-flow model. `HPyGlobal_Store` and load
are also per-interpreter operations even when the C variable itself is shared.

`RuntimeGlobalStorage` records the differences that code generation must not
infer from C type names. CPython storage is a `PyObject *`: loading it is
borrowed, initialization transfers an owned reference into the slot, and Cython
must traverse/clear its lifetime. HPy storage is a registered `HPyGlobal`:
loading returns an owned local handle, storing does not consume the input
handle, and the runtime owns the stored object's interpreter-lifetime
reference. The contract already emits the exact CPython assignment and HPy
load/store spellings; compiler caches are not routed through it until M2 can
prove every loaded handle is closed.

The gated HPy backend therefore rejects dynamic-name emission at this stage.
Emitting a direct HPy item/attribute call would omit Cython's fallback and
exception behavior, while substituting an unregistered long-lived handle would
break interpreter isolation. M2 owns registered-storage and local-handle
lifetime; M3 owns the module namespace helpers.

Module construction is a separate structural hook. Current HPy supports only
multi-phase initialization: the init function returns an `HPyModuleDef`, the
interpreter creates the module, and executable initialization belongs in an
`HPy_mod_exec` slot. There is no public manual `PyModule_Create` equivalent.

`RuntimeModuleDefinition` makes this structural difference queryable without
scattering backend tests across `ModuleNode`. The CPython contract permits
manual creation and legacy methods and does not require multi-phase execution.
The HPy contract requires multi-phase initialization, returns a definition from
its context-free init function, executes initialization through a slot that
receives both `HPyContext *` and the module handle, supports registered globals,
and forbids legacy methods in Universal output.

Core module-object operations now also cross the runtime boundary. CPython
retains the exact `PyImport_ImportModule`, `PyObject_SetAttr`,
`PyObject_SetAttrString`, `PyModule_Create`, `PyModule_GetDict`,
`PyImport_GetModuleDict`, and `__Pyx_PyImport_AddModuleRef` spellings. HPy maps
only the operations with public semantic equivalents:

- import becomes `HPyImport_ImportModule`;
- handle-named publication becomes `HPy_SetAttr`; and
- UTF-8-named publication becomes `HPy_SetAttr_s`.

Manual module creation, borrowed access to the module or `sys.modules`
dictionary, and creating/retrieving a registry entry are rejected under the
Universal HPy contract. HPy creates the extension module from `HPyModuleDef`,
and setup belongs in `HPy_mod_exec`; silently substituting an import or generic
attribute read would change failure, ownership, and reload behavior.

The remaining implementation order is deliberate. M2 first makes loaded local
handles ownership-tracked. M3 then emits the HPy definition, init macro, and
execution slot. M4 registers and migrates long-lived caches and validates
interpreter isolation. Extension-type field traversal remains in M5. This
prevents the backend seam from depending on cleanup logic that does not yet
exist.

Authoritative HPy references verified on 2026-07-14:

- <https://docs.hpyproject.org/en/latest/api-reference/hpy-global.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-type.html#hpy-module>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-object.html>
- <https://docs.hpyproject.org/en/latest/api-reference/public-api.html>
