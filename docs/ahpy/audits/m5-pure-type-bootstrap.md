# M5 pure-type bootstrap validation

The current M5 vertical slice accepts private `cdef class` declarations with
no base or with one earlier generated pure HPy base from the same module. Their
fields may be generic `object` values or enabled fixed C numeric scalars with
private, `public`, or `readonly` visibility. It emits a pure native struct
without `PyObject_HEAD`, `HPyType_HELPERS`, and an object-shaped
`HPyType_Spec`. Every object field is stored as `HPyField`; public and readonly
fields are exposed with custom `HPyDef_GETSET`/`HPyDef_GET` definitions, while
private fields remain native-only. The accessors use `HPyField_Load` and
`HPyField_Store` directly and preserve null-as-`None`, deletion-to-`None`, and
readonly behavior. They deliberately avoid HPy 0.9 `HPyMember_OBJECT`: the
Universal runtime mutates that static definition's offset while creating a
type, then adds the object-head offset again when the same binary creates its
type in another interpreter. The custom accessors therefore close an observed
second-interpreter wrong-offset/`None` read without introducing a CPython API.
A generated `HPy_tp_traverse` visits
every field exactly once and the specification enables
`HPy_TPFLAGS_HAVE_GC`. `HPy_mod_exec` creates the type with
`HPyType_FromSpec`, publishes it on the current module, and closes the local
owned handle. Function references reload the type from that interpreter-owned
module attribute.

The native-member slice accepts signed/unsigned byte, short, int, long, and
long-long storage plus `float` and `double`. Public and readonly declarations
use the matching `HPyMember_*` kind at their native struct offsets; allocation
zero-initialization, signed/unsigned and wide values, floating values, integer
overflow, wrong-type conversion, and readonly errors are exercised through the
real runtime descriptors. Native scalar storage is
not an owned handle and is therefore excluded from `HPy_tp_traverse`; a class
containing only these fields has neither the traverse slot nor
`HPy_TPFLAGS_HAVE_GC`. Generated methods load fixed fields directly through
`Struct_AsStruct` and materialize an owned `HPyLong`/`HPyFloat`; writes use the
matching signed/unsigned long or long-long helper, or `HPyFloat_AsDouble`,
check the HPy error state, and enforce the target C range before narrowing.
Private fields therefore never
fall back to Python attribute lookup. Cython's analyzed in-place coercion shape
is recognized for `+=`, `-=`, `*=`, `&=`, `|=`, `^=`, `<<=`, and `>>=`, and lowered back to
direct C field arithmetic/bitwise operations rather than HPy number calls.
Bitwise/shift results and RHS narrowing overflow pass normal/debug cleanup.
For the currently enabled untyped method arguments, native `/=`, `//=`, `%=`,
and `**=` follow Cython's analyzed Python-result path: the emitter materializes
the field as an owned HPy number, invokes the exact public HPy in-place API,
then converts and range-checks the owned result back into native storage.
Negative floor/modulo, zero division, float division, integer true-division
result rejection, power overflow, and normal/debug cleanup pass. Future typed
arguments retain a separate direct-C directive gate. `bint` uses `char`
storage exactly as required by
`HPyMember_BOOL`. Public descriptors accept exact bool values, while
constructor/private method writes use Cython's general truth-test conversion;
direct loads materialize owned `True`/`False` handles and the field never
participates in GC traversal. `Py_ssize_t` uses exact `HPy_ssize_t` storage and
the matching `HPyMember_HPYSSIZET` descriptor. Constructor and private method
writes use `HPyLong_AsSsize_t` with HPy error-state checking, direct loads
materialize an owned integer handle, and real normal/debug execution covers
the platform `sys.maxsize` and `-sys.maxsize-1` boundaries plus overflow on
both write paths. It is also excluded from traversal. Typed direct-C
division/modulo/power directive semantics retain a separate gate. External C
declaration blocks and external typedef fields are rejected because the header
owns their width, signedness, and alignment; enum fields are rejected because
their compiler-selected layout must not be guessed as C `int` or
`HPyMember_INT`. Dedicated diagnostics and compile-failure tests enforce both
policies until their ABI gates exist. `long double` retains exact native
storage and deliberately has no `HPyMember_DOUBLE` alias. Public fields use a
Universal `HPyDef_GETSET` descriptor and readonly fields use `HPyDef_GET`;
their getter/setter boundary converts through Python's double precision just
like Cython, rejects deletion and readonly writes, propagates conversion
errors, and remains outside GC traversal. Constructor, private/direct method,
public, readonly, deletion, wrong-type, and normal/debug leak paths pass.
Non-external local
scalar typedef chains are resolved completely to the enabled base storage and
member kind; no typedef declaration or guessed layout crosses into generated
output. An unsigned-short typedef passes normal/debug public, readonly,
constructor, direct-load, private-write, negative, large-overflow, and
descriptor `RuntimeWarning`/narrowing behavior. External typedef blocks remain
rejected before code generation. Plain `char` has its own exact gate: storage
and public/readonly descriptors use `char` and `HPyMember_CHAR`,
so Python attribute access accepts and returns one-character ASCII strings,
while direct Cython method access remains numeric. Method/constructor writes
use signed-long conversion guarded by the target platform's `CHAR_MIN` and
`CHAR_MAX`; direct loads return owned integers. Normal/debug execution covers
zero initialization, both access models, invalid non-ASCII/multi-character
descriptor writes, and an out-of-range numeric write, with no GC ownership.

