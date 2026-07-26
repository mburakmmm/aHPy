# M3 generated bootstrap validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: strict bootstrap subset passes; M3 remains in progress

## Implemented subset

The `hpy-universal` backend now completes Cython parsing, semantic analysis,
and optimisation before selecting a dedicated Universal bootstrap emitter
through `RuntimeCodeGenerationKind`. The original emitter accepted simple module names
and undecorated module `def` functions with required untyped ordinary,
multiple, and positional-only arguments. Function bodies may use linear local
assignment/reassignment, discarded expressions, `pass`, final returns, and a
one-clause conditional early return. Implemented return expressions include `None`, a
boolean, a signed 64-bit integer, a finite float, a supported
Unicode/bytes literal, or an empty/fixed-size/nested list, tuple, or dictionary
composed from those implemented values. Unicode NUL and lone-surrogate forms are
diagnosed rather than truncated or encoded incorrectly.

It emits `hpy.h`, `HPyFunc_NOARGS`/`HPyFunc_O`/`HPyFunc_KEYWORDS` definitions, call-scoped
`HPyContext *ctx`,
owned context-constant duplication, `HPyLong_FromLongLong`,
`HPyFloat_FromDouble`, `HPyUnicode_FromString`,
`HPyBytes_FromStringAndSize`, `HPyListBuilder`/`HPyTupleBuilder` lifecycles,
`HPyDict_New`/`HPy_SetItem`, `HPyArg_ParseKeywords`/`HPyTracker_Close`, and
`HPy_IsTrue`, plus deterministic definition arrays,
`HPyModuleDef`, and `HPy_MODINIT`. Builder items are closed after non-stealing
`Set`; intermediate allocation failure cancels all live nested builders in
reverse order. Unsupported AST forms raise a source-positioned compiler error
and never enter CPython codegen.

## Qualified module-name follow-up

The backend now accepts dotted package-module names whose individual
components are C identifiers. It preserves the full name for runtime type and
metadata identity while passing only the final component to `HPy_MODINIT`, as
required by the Universal loader's exported `HPyInit_<leaf>` symbols. A real
`ahpy_package.qualified_module` build passes binary-boundary checks and imports
with the exact `__name__` in normal, HPy Trace, and HPy Debug modes. The same
fixture exports and calls valid Unicode module-function and extension-method
names; their Python spellings stay intact while only indexed private C-symbol
fragments use deterministic UTF-8 hex encoding. Unicode `cdef class` names
follow the same rule for generated type/helper symbols while their HPy type
spec name and module attribute retain the original spelling.

`HPy_GetItem` and UTF-8-name `HPy_GetAttr_s` reads are also enabled over the
implemented expression subset. Their owned operands are closed before a null
result propagates the runtime exception.

Linear bodies also support `HPy_SetItem`, `HPy_DelItem`, `HPy_SetAttr_s`, and
`HPy_DelAttr_s`. Each operation executes into a status temporary before its
owned operands close; negative status then propagates through the common
cleanup path. Success and missing/immutable-target failures run under Debug
Mode leak detection.

`HPy_Call` supports zero, one, or multiple positional values in the strict subset. A
bound-method expression first performs the ownership-checked attribute read.
Multiple values use a scoped HPy handle array. Callable and argument handles
are closed in reverse order before a null call result propagates the callable's
exception.

Explicit keyword and mixed calls append keyword values to the same handle
array, pass only the positional count as `nargs`, and pass a separately owned
tuple of names as `kwnames`. Both the name tuple and every value are closed
after `HPy_Call`; a raising keyword callable is exercised in Debug Mode.

## Validation

The focused compiler/model command currently passes 239 tests:

```console
python3 -m unittest \
    Cython.Compiler.Tests.TestHPyModuleWriter \
    Cython.Compiler.Tests.TestRuntimeAPI \
    Cython.Compiler.Tests.TestHandleModel
```

The real HPy gate is:

```console
.venv-hpy09/bin/python Tools/ahpy/test_generated_hpy.py
```

