# HPy handle storage and ownership model

Universal HPy handles are not pointer-like references that can be copied into
arbitrary C storage. The compiler therefore models storage, ownership, and
liveness separately before selecting generated C syntax. The initial model is
implemented in `Cython.Compiler.HandleModel` and deliberately has no dependency
on the C emitter.

This is the M2 semantic foundation, not a claim that HPy code generation is
enabled. Temporary allocation, control-flow merging, context propagation, and
generated cleanup are still gated work.

## Storage contracts

| Storage kind | C representation | Lifetime | Direct API use | Load result |
| --- | --- | --- | --- | --- |
| `LOCAL` | `HPy` | one call | yes | not applicable |
| `FIELD` | `HPyField` | object lifetime | no | owned local `HPy` |
| `GLOBAL` | `HPyGlobal` | module lifetime | no | owned local `HPy` |
| `CONTEXT_CONSTANT` | `HPy` supplied by `ctx` | one call | yes | not applicable |

`HPyField` and `HPyGlobal` are indirect storage and cannot be declared as local
values. A plain `HPy` cannot be persisted across calls. Field operations need
an owner object, and globals must be registered in the module definition; the
model records both requirements for later emitters.

## Ownership and state transitions

Every directly usable value is `OWNED`, `BORROWED_ARGUMENT`, or `IMMORTAL` and
starts in the `LIVE` state.

| Value | Use | Duplicate | Close | Move/owned return |
| --- | --- | --- | --- | --- |
| live owned | allowed | creates live owned value | becomes closed | becomes moved |
| live borrowed argument | allowed | creates live owned value | rejected | rejected; return duplicates |
| live context constant | allowed | creates live owned value | rejected | rejected; return duplicates |
| moved or closed | rejected | rejected | rejected | rejected |

Loading a field or global produces a new owned local handle. Storing a handle
in a field or global does not consume the input. At a control-flow exit the
tracker reports every owned value that remains live, while borrowed and
immortal values never create a close obligation.

These rules make double-close, use-after-move, borrowed close, invalid storage,
and leaked owned handles deterministic compiler-model errors. Later M2 slices
will attach these facts to runtime-operation results, Cython temporaries, and
all generated early-exit paths.

## Runtime-operation contracts

The M1 Runtime API handle surface has an exhaustive semantic operation enum.
Its registry follows two public HPy invariants: a returned handle is an owned
local that the caller must close or return, and a handle argument is borrowed
and never stolen. `CLOSE` is the sole explicit consuming argument operation.

The registry additionally records builder creation and terminal build/cancel
operations. A completeness assertion prevents a newly declared operation from
silently lacking ownership metadata. The state tracker can apply a contract to
concrete compiler value names, validating all input states, performing an
explicit close transition, and declaring each handle result as owned local
storage.

### Direct borrowed operands

An owned materialization is not required merely to pass a value to an HPy API
whose argument contract is borrowed. The Universal emitter may reuse a direct
live `NameNode` handle only when that name resolves to a call-scoped borrowed
argument or a live owned local. Deleted stable slots receive the normal
`UnboundLocalError` guard first. Globals, builtins, closure fields, extension
fields, and arbitrary expressions still materialize owned handles.

The enabled sites are `HPy_GetAttr_s` receivers, zero-argument `HPy_Call`
callables, binary-operation operands, and fixed list/tuple builder items. A
left binary operand remains borrowed only when the right operand is also a
direct name. An arbitrary right expression may rebind or delete the left local,
so that case duplicates the already-evaluated left value before evaluating the
right. A direct right name may remain borrowed after a non-name left expression
has completed. This preserves Python's left-to-right evaluation and value
lifetime rules.

The API call or builder-set operation cannot outlive the source handle;
ownership remains with the argument frame/tracker or local lifetime, and the
ordinary failure epilogue retains its cleanup obligation. The borrowed handle
is never closed or returned directly. Emitter state tests, Debug Mode, Trace
Mode, and allocation/API fault injection enforce this boundary.