Ordinary undecorated instance methods without special names are emitted as
`HPyDef_METH` definitions in the type's definition array. The runtime receiver
is bound as the method's borrowed `self` handle; zero, one-positional-only, and
keyword-capable remaining signatures reuse the same checked argument layouts
as module functions. Side-effect-free scalar/list/tuple/dict defaults are
stored on the defining type and loaded through the runtime `self.__class__`,
covering inherited lookup, mutable identity, positional/keyword overrides, and
keyword-only rejection in normal and Debug Mode. Every generated type also
owns a hidden reference to its defining module. Ordinary methods and supported
slot wrappers load it through `self.__class__`, enabling dynamic module-global
rebinding, builtins, and interpreter-owned constant caches without static
`HPyGlobal` state. Reserved cache-name collisions are rejected before code
generation. Generic object-field reads, writes, and in-place updates use
the generated `Struct_AsStruct` helper plus `HPyField_Load`/`HPyField_Store`;
they never route private fields through Python attribute lookup. A null field
is materialized as an owned `None`, matching Cython's initialized/deleted field
semantics.

Python protocols without HPy type slots use the same ordinary-method lane.
`__format__`, `__bytes__`, `__complex__`, and `__round__` are published as
`HPyDef_METH` definitions with `HPyFunc_O`, `HPyFunc_NOARGS`, or the checked
keyword-capable signature as required. The generated runtime proves builtin
`format`, `bytes`, `complex`, and one/two-argument `round` dispatch, inherited
lookup, invalid bytes/complex result rejection by the interpreter, and body
error propagation in normal, HPy Trace, and HPy Debug modes. Invalid source
arities fail before C emission; no fictitious `HPy_tp_*` slot is generated.

Synchronous context-manager protocols also use the ordinary-method lane.
`__enter__(self)` is emitted as `HPyFunc_NOARGS`, while
`__exit__(self, exc_type, exc_value, traceback)` uses the checked
keyword-capable wrapper. The generated corpus proves successful entry and
exit, true-result exception suppression, false-result propagation, inherited
lookup, and body-error propagation in normal, HPy Trace, and HPy Debug modes.
Invalid source arities fail before C emission with an actionable diagnostic;
no fictitious context-manager type slot is generated, and asynchronous context
methods remain behind their independent HPy 0.9 gate.