It generates C from `tests/ahpy/bootstrap_answer.pyx`, scans for forbidden
legacy headers, types, helpers, and reference-count operations, builds with
`HPY_ABI_UNIVERSAL` plus HPy's `forbid_python_h` include guard, and imports the
same `.hpy0` artifact normally and with `HPY=debug`. An `nm` audit rejects any
undefined CPython symbol import before execution. Scalar—including UTF-8
text and embedded-NUL bytes—empty sequence, fixed sequence, and nested sequence
and dictionary semantics pass in both modes, and
`hpy.debug.LeakDetector` reports no open handles.

The `HPyFunc_O` lane deliberately requires Python positional-only syntax so
that rejecting keyword calls matches the source signature. Its input handle is
borrowed; direct returns and each container insertion duplicate it before any
owned close operation.

Required ordinary/multiple arguments use `HPyFunc_KEYWORDS`. A Universal-only
pre-validation pass rejects unknown keywords and positional/keyword duplicates
that HPy 0.9's parser does not itself reject. Parsed `O` handles remain tracker
owned and the tracker closes after the result is materialized but before return.

The same pre-validation rejects excessive positional arguments, including
positional values crossing the first keyword-only parameter. Required
keyword-only arguments remain required `O` entries and therefore fail parsing
when absent; success, missing, and positional-misuse cases run in Debug Mode.

Linear locals and conditional early returns fork compiler-visible lifetime
state. Both the taken and fall-through paths close prior locals exactly once;
the generated corpus exercises both paths under LeakDetector.

All-returning `if/elif/else` chains are also supported. Each branch is emitted
from an isolated copy of the incoming lifetime state and closes its own locals
and argument tracker. Since every branch terminates, no unsafe handle identity
is merged into an outer C scope.

The explicit exception lane supports a context-provided builtin exception as a
bare type or a call with zero, one, or multiple positional payload expressions
already supported by the backend. Safe single Unicode literals use
`HPyErr_SetString`; all other calls build an exact HPy argument tuple before
`HPyErr_SetObject`, preserving a tuple payload as one constructor argument
instead of unpacking it. NUL-bearing Unicode therefore avoids C-string
truncation, and lone-surrogate Unicode takes the same object path. Bare or
nullary `MemoryError` uses `HPyErr_NoMemory` and retains its exact empty `args`
tuple. Every path closes evaluated payloads, the temporary argument tuple, live
locals, and the argument tracker before returning `HPy_NULL`; a failing payload
expression retains its original exception. Empty, bare, one- and two-argument
parity, list identity, tuple nesting, NUL/lone-surrogate text, exact
`MemoryError`, evaluation failure, and leak cleanup pass normal, trace, and
Debug execution.

Dynamically evaluated exception instances and subclasses use only public
`HPy_TypeCheck`, `HPy_Type`, `HPyType_IsSubtype`, `h_BaseException`, and
`h_TypeType`. Instance raises retain the exact object; class raises normalize
through an empty argument tuple; positional and keyword constructor calls raise
their resulting instance. Invalid objects/classes receive Python's
`exceptions must derive from BaseException` `TypeError`, while constructor
failures remain active. All of these cases pass normal, trace, and Debug leak
gates.

The first handler slice uses only public HPy 0.9 current-error operations. A
terminal `try` may contain linear assignments, expressions, deletions, and
passes before its final return or explicit raise, then match direct builtin
exceptions, a tuple-normalized group of builtin exceptions, multiple clauses,
or a final bare clause. An internal failure label checkpoints handles,
builders, and argument trackers that existed before the try; each failure edge
closes only intermediates created in the protected body. A matched clause
clears the current error and returns a side-effect-free literal, while an
unmatched error retains its identity and propagates through the ordinary
function cleanup. Callable success, ValueError/TypeError/default matching,
explicit raise, container return, a local allocated before a failing call,
unmatched ZeroDivisionError, and leak cleanup pass normal, trace, and Debug
execution. HPy 0.9 exposes no public exception
type/value/traceback fetch/restore API, so observable handler bodies,
`except as`, reraise, traceback/cause/chaining, `else`/`finally`, and nesting
remain rejected rather than emulated with CPython state.

