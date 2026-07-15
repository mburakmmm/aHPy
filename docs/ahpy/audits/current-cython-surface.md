# Current Cython runtime surface audit

- Audit date: 2026-07-14
- Cython revision: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
- Machine-readable inventory: `capi-inventory.json`
- Generator: `Tools/ahpy/build_inventory.py`

## Runtime API baseline

The deterministic scanner inspected 110 compiler and utility source files and
found 589 distinct Python-API-shaped call symbols across 3,900 occurrences.
Conservative initial categories are:

| Category | Distinct symbols | Initial owner |
|---|---:|---|
| Directly mappable | 243 | M3 core runtime |
| Structurally different | 51 | M1/M2 runtime and ownership |
| Backend-independent replacement | 9 | M1 runtime seam |
| CPython legacy/private | 47 | M3 Universal enforcement |
| Unsupported until validated | 239 | M6 capability review |

Every symbol has an owner, rationale, occurrence count, and file list in the
JSON inventory. All classifications start with `classification_reviewed=false`.
This is intentional: the list establishes a complete conservative boundary,
while later focused reviews may promote a symbol only with a public HPy mapping,
ownership contract, and tests.

## Existing abstractions to reuse

Current Cython already contains several relevant portability paths:

| Marker | Occurrences | Files |
|---|---:|---:|
| `CYTHON_COMPILING_IN_LIMITED_API` | 308 | 23 |
| `CYTHON_AVOID_BORROWED_REFS` | 80 | 12 |
| `CYTHON_OPAQUE_OBJECTS` | 15 | 3 |
| `CYTHON_USE_MODULE_STATE` | 34 | 4 |
| `CYTHON_USE_TYPE_SPECS` | 37 | 6 |
| `CYTHON_COMPILING_IN_CPYTHON_FREETHREADING` | 65 | 12 |

These paths are implementation evidence, not an HPy abstraction by themselves.
They reduce direct struct access and borrowed-reference assumptions and must be
reviewed before creating parallel HPy-only helpers.

## Python object storage sites

### Locals and temporaries

- `Cython.Compiler.PyrexTypes.PyObjectType` defines the default C declaration,
  null value, reference-count operations, coercions, and assignment behavior.
- Expression and statement nodes request and release Python-object temporaries
  through the C code writer and function state.
- Disposal currently assumes `Py_INCREF`/`Py_DECREF` semantics and does not
  encode handle ownership in the type itself.

Required change: storage kind, ownership, and move/close state become explicit
compiler properties before an HPy emitter is enabled.

### Module globals and cached values

- `Cython.Compiler.Code.GlobalState.code_layout` has separate module-state,
  cached builtin, cached constant, global initialization, traversal, clearing,
  and cleanup sections.
- `Cython.Compiler.ModuleNode` generates PEP 489 module definitions, create/exec
  functions, module-state traversal, cleanup, and interpreter-compatibility
  declarations.
- Builtin/type/string/code-object caches are spread across ModuleNode and utility
  templates.

Required change: Universal mode registers long-lived values as `HPyGlobal` and
loads an owned local handle for each use. Loaded handles are closed on all exits.

### Extension type fields

- Extension layouts and slots are generated through ModuleNode, Symtab,
  PyrexTypes, TypeSlots, and `Cython/Utility/ExtensionTypes.c`.
- Python-valued fields currently use pointer/refcount and CPython traversal
  conventions.

Required change: pure HPy structs use `HPyField`; generated traversal visits
every owned field exactly once. No plain local `HPyField` and no long-lived
plain `HPy` are permitted.

### Closures, generators, and coroutines

- Closure scopes synthesize extension-like storage for captured values.
- `Cython/Utility/Coroutine.c` stores many Python references in suspended
  generator/coroutine objects, exception state, frames, weakrefs, code objects,
  names, and delegation state.

Required change: this is a separate M6 feature family. It must not reuse local
handle assumptions across suspension and is rejected until its field/traversal
model is complete.

### Memoryviews and buffers

- `Cython/Utility/MemoryView.pyx`, `MemoryView_C.c`, Buffer compiler support, and
  memoryview-slice types store object references and expose buffer lifetimes.

Required change: port through `HPy_buffer` and explicit acquired-buffer
ownership in M6. Object-dtype memoryviews remain blocked until separately
validated.

### Process globals and freelists

- Type caches, module caches, freelists, and some utility objects can exist as C
  globals depending on build configuration.

Required change: each Python-valued process global must become a registered
`HPyGlobal`, per-interpreter state, or an explicit Universal-mode diagnostic.

## HPyContext propagation boundary

The context is required for generated functions or helpers that perform any of
the following:

- create, duplicate, close, load, or store a handle;
- call Python, inspect truth/identity/type, or access an item/attribute;
- convert between native and Python values;
- manipulate exceptions;
- build containers;
- access module globals, cached values, or context constants;
- acquire/release a Python buffer;
- create or operate on HPy types.

Provably native C arithmetic, pointer operations, external C calls with a
Python-independent boundary, and pure native helpers do not receive context.
The context is a hidden generated argument and may not be stored in global,
field, closure, or suspended state.

Callbacks, public C APIs, closures, generators, coroutines, and `nogil` paths
remain disabled for HPy until their context acquisition/propagation contract is
separately accepted.

## Module and type initialization paths

Current Cython generates:

- a CPython `PyModuleDef`;
- PEP 489 create and exec slots;
- module-state allocation, lookup, clear, traverse, and free paths;
- cached builtin/constant/code object initialization;
- extension type declarations/specs and slot tables;
- global initialization and optional cleanup;
- embedded-module entry points where requested.

The HPy backend must replace this as a coherent module-level unit with
`HPyModuleDef`, `HPy_MODINIT`, `HPy_mod_exec`, registered globals, and HPy type
specs. It cannot be selected per function.

## Test baseline

The repository inventory contains 1,750 files under `tests`. Major suites are:

| Suite | Files |
|---|---:|
| `run` | 1,076 |
| `errors` | 277 |
| `compile` | 243 |
| `broken` | 51 |
| `build` | 38 |
| `memoryview` | 31 |
| `wrappers` | 10 |
| `pyximport` | 7 |
| `buffers` | 6 |

The initial aHPy conformance manifest selects five new CPython-oracle modules:

1. module functions, arguments, defaults, keywords, and returns;
2. tuple/list/dict/set builders and mutation;
3. raising, matching, propagation, and chaining;
4. imports, globals, builtins, attributes, and calls;
5. owned temporaries, early returns, loops, and failure cleanup.

On 2026-07-14, the CPython C backend compiled and ran all 19 doctests on Python
3.14.2 with Clang. This is the M0 semantic baseline. HPy support remains
`planned`; passing the CPython oracle does not change the support matrix.
