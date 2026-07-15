# Historical Cython/HPy backend audit

- Audit date: 2026-07-14
- Current Cython baseline: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
- Purpose: evidence and regression-test mining only

No historical backend branch is merged into aHPy. Each is retained under
`refs/ahpy-history/` so that individual ideas and failure cases can be studied
without treating an old branch as the implementation base.

## Cython PR #4490

References:

- GitHub: <https://github.com/cython/cython/pull/4490>
- Local ref: `refs/ahpy-history/cython-pr-4490`
- Base: `3e2f28a328afc729158f31f0ab5320802c4cc9f2`
- Head: `f69934f250970173982546ed14b57bb02afab2dc`
- Development dates: 2021-05-26 through 2022-02-07
- Unique commits: 177
- Difference from the 2026-07-13 Cython baseline: 177 commits on the historical
  side and 3,733 commits on the current side
- Patch size: 31 files, 3,338 additions, 742 deletions

The only new dedicated HPy runtime test was `tests/run/hpy_basic.py`. It tested
an HPy-decorated integer addition function and a normal C-API function. One
existing `builtin_abs.pyx` test received a small change. This is proof of a
vertical slice, not broad Cython compatibility.

Every PR and follow-up commit is recorded in
`cython-pr-4490-commits.tsv`. The classification is intentionally conservative:
"reusable" means the problem or test idea remains relevant, not that the patch
can be cherry-picked.

### Reusable concepts that require a new implementation

- A runtime API boundary for null checks, calls, conversions, globals, builders,
  errors, method definitions, and module setup.
- Hidden `HPyContext *` propagation only through Python-interacting functions.
- Distinct compiler types for local objects, long-lived storage, tuple builders,
  and list builders.
- Builder-shaped tuple/list generation with a no-op finalization path for the
  CPython backend when useful.
- Explicit load/store/close operations for long-lived handles.
- Using new-reference expressions rather than separate borrowed-reference plus
  incref sequences where HPy semantics demand it.
- Treating return statements and exception cleanup as ownership transitions.

### Rejected approaches

- A second general `HPyCCodeWriter`. It moved syntax-specific structure away
  from compiler nodes and was removed inside the experiment itself.
- Per-function `@cython.hpy` selection. ABI, module initialization, globals, and
  type layout are module-level decisions.
- A mutable process-global backend object. It is unsafe for concurrent or nested
  compilations and makes tests order-dependent.
- Shipping both full CPython and HPy user-code bodies behind preprocessor
  branches. aHPy emits only the selected backend and shares only operations with
  equivalent semantics.
- Dummy or empty implementations for unsupported behavior. aHPy emits a source
  diagnostic instead.
- Storing globals in `HPyField` values associated with `ctx->h_None`. Modern
  aHPy uses registered `HPyGlobal` values until a validated public module-state
  accessor is available.

### Obsolete implementation assumptions

- The branch targets HPy 0.0.3. HPy 0.9 changed module initialization, method
  signatures, calling conventions, Hybrid-ABI rules, and several public APIs.
- Current Cython has substantially expanded Limited API, opaque object,
  free-threading, module-state, and borrowed-reference avoidance paths.
- Cython compiler nodes and utility code have changed across more than 3,700
  upstream commits.
- Several HPy paths deliberately disabled caches, Cython functions, type slots,
  traceback generation, coroutine detection, or cleanup.

## `mattip:hpy-2` follow-up

- Local ref: `refs/ahpy-history/mattip-hpy-2`
- Head: `9dbe3991e0ecf9c38c1034f87b005e60e3bcc8c9`
- Additional commits after the original RFC line: 19 in the recorded ancestry
- Last development date: 2022-07-31

The follow-up updated the experiment to HPy 0.0.4, added braces for C++ `goto`
and initialization rules, and fixed several ownership/in-place-operation
issues. Its value is primarily a regression catalogue:

- C++ scopes must not let generated gotos cross initialized variables.
- Null-condition polarity must be tested at generated-code and runtime levels.
- `get_newref()` return values and temporary release must be exercised.
- In-place binary operations require their own runtime mappings.

It still predates HPy 0.9 and current Cython and is not a code base for aHPy.

## 2023-2024 DuToitSpies experiments

The later public work referenced from the original RFC is still available, but
under multiple branch names rather than `hpy_backend`:

| Branch | Local historical ref | Head | Unique commits from its base | Scope |
|---|---|---|---:|---|
| `hpy_initialisation` | `dutoit-initialisation` | `7ad4112a` | 9 | Blank Universal module initialization |
| `hpy_initial_example` | `dutoit-initial-example` | `a2ae9677` | 15 | Basic values and CPython regression |
| `hpy_backend_original` | `dutoit-backend-original` | `c014b4f9` | 335 | Functions, globals, containers, calls, types, benchmarks |
| `cclass_port` | `dutoit-cclass-port` | `be0a0301` | 345 | Adds early `cdef class` work |

The largest branch changes 43 files with 4,808 additions and 1,564 deletions.
It adds ten general HPy tests plus one basic `cdef class` test. The history is a
useful source of leak, segfault, context, temporary, global-load, C++, GraalPy,
and type-layout regression scenarios.

The commit messages also contain explicit warnings such as "temp fix", "works
sometimes", "almost running", legacy slots for doctests, and behavior dependent
on optimization level. Therefore the code must not be copied wholesale. Tests
and minimal reproductions are to be extracted one behavior at a time after the
new ownership/runtime architecture exists.

## Architecture constraints derived from maintainer review

1. Syntax nodes retain responsibility for the structure of generated code.
2. Runtime differences use a focused API service; code writers remain formatting
   and output tools.
3. Equivalent low-level operations may share helpers/macros, but HPy storage and
   lifetime distinctions stay explicit.
4. Generated-code duplication and output growth are measured.
5. Backend selection is explicit and module-wide.
6. Backend-neutral refactors are separated from HPy feature patches.
7. Ownership changes receive dedicated tests rather than relying on CPython
   reference-count behavior.

These constraints are normative in ADR 0001 and the root roadmap.