HPy 0.9's generic pure-type deallocator invokes every registered traverse
implementation with a clearing visitor before optional `HPy_tp_destroy` hooks.
The generated traversal therefore serves both cyclic GC and ordinary refcount
teardown. A Python payload with an observable finalizer remains alive while an
`HPyField` owner exists and is released immediately when that owner is
deallocated; normal and Debug Mode both pass. User-defined finalization,
resurrection, weak references, and non-HPy native resource destruction were
initially separate gates. The finalization gate now maps `__del__` to exact
`HPy_tp_finalize`/`HPyFunc_DESTRUCTOR`. Success returns void; every supported
failure path closes owned handles and argument trackers, calls
`HPyErr_WriteUnraisable(ctx, self)`, and returns without leaking the error.
A finalizer that appends itself to an external list resurrects once, is not
called again after the resurrected reference is released, and then deallocates
normally. A raising finalizer reaches `sys.unraisablehook` with its original
`RuntimeError`. Deleting a public object descriptor stores `None` into its
`HPyField` and observably releases the old payload immediately. These paths
pass normal and Debug Mode. Weak references and non-HPy native resource
destruction remain separate gates.

HPy 0.9 exposes no public weak-reference layout field, offset slot, or
`HPyType_SpecParam` contract. Its CPython runtime's internal `tp_weaklist`
handling is not a Universal API and must not leak into generated code. The
backend therefore rejects a `cdef object __weakref__` declaration with a
versioned, actionable diagnostic until a portable HPy type-layout surface is
available.