Extension-field `AsStruct`, load, and store operations apply a narrower rule:
the owner may be reused directly only when it is an incoming borrowed argument,
whose caller-owned lifetime spans the complete call. An owned local owner is
materialized because a side-effectful store RHS could rebind and close that
local after receiver evaluation. Direct Name field values may remain borrowed
for `HPyField_Store`. Extension type/module owners are loaded lazily at the
first constant, default, global, builtin, or closure access; field-only methods
never create them. Branch lifetime snapshots include these lazy owner names so
a handle declared inside one branch cannot leak into another branch's C code.

## Temporary integration

`FunctionState` has a dedicated HPy temporary path layered over its existing C
slot allocator. Allocating a handle temporary begins a new logical handle
lifetime. Closing or moving that handle is required before an owned slot can be
released, and reusing the same C variable creates a new generation rather than
reviving the old handle identity. Borrowed temporaries may be released without
closing.

Function exit validation reports live owned HPy temporaries before the existing
generic temporary guard runs. The path is opt-in, so CPython temporary behavior
and generated output remain unchanged.

The base expression lifecycle now selects this path through runtime semantics:
Python expression temporaries are owned, normal disposal closes them, and an
assignment that absorbs the result moves them. Releasing the compiler temporary
then verifies the terminal state. Borrowed expression temporaries are rejected
instead of silently skipping cleanup. Emptying an absorbed result is also a
runtime operation, preserving CPython's `0` spelling while HPy uses `HPy_NULL`.
Generic coercion contracts are explicit: converting a native value to Python
produces an owned result; converting from Python borrows the source; and
forcing a Python value into a new temporary duplicates it into an independently
owned handle. Feature-specific coercions remain owned by their later support
milestones.

Handle-aware Python temporaries use a dedicated compiler C storage type whose
Universal declaration is `HPy` and whose null value is `HPy_NULL`; they are not
declared as `PyObject *`. Runtime-owned non-handle resources use exact opaque C
types such as `HPyListBuilder` and `HPyTupleBuilder`.

Builders have their own live, built, and cancelled states. A builder cannot be
released or reused until `Build` or `Cancel` reaches a terminal state. The
separate-builder sequence emitter allocates the opaque builder, emits
`New -> Set* -> Build`, records that HPy `Set` never steals item handles, and
then releases the compiler temp. The strict Universal bootstrap emitter now
uses this model for empty, fixed-size, and nested list/tuple literals. It
closes each owned item after `Set` and emits reverse-order `Cancel` operations
for all live nested builders when an item allocation fails. Python-object
repetition remains explicitly gated rather than falling back to CPython
operators.

## Control-flow planning

Handle state can be forked for compiler control-flow edges. Cleanup plans cover
normal, return, break, continue, goto, and exception exits and close live owned
handles in reverse acquisition order while allowing an explicit return result
to be preserved and moved. Applying a plan changes those values to closed.

Merging branches is deliberately strict: storage declarations, value sets,
ownership, and terminal states must agree. A live value on one edge and a
closed or moved value on another is rejected with a request for matching edge
cleanup. This model is ready for emitter integration, but generated labels and
cleanup blocks are not yet connected and remain an unchecked M2 item.

## Global-load boundary

The code writer owns the sole compiler path for runtime-global loads. CPython
keeps its borrowed `PyObject *` expression. HPy assigns `HPyGlobal_Load` to a
new owned handle temporary, checks it with `HPy_IsNull`, and disposes it through
a null-guarded `HPy_Close` before releasing the compiler temp. A second disposal
is rejected by the state model.

A static compiler test prevents other emitter modules from calling
`global_load` directly. M4 will route generated builtin, type, string, tuple,
code-object, and user-global caches through this boundary; until then the HPy
backend remains gated and no untracked HPy global load is emitted.

Authoritative references verified on 2026-07-14:

- <https://docs.hpyproject.org/en/latest/api.html#handles>
- <https://docs.hpyproject.org/en/latest/api-reference/builder.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-field.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-global.html>