Python-object addition, subtraction, multiplication, true/floor division,
remainder, shifts, bitwise operations, and power emit their corresponding HPy
number APIs. Both owned operands close after each call; null results preserve
the runtime exception. Power passes the context's borrowed `None` constant as
HPy 0.9's required third argument. Numeric success, Unicode concatenation,
zero division, and mixed-type failures run under Debug Mode.

Unary plus, minus, and invert emit `HPy_Positive`, `HPy_Negative`, and
`HPy_Invert`. Their owned input closes before the checked result propagates;
success and protocol failure run under Debug Mode.

Boolean `and` and `or` evaluate the left operand once, call `HPy_IsTrue`, and
evaluate the right operand only on the required branch. The selected object is
returned as an owned handle without changing Python identity. Boolean `not`
duplicates the inverse context boolean after checking the truth status. Taken,
short-circuited, and raising truth/RHS paths all run under Debug Mode.

Cascaded comparisons retain owned result and middle-operand slots across
branches. Each middle operand is evaluated once, later comparisons are skipped
after a falsey result, and the actual falsey comparison object—not a coerced
boolean—is preserved. Rich, identity, and membership links can be mixed;
raising truth and final-comparison paths run under Debug Mode.

Regular and in-place matrix multiplication use `HPy_MatrixMultiply` and
`HPy_InPlaceMatrixMultiply`; the remaining augmented number operators map to
their corresponding public HPy APIs. Power passes `ctx->h_None` as its required
third argument. Cython's normalized in-place AST is honored: `LetNode` bindings
keep attribute receivers and item bases/keys alive exactly once, while the
result is assigned back through HPy. Local, attribute, item, mutable-identity,
evaluation-order, arithmetic failure, and setter failure cases run under Debug
Mode.

Continuing and nested conditionals promote every loop/branch-carried local to a
stable owned HPy slot before control splits. Newly introduced locals must be
assigned on every path; otherwise compilation fails with a source-positioned
diagnostic. Conditional expressions use the same convergence rule while
evaluating only their selected operand.

`while` loops retain stable locals across iterations and distinguish normal
completion from `break` so `while...else` follows Python semantics. `continue`,
truth-protocol failures, and raising body expressions run under Debug Mode.

HPy 0.9 exposes no public generic `GetIter`/`IterNext` operations. The verified
iteration slice therefore handles fixed non-empty list/tuple literals through
`HPy_Length` and `HPy_GetItem_i`; target handles, break/continue/else, and
comparison failures are covered. Other iterable shapes fail compilation with
an explicit HPy-version diagnostic instead of using private context fields.

Slice objects are constructed by calling the public `ctx->h_SliceType` with
three owned arguments. The resulting handle flows through the same
`HPy_GetItem`, `HPy_SetItem`, and `HPy_DelItem` paths as ordinary keys. Reads,
writes, deletes, in-place mutation, bound evaluation order, and protocol
failures run under Debug Mode. HPy 0.9 provides no public set constructor/add
operation or SetType context constant, so set literals receive an actionable
compile-time diagnostic rather than a CPython or private-context fallback.

The six ordering/equality operators emit `HPy_RichCompare` with the matching
`HPy_LT` through `HPy_GE` opcode. The owned boolean result and both operands
follow the same checked cleanup discipline; equality and ordering cases run in
normal and Debug Mode.

Identity comparisons use `HPy_Is` rather than comparing handle
representations. Their integer result selects `ctx->h_True` or `ctx->h_False`,
which is duplicated into an owned result before return.

Membership comparisons use `HPy_Contains`. The integer status is checked
before selecting and duplicating a context boolean, so protocol errors remain
active exceptions; both operands close on success and failure. `in` and
`not in` successes plus a non-container failure run under Debug Mode.

Missing-key and missing-attribute cases are executed while Debug Mode leak
detection is active, proving that exception returns do not retain operand
handles.

The same Debug Mode lane executes a callable that raises, covering cleanup for
both callable and positional-argument owned temporaries.

This record does not claim the complete M3 function, value, exception,
container, import, or cross-interpreter surface.

Module execution, registered globals, imports, builtins, retry, concurrency,
and subinterpreter evidence now live in the separate
`m4-module-state-validation.md` record.