The same rule applies independently to instance dictionaries. HPy 0.9 exposes
no public portable `__dict__` layout, offset, or type-spec contract; generated
Universal code must not synthesize CPython's `tp_dictoffset`. A `cdef dict
__dict__` declaration is therefore rejected with its own versioned ABI
diagnostic.

The first special-method slice lowers a required-untyped `__init__` method to
an `HPy_tp_init` slot. Unlike an ordinary keyword method, this slot receives an
HPy dictionary for keywords, so the implementation uses
`HPyArg_ParseKeywordsDict` and an integer `0`/`-1` success contract. The
receiver is borrowed, parsed argument handles are tracked, direct object-field
stores use `HPyField_Store`, and every success/error path closes its owned
handles and tracker. Positional and keyword construction pass in both normal
and HPy Debug Mode for object and native C `int`/`double` field stores;
constructor conversion/overflow failures are leak-checked as well.
Side-effect-free literal/list/tuple/dict defaults on `__cinit__`, `__init__`,
and `__call__` are evaluated once during module exec, copied from the module's temporary
cache to hidden attributes on the defining type, and loaded through
`self.__class__`. This keeps them interpreter-owned, avoids static
`HPyGlobal`, and lets a derived type inherit the defining type's default
naturally. Default and positional/keyword override paths pass normal and Debug
Mode; mutable list/dict defaults retain one-time identity across instances.
The `__cinit__` gate gives every type with a local or inherited C initializer
an `HPy_tp_new` wrapper. It allocates once with `HPy_New`, calls generated
helpers from the oldest base through the most-derived class using the original
positional/keyword constructor arguments, and only then permits `HPy_tp_init`
to run. A nullary helper intentionally ignores those arguments, matching
Cython's base-class compatibility rule. If any helper fails, the owned partial
instance is closed; HPy 0.9's traverse-driven deallocator clears local and
inherited `HPyField` payloads. Normal and Debug Mode cover local and derived
failures, base-before-derived field visibility, `__cinit__` plus `__init__`
ordering, callable construction, dynamic module-global reads, type-owned
mutable defaults, and subinterpreter isolation.

The Cython frontend rejects extension-type `__new__` before the HPy emitter and
directs users to `__cinit__`; that guard remains intentional until custom
`HPy_tp_new` allocation has layout, base-chain, and partial-cleanup validation.
Custom allocation hooks, overridden/explicit base-initializer calls,
native-resource deallocation, and all other special methods remain separate gates. A derived
type without its own initializer inherits the
supported base initializer through the runtime type hierarchy; positional and
keyword construction are exercised in normal and Debug Mode.

The initial callable-type slice maps `__call__` to `HPy_tp_call` with the exact
`HPyFunc_KEYWORDS` fast-call signature and reuses the checked positional-only
and keyword parser. HPy 0.9 implements this slot through a hidden vectorcall
field; its fallback constructor delegates to `object.__new__` and rejects
arguments before a custom initializer can run. Every supported callable type
therefore receives `HPy_tp_new`; its implementation uses `HPy_New` to zero the
pure payload and initialize HPy's vectorcall field. When the type has a local
or inherited supported `__init__`, argument validation remains with the
effective `HPy_tp_init`. With no effective initializer, `HPy_tp_new` accepts
only an empty positional/keyword constructor call before allocation.
Positional/keyword/default initialization, inherited initialization and
default lookup, empty no-init construction, no-init argument rejection,
positional-only misuse,
missing/extra/unexpected call arguments, owned results, and normal/Debug Mode
cleanup pass.

`__dealloc__` is rejected with a dedicated ABI diagnostic instead of being
mistaken for an ordinary unsupported special method. HPy 0.9 maps its resource
hook to `HPy_tp_destroy`, whose implementation receives only `void *` storage,
not an `HPyContext` or an `HPy self` handle. The backend will enable it only
after native-resource-only bodies have a separate validator; supported
Python-level finalization remains `__del__`/`HPy_tp_finalize`.

A real module-aware type executes module/global-dependent `__cinit__`, `__init__`,
`__call__`, `__repr__`, `__len__`, mapping lookup/mutation, `__hash__`,
`__bool__`, `__contains__`, rich comparison, and `__del__` bodies. Dynamic
global rebinding is visible immediately; finalization records into a
module-owned event list. The type-to-module ownership cycle passes normal
execution and HPy Debug Mode without leaked handles. Three subinterpreters each
receive independent generated types, module globals, method lookups, constructor
and special-call behavior, and finalizer event lists; their mutations do not
affect the main interpreter.

For strict single inheritance, the emitter does not depend on HPy 0.9 to copy
lifecycle slots implicitly. It resolves the effective initializer and callable
method, constructs an explicit base-to-derived `__cinit__` helper chain, and
emits local `HPy_tp_init`, `HPy_tp_call`, and vectorcall-safe `HPy_tp_new`
wrappers where required. Cython's cloned inherited-field entries
are aliased to the same embedded base storage, so derived methods retain direct
private/native field access. A subtype whose only owned fields come from its
base still emits its own traverse wrapper, calls the base traverse exactly
once, and carries `HPy_TPFLAGS_HAVE_GC`, satisfying HPy type-spec validation.

Rich comparison methods share the single `HPy_tp_richcompare`/
`HPyFunc_RICHCMPFUNC` slot required by HPy. The wrapper switches on
`HPy_RichCmpOp` and dispatches all six operations to independently generated
helpers with borrowed receiver/other handles and owned arbitrary Python
results. An unimplemented opcode returns an owned duplicate of the public
context `NotImplemented` handle, preserving reflected/fallback behavior rather
than synthesizing a boolean. All six dispatch branches, identity of borrowed
operand/field/self results, a partial implementation's ordering `TypeError`,
and normal/Debug Mode cleanup pass.

The binary numeric gate covers all two-argument families exposed by HPy 0.9:
add, subtract, multiply, remainder, divmod, floor/true divide, left/right
shift, bitwise and/xor/or, and matrix multiply. Each root type's normal and
reflected methods share the exact corresponding `HPy_nb_*` slot; all matching
in-place slots except the nonexistent in-place divmod are emitted separately.
Each generated type receives a unique hidden marker attribute whose value is
an HPy context constant and whose storage is owned by that interpreter's type.
The wrapper obtains both operand types with `HPy_Type` and tests for its marker,
so it can select normal versus reflected direction without static `HPyGlobal`
state, CPython `PyTypeObject` access, or slot-pointer comparison. Owned
`NotImplemented` results are closed before fallback and duplicated only for
the final slot result. Normal and Debug Mode execute all 13 left/right and 12
in-place operations and cover unrelated aHPy operand types, reflected-only
same-type dispatch, user `NotImplemented`, right-method fallback, and raised
errors; three subinterpreters independently recreate and exercise the marker.
When a generated derived type overrides either normal or reflected direction,
the emitter merges the effective ancestor method and renders its already
analyzed body against the derived field layout. Runtime tests prove inherited
field access, a derived reflected override's priority for `Base + Derived`, the
normal inherited direction for `Derived + Base`, unrelated operands, and
inherited versus overridden in-place methods.

Power uses its separate `HPyFunc_TERNARYFUNC` ABI through exact
`HPy_nb_power` and `HPy_nb_inplace_power` slots. `__pow__`, `__rpow__`, and
`__ipow__` accept Cython's two- or three-argument source forms. The slot passes
the modulus directly to a three-argument implementation; a two-argument
implementation accepts HPy's `None` sentinel and rejects a real modulus with a
deterministic `TypeError`. A source `modulus=None` default therefore needs no
interpreter-owned default cache. The marker dispatcher merges inherited normal
and reflected directions and retains subtype priority. Normal and Debug Mode
cover ordinary, reflected, explicit-modulus, and in-place calls, inherited
dispatch, `NotImplemented` fallback, raised errors, and cleanup.

The first value-returning special methods, `__repr__` and `__str__`, use the
`HPy_tp_repr` and `HPy_tp_str` `HPyFunc_REPRFUNC` slots rather than appearing as
ordinary methods. Their receiver remains borrowed, object-field results are
loaded as owned handles, and both valid strings and the runtime's non-string
`TypeError` path pass normal and Debug Mode leak checks.

The first scalar-returning slot, `__len__`, publishes both `HPy_sq_length` and
`HPy_mp_length` with the exact `HPyFunc_LENFUNC` `HPy_ssize_t` contract. Its
Python result remains owned until
`HPyLong_AsSsize_t` completes; `-1` is treated as failure only when an HPy error
is set, and a successfully converted negative value raises `ValueError` before
the slot returns `-1`. Positive/zero values, truth testing, non-integers,
overflow, negative values, and all associated cleanup pass normal and Debug
Mode execution.

The subscript family lowers two-argument `__getitem__` to
`HPy_mp_subscript`/`HPyFunc_BINARYFUNC` and adds an exact
`HPy_sq_item`/`HPyFunc_SSIZEARGFUNC` adapter. The adapter converts its native
index with `HPyLong_FromSsize_t`, passes that handle to the analyzed mapping
body, and closes it on success or error. `__setitem__` and `__delitem__` remain
coupled behind both `HPy_mp_ass_subscript` and `HPy_sq_ass_item`; the sequence
adapter applies the same owned-index rule and preserves HPy's null-value
deletion signal. Receiver/key/value inputs remain borrowed and Python results
remain owned. Real sequence iteration, direct mapping and CPython sequence-API
length/mutation/deletion calls, inherited length/assignment, a derived lookup
override, underlying lookup/set/delete errors, and cleanup all pass normal and
Debug Mode.

User-written extension-type `property` blocks use public `HPyDef_GET`,
`HPyDef_SET`, or `HPyDef_GETSET` definitions according to their accessor set.
Getter and setter closures are unused, receiver/value handles remain borrowed,
the setter wrapper distinguishes HPy's null deletion signal, and accessor
bodies share the ordinary field/global ownership model. Property docstrings,
getter-only and setter-only errors, complete get/set/delete behavior,
body-raised lookup errors, inherited descriptors, three independently created
subinterpreter types, and normal/Debug Mode cleanup pass. Synthesized
properties for `public` fields are identified by their physical field names
and stay on the separately validated custom-field/member path, preventing
duplicate descriptors.

Slotless `__format__` is deliberately exposed as an ordinary `HPyDef_METH`
definition: Python's `format()` resolves the method normally and HPy 0.9 has
no corresponding type slot to synthesize. A positional-only source spelling
uses `HPyFunc_O`; the already checked keyword wrapper remains available when
the source method permits keyword calls. Valid strings, the runtime's
non-string-result `TypeError`, body-raised `KeyError`, inheritance, and
normal/Debug Mode cleanup pass.

The first hash slot uses `HPy_tp_hash`/`HPyFunc_HASHFUNC`. It validates the
owned Python result against the public `LongType` context handle with
`HPy_TypeCheck`, then calls `HPy_Hash` rather than narrowing directly. This
preserves Python's arbitrary-width integer hash reduction and `-1` to `-2`
normalization; small, very large, `-1`, and non-integer returns pass their exact
normal/Debug Mode success or error paths.

`__bool__` uses `HPy_nb_bool`/`HPyFunc_INQUIRY`. Current Cython extension types
analyze this method as a C `int` return, so the HPy emitter deliberately uses
`HPyLong_AsLong` plus `INT_MIN`/`INT_MAX` validation rather than imposing the
different exact-`bool` rule of a Python class. Zero, one, another nonzero
integer, non-integer conversion failure, and overflow all pass normal and Debug
Mode cleanup.

The first unary numeric family maps `__neg__`, `__pos__`, `__abs__`, and
`__invert__` to `HPy_nb_negative`, `HPy_nb_positive`, `HPy_nb_absolute`, and
`HPy_nb_invert`. These slots share `HPyFunc_UNARYFUNC`; their receiver is
borrowed and their arbitrary Python result is returned as an owned handle.
Field-backed identity results pass all four operators in normal and Debug Mode.

The conversion unary family maps `__int__`, `__float__`, and `__index__` to
`HPy_nb_int`, `HPy_nb_float`, and `HPy_nb_index`. The helpers return an owned
Python value; the interpreter's ordinary `int()`, `float()`, and index protocol
enforce the required result type. Valid integer/float values and all three
wrong-result-type paths pass normal and Debug Mode cleanup.

Membership maps `__contains__` to `HPy_sq_contains`/`HPyFunc_OBJOBJPROC`. The
receiver and searched value are borrowed, while the method result follows the
same checked C `int` conversion as Cython's inquiry slots. True, false,
non-integer, and overflow paths pass normal and Debug Mode cleanup.

The initial inheritance slice embeds the complete base payload as the first
member of the derived native struct and appends only fields declared by the
derived class. `HPy_mod_exec` loads the base type from the current
interpreter's module namespace, passes it through
`HPyType_SpecParam_Base`, creates the derived type, and closes the temporary
base handle. Inherited fields and methods remain accessible through the normal
runtime hierarchy. Derived traversal first invokes the generated base
traversal and then visits only newly declared `HPyField` members, preventing
both omissions and duplicate visits. Normal and Debug Mode tests cover
inherited initialization/method dispatch, public base/derived fields, exact
`isinstance` behavior, and collection of a cycle referenced by both layout
segments. Multiple inheritance, forward-declared bases, cross-module generated
bases, builtin bases, and metaclass selection remain explicit later gates.

`tests/ahpy/bootstrap_types.pyx` is compiled as a real Universal `.hpy0`
alongside the main and failed-init/retry modules. Normal and HPy Debug Mode
verify instance construction, exact type identity, module metadata, ordinary
method receiver/argument layouts, public and private field read/write/in-place
behavior, positional/keyword `__cinit__`/`__init__`, partial-construction
cleanup, public delete and readonly semantics,
GC tracking, collection of a self-cycle, cache identity, leak freedom,
forbidden-header scanning, and the undefined-symbol boundary. Compiler tests
require the pure HPy spellings and reject native fields outside the enabled
fixed-scalar set, builtin/extension-typed fields, weakrefs, special methods other
than the supported `__cinit__`, `__init__`, `__call__`, `__repr__`, `__str__`,
`__len__`, mapping, comparison, finalization, and
`__hash__`/`__bool__`/enabled-unary/conversion family, decorators, and bases outside the
strict same-module single-inheritance boundary.

HPy 0.9 provides no public code-object constructor or `CodeType` context
handle. Code-object caches and Python-function `__code__` introspection are
therefore blocked for this ABI rather than implemented through CPython APIs.

HPy 0.9's public `HPySlot_Slot` enum also omits `HPy_tp_iter` and
`HPy_tp_iternext`. Pure-type `__iter__` and `__next__` therefore receive a
dedicated versioned diagnostic; the backend does not leak CPython
`Py_tp_iter`/`Py_tp_iternext` into Universal output.

The same slot-surface audit gives separate HPy 0.9 diagnostics to attribute
hooks (`__getattribute__`, `__getattr__`, `__setattr__`, `__delattr__`),
descriptor hooks (`__get__`, `__set__`, `__delete__`), and async protocol hooks
(`__await__`, `__aiter__`, `__anext__`). The public enum exposes no
`HPy_tp_getattro`/`setattro`, `HPy_tp_descr_get`/`set`, or await/aiter/anext
slots; CPython `Py_tp_*`/`Py_am_*` substitution is forbidden. User-written
extension properties remain supported through the independent public
`HPyDef_GET`/`SET`/`GETSET` surface.
