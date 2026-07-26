# aHPy implementation roadmap

This file is the normative, dependency-ordered implementation checklist for
the aHPy backend. A task is complete only when its implementation, tests,
documentation, and exit gate are all complete. Later phases must not weaken an
earlier phase's exit gate.

## Project-wide rules

- [ ] Preserve the existing CPython backend unless a change is separately
      reviewed and covered by a regression test.
- [ ] Never silently fall back from `hpy-universal` to the CPython or HPy
      Hybrid ABI.
- [ ] Reject unsupported Universal-ABI constructs with an actionable source
      diagnostic.
- [ ] Keep syntax-specific code generation in compiler nodes; isolate runtime
      API differences behind a typed runtime API rather than a second general
      code writer.
- [ ] Treat handle storage, ownership, lifetime, and state as compiler-visible
      properties.
- [ ] Require a test for every fixed leak, invalid handle use, crash, ABI
      violation, or backend regression.
- [ ] Run HPy Debug Mode for every executable Universal-ABI test.
- [ ] Keep changes upstreamable: neutral refactors first, HPy behavior second,
      and no monolithic backend pull request.
- [ ] Update this checklist and the support matrix in the same change whenever
      project scope changes.

## M0 - Repository, scope, and evidence baseline

### Repository baseline

- [x] Attach the empty repository to the official Cython upstream.
- [x] Base development on Cython commit
      `b99cb0e3b5425e11414cadd24168a6cc850e8000` (2026-07-13).
- [x] Create the `codex/ahpy-bootstrap` development branch.
- [x] Add the complete dependency-ordered implementation checklist.
- [x] Add the initial scope, architecture, version-policy, and support-matrix
      documents.
- [x] Add `https://github.com/mburakmmm/aHPy.git` as `origin`, publish the
      upstream Cython baseline as `main`, and push the
      `codex/ahpy-bootstrap` development branch through an authorized account.
- [x] Decide and document the release branch and backport policy.
- [x] Decide and document the aHPy version format relative to Cython versions.
- [x] Add a project changelog and release-note fragment policy.
- [x] Confirm that Apache-2.0 is used for aHPy changes and preserve all Cython
      and third-party copyright notices.

### Historical HPy backend audit

- [x] Fetch Cython PR #4490 into a local historical reference.
- [x] Record its base/head commits, changed files, and test coverage.
- [x] Classify each commit as reusable concept, reusable test, obsolete HPy API,
      obsolete Cython architecture, or rejected approach.
- [x] Audit the follow-up `mattip:hpy-2` work for HPy 0.0.4 and C++ changes.
- [x] Search for all later public Cython/HPy experiments and record their state.
- [x] Convert maintainer feedback from PR #4490 into architecture constraints.
- [x] Do not copy old implementation code until its HPy 0.9 and current Cython
      compatibility is demonstrated by a focused test.

### Current Cython dependency inventory

- [x] Generate a machine-readable inventory of Python C-API calls in
      `Cython/Compiler` and `Cython/Utility`.
- [x] Classify each operation as backend-independent, directly mappable to HPy,
      structurally different in HPy, unsupported by HPy, or legacy-only.
- [x] Inventory existing Limited API, opaque-object, module-state,
      subinterpreter, and borrowed-reference avoidance paths.
- [x] Inventory all Python object storage sites: locals, temporaries, C globals,
      module state, extension fields, closures, generators, and freelists.
- [x] Inventory all function signatures that interact with Python objects and
      therefore require `HPyContext` propagation.
- [x] Inventory all generated type/module definitions and initialization paths.
- [x] Produce a baseline count of Cython tests by feature family.
- [x] Select a small conformance corpus covering success, exception, cleanup,
      and import paths.

### M0 exit gate

- [x] Architecture decisions are recorded and non-contradictory.
- [x] Every C-API dependency in the initial corpus has an owner and category.
- [x] The initial supported/unsupported boundary is explicit.
- [x] The CPython baseline test subset passes before backend refactoring begins.

## M1 - Backend-neutral runtime API seam

### Compiler API

- [x] Define a typed `RuntimeAPI` protocol with capability discovery.
- [x] Define runtime operation groups for objects, calls, containers,
      conversions, exceptions, globals, modules, and types.
- [x] Implement a `CPythonRuntimeAPI` that preserves current output semantics.
- [x] Make backend selection a compiler/build option, not a function decorator.
- [x] Add accepted values `cpython`, `hpy-universal`, and test-only
      `hpy-cpython`; reserve `hpy-hybrid` without enabling it.
- [x] Reject unknown backend names at option parsing time.
- [x] Carry the selected backend through compilation contexts without mutable
      process-global backend state.
- [x] Add a capability error type with source position, missing capability,
      reason, and migration guidance.

### Neutral refactoring

- [x] Route null checks, duplication, close/clear, and error checks through the
      runtime API.
  - [x] Route direct lifecycle and error-state emission in the general code
        generator (`Code`, `ModuleNode`, `Nodes`, `ExprNodes`, and `Buffer`).
  - [x] Preserve byte-identical CPython output against the clean upstream base
        for all five aHPy oracle modules after the routing change.
  - [x] Keep the CPython-specific type lifecycle spellings in `PyrexTypes.py`
        behind the runtime API/type boundary.
  - [x] Pass the context-local runtime API into type conversion error
        conditions instead of spelling `PyErr_Occurred` inside type logic.
- [x] Route calls and argument layout through the runtime API.
  - [x] Model tuple/dict, no-argument, one-argument, and method calls explicitly.
  - [x] Model array calls with immutable keyword-layout and receiver metadata.
  - [x] Preserve CPython fast-call/vectorcall utility selection for all five
        valid layout combinations and reject invalid combinations.
  - [x] Record the HPy `HPy_Call`, `HPy_CallMethod`, and `HPy_CallTupleDict`
        argument-layout contracts that the HPy implementation must satisfy.
- [x] Route tuple/list/dict construction through builder-capable abstractions.
  - [x] Represent list and tuple construction kind explicitly instead of
        selecting C-API names in expression/statement nodes.
  - [x] Model whether the runtime uses a distinct builder/result type, whether
        item insertion steals a reference, and where allocation failure is
        reported.
  - [x] Model builder `New`, `Set`, `Build`, and `Cancel` operations for both
        CPython and HPy contracts.
  - [x] Route fixed-size, empty, array-based, and packed sequence construction.
  - [x] Route empty/presized dict creation, item/string-item insertion, and
        direct dict copies used by general code-generation nodes.
  - [x] Record that HPy has tuple-from-array and tuple-pack helpers but requires
        `HPyListBuilder` for the corresponding list cases.
  - [x] Add a static regression test that rejects direct fixed-size container
        construction bypasses in the main compiler code emitters.
  - [x] Preserve byte-identical CPython output for all five oracle modules.
- [x] Route primitive-to-object and object-to-primitive conversions through the
      runtime API.
  - [x] Represent conversion direction and semantic kind for booleans, signed
        and unsigned integers, floats, complex values, Unicode code points,
        C strings, and custom conversions.
  - [x] Carry the native C type and selected helper in an immutable conversion
        descriptor.
  - [x] Route the central `CType` to/from-Python conversion emitters through the
        context-local runtime API while retaining specialized array/memoryview
        paths for their later feature milestones.
  - [x] Reject HPy conversion emission explicitly until M2 supplies handle and
        context storage instead of falling back to CPython helpers.
  - [x] Preserve clean-tree CPython output and validate integer, typedef,
        boolean, float, complex, C-function, memoryview-wrapper, and
        subinterpreter conversion paths under C and C++.
- [x] Route exception creation, matching, fetching, restoring, chaining, and
      formatting through the runtime API.
  - [x] Route set-string, set-object, set-none, formatting, clear, out-of-memory,
        current-error matching, and current-exception-type operations.
  - [x] Route fetch/restore, raise/reraise, normalize/get, save/reset, and swap
        operations that use CPython's type/value/traceback exception triple.
  - [x] Preserve the distinction between current-error matching and matching a
        supplied exception object.
  - [x] Map the public HPy core operations exactly and reject CPython-style
        exception-triple operations because HPy exposes no public equivalent.
  - [x] Add a static regression test that rejects core exception-operation
        bypasses in the main compiler code emitters.
  - [x] Keep feature-specific argument, buffer, unpacking, and C++ translation
        helpers visible for their owning milestones instead of misclassifying
        them as core exception operations.
  - [x] Preserve clean-tree CPython output for all five oracle modules and pass
        the C/C++ aHPy conformance selector.
- [x] Route global/module operation selection through the runtime API.
  - [x] Model module-global, builtin, and class-namespace lookup as distinct
        immutable operations.
  - [x] Route all principal compiler uses of `__Pyx_GetModuleGlobalName`,
        `__Pyx_GetBuiltinName`, and `__Pyx_GetNameInClass` through the
        context-local runtime API.
  - [x] Reject HPy dynamic-name emission until registered global storage,
        module execution state, context propagation, and owned local handles
        exist.
  - [x] Add a static bypass guard and preserve byte-identical CPython output for
        the five oracle modules; pass the 38-case C/C++ conformance selector.
  - [x] Define registered long-lived global storage metadata, including module
        registration, per-interpreter isolation, load ownership, and close
        requirements.
  - [x] Define module-object hooks for import, handle-name and UTF-8-name
        attribute publication, manual creation, module-dict access, module
        registry access, and module-registry lookup.
  - [x] Map `HPyImport_ImportModule`, `HPy_SetAttr`, and `HPy_SetAttr_s` only
        where public HPy semantics match; reject manual creation and borrowed
        module/registry dictionary access with an actionable capability error.
  - [x] Define immutable module-definition metadata that records CPython's
        configurable initialization and HPy's mandatory multi-phase,
        definition-returning, context-free init plus context-bearing exec slot.
  - [x] Route the principal compiler module-object emitters through the hooks
        and add a static bypass guard while preserving all five clean-tree
        CPython outputs and the 38-case C/C++ conformance selector.
  - [x] Assign ownership-tracked loads from registered long-lived storage to M2
        and concrete builtin/constant/type/string/code-object cache migration
        to M4, avoiding an M1-to-M2 dependency cycle.
  - [x] Assign concrete `HPyModuleDef`, `HPy_MODINIT`, `HPy_mod_exec`,
        traversal, clear, teardown, and failed-init emission to M3/M4/M5 after
        the handle model exists; do not emulate these with CPython hooks.
- [x] Route method, slot, type, and module definitions through explicit hooks.
  - [x] Represent no-argument, one-argument, varargs-keywords, and
        fastcall-keywords method layouts as runtime-neutral signatures.
  - [x] Route CPython method table declarations, entries, terminators, and
        standalone definitions while defining HPy's `HPyDef_METH` plus
        `HPyDef *` array contract.
  - [x] Define CPython slot-spec versus pure-HPy definition-array type models,
        including builtin-shape and object-header requirements.
  - [x] Route type-slot entries, type definition arrays, and type specification
        declarations; map only verified HPy slots and reject unsupported slots.
  - [x] Route module slot arrays, module definition declarations, and CPython
        definition initialization while rejecting expression-style HPy init.
  - [x] Keep actual HPy wrapper signatures and complete module/type definition
        bodies assigned to M3/M5, after M2 supplies handle ownership.
- [x] Separate C-language differences from Python-runtime API differences.
  - [x] Add a static test that prohibits C/C++ output-language selection inside
        `RuntimeAPI.py`; language selection remains in the existing compiler
        configuration and writers.
- [x] Avoid backend conditionals scattered through unrelated compiler code.
  - [x] Add a static test that confines backend names and constants to runtime
        option/context setup and `RuntimeAPI.py`.

### M1 tests and exit gate

- [x] Add unit tests for backend option parsing and capability diagnostics.
- [x] Add golden-output tests for representative CPython modules.
- [x] Run the complete normal Cython test suite.
- [x] Demonstrate no intentional CPython runtime or performance regression.
  - [x] Preserve byte-identical generated C for all five oracle modules, which
        makes their compiled runtime paths identical to the upstream base.
  - [x] Alternate 12 current/base compiler invocations: current median 0.222 s
        versus upstream 0.234 s (0.952 ratio), showing no compiler-time
        regression in the representative module.
- [x] Document every unavoidable generated-code change (none in the initial
      Runtime API seam; explicit/default CPython output is byte-identical).

## M2 - HPy context, handle model, and cleanup correctness

### Compiler-visible model

- [x] Add storage kinds `LOCAL`, `FIELD`, `GLOBAL`, and `CONTEXT_CONSTANT`.
- [x] Add ownership kinds `OWNED`, `BORROWED_ARGUMENT`, and `IMMORTAL`.
- [x] Add handle states `LIVE`, `MOVED`, and `CLOSED` where statically useful.
- [x] Define ownership contracts for every HPy handle operation in the M1
      Runtime API surface and enforce registry completeness as it expands.
- [x] Define when an owned, borrowed, or immortal return requires move versus
      `HPy_Dup` in the compiler-visible state model.
- [x] Prevent local `HPyField` values and long-lived plain `HPy` storage in the
      compiler-visible declaration model.
- [x] Prevent double-close, use-after-move, and close of borrowed arguments in
      the compiler-visible state model.
- [x] Teach function temporary allocation, reuse, disposal, and exit validation
      about distinct HPy handle lifetimes and ownership.
- [x] Route base Python-expression temporary allocation, disposal, absorbed
      assignment, and empty-handle spelling through the handle-aware path.
- [x] Add distinct `HPy`/opaque-builder C storage types and enforce
      `New -> Set* -> Build|Cancel` builder lifecycles without stealing items.
- [x] Teach base expression-result temporaries and generic to/from-Python and
      to-temporary coercion contracts about HPy ownership.
- [x] Make the compiler's sole `HPyGlobal_Load` writer path allocate an
      ownership-tracked local handle, guard null cleanup, close it exactly once,
      and statically reject emitter bypasses. M4 connects actual global/cache
      sites to this path.
- [ ] Teach all return, break, continue, goto, and exception paths to clean up
      live owned handles exactly once.
  - [x] Teach strict linear local assignment/reassignment, discarded expression,
        final return, and one-clause conditional early-return paths to close
        live owned handles exactly once; loops and general branch merges remain.
  - [x] Teach all-returning `if/elif/else` branches to fork the incoming
        lifetime state and close locals/argument trackers independently.
  - [x] Teach `break`/`continue` to close body-iteration owned temps/builders
        against the loop-entry lifetime snapshot before transferring control.
  - [x] Teach continuing `while`/`for` iterations (including nested
        fors/comprehensions) to run the same body-iteration cleanup before
        restoring the loop-entry lifetime snapshot, so nested locals cannot
        leak under HPy Debug Mode.
  - [x] Teach return and raise inside continuing `while`/`for` bodies to close
        every remaining owned handle (including for-loop sequences) before
        function exit.
  - [x] Teach mixed terminating/continuing conditional branches to return/raise
        with full cleanup while continuing arms keep promoted stable locals.
- [x] Add emitter-independent cleanup plans, state forks, and strict branch
      merges for normal, return, break, continue, goto, and exception edges.

### HPyContext propagation

- [x] Add backend and compiler-visible call-scoped context contracts that
      distinguish Python-interacting functions from provably pure-C functions.
- [ ] Add hidden `HPyContext *ctx` parameters to Python-interacting generated
      functions.
  - [x] Emit the call-scoped context parameter in strict bootstrap
        `HPyFunc_NOARGS` implementations.
  - [x] Emit call-scoped context on every bootstrap Universal function/slot/
        property/`mod_exec` implementation that performs public HPy operations.
- [x] Avoid adding context to provably pure-C helpers.
  - [x] Keep bootstrap GC traverse helpers and other non-Python operations
        context-free; ContextPropagationModel rejects pure-C callers of
        context-requiring callees.
- [x] Propagate context through utility-code declarations and calls.
  - [x] Record that the Universal bootstrap emitter does not consume
        `Cython/Utility/*.c`; utility-code HPy ports remain a future M6/M7
        family gated separately rather than silently falling back to CPython
        utilities.
- [x] Keep callbacks, closures, generators, and public C APIs rejected until
      their context entry/ownership policies are explicitly defined.
- [x] Reject attempts to persist `HPyContext *` beyond its valid call lifetime.

### M2 tests and exit gate

- [x] Add a pinned HPy 0.9.0 handwritten Universal reference module and run it
      in normal and Debug Mode with explicit leak detection.
- [x] Unit-test ownership transitions independently of C compilation.
- [ ] Test nested expressions and all early-exit cleanup paths.
  - [x] Test nested fixed-size list/tuple expressions and generated
        allocation-failure cleanup with reverse-order builder cancellation.
- [ ] Test failures after each intermediate allocation/API call.
  - [x] Cover every intermediate scalar allocation in the strict fixed-size
        list/tuple bootstrap emitter, plus list-builder build, dictionary set,
        call, attribute-get, and item-get failure returns; remaining APIs stay
        open below.
- [ ] Run all executable cases under HPy Debug Mode.
- [ ] Run ASan, UBSan, and leak detection where supported.
- [ ] Exit with zero known leaks, double-closes, invalid handles, or borrowed
      argument closes in the initial corpus.

## M3 - Universal HPy module and function core

### Generated translation unit

- [x] Include `hpy.h` and prohibit `Python.h` in the strict Universal bootstrap
      lane.
- [x] Emit through the HPy build lane that defines `HPY_ABI_UNIVERSAL`, and
      compile with HPy's `forbid_python_h` include guard.
- [x] Emit `HPy_MODINIT` and an `HPyModuleDef`.
- [x] Support qualified package-module names: retain the full dotted name for
      runtime type/metadata identity and use only the final identifier in the
      `HPy_MODINIT` export symbol; import the built package module in normal,
      Trace, and Debug modes.
- [x] Emit `HPy_mod_exec` initialization where runtime setup is required.
- [ ] Generate HPy module-level method definitions and all declared signatures.
  - [x] Generate strict argument-free `HPyFunc_NOARGS` definitions.
  - [x] Preserve valid Unicode Python function/method names at the HPy boundary
        while encoding only their private generated C-symbol fragments; cover
        module functions and extension methods in normal, Trace, and Debug
        modes.
  - [x] Generate `HPyFunc_O` for exactly one untyped positional-only argument;
        model the incoming handle as borrowed and duplicate it for owned
        returns/container temporaries.
  - [x] Add ordinary one-argument, multiple-argument, positional-only, and
        keyword-capable signatures with tracked `HPyArg_ParseKeywords` parsing;
        compensate for HPy 0.9's missing duplicate/unknown-key validation.
- [x] Generate deterministic definition arrays and terminators.
- [x] Keep the implemented HPy module pieces in a valid compilation unit
      layout.
- [x] Select the bootstrap emitter through a typed code-generation-kind
      contract, independently of handle-ownership policy.
- [x] Reject invalid module-name components, unsupported module statements,
      function signatures, decorators, bodies, and return expressions outside
      the bootstrap subset at their source positions.

### Core Python semantics

- [x] Support `None`, booleans, integers, floats, complex numbers, strings, and
      bytes.
  - [x] Support owned `None` returns through `HPy_Dup` and signed 64-bit integer
        literals through `HPyLong_FromLongLong` in the bootstrap slice.
  - [x] Support booleans, finite float literals, NUL-free/lone-surrogate-free
        Unicode literals, and arbitrary byte literals through public HPy APIs;
        cover success, nested-builder allocation failure, and rejected literal
        boundaries.
  - [x] Add arbitrary-size integers through `ctx->h_LongType`, imaginary and
        complex literals through `ctx->h_ComplexType` plus HPy arithmetic,
        overflow infinities through `HPyFloat_FromDouble`, and NUL/lone-
        surrogate Unicode through length-aware bytes plus
        `HPyUnicode_FromEncodedObject(..., "surrogatepass")`.
- [ ] Support tuple and list builders, dictionaries, sets, and slices in the
      declared initial subset.
  - [x] Support empty, fixed-size, and nested list/tuple literals containing
        implemented bootstrap values through `HPyListBuilder` and
        `HPyTupleBuilder`, including item close, `Build`, and failure `Cancel`.
  - [x] Support empty, fixed-size, and nested dictionary literals over
        implemented values through `HPyDict_New`/`HPy_SetItem`, including
        allocation and insertion failure cleanup.
  - [ ] Add set literals when the selected public HPy API exposes set
        construction/add operations or a SetType constant; HPy 0.9 exposes
        neither and receives an actionable compile-time diagnostic.
  - [x] Add list/tuple multiplication with owned base/factor handles, public
        `HPy_Multiply`, failure cleanup, and normal/debug execution.
  - [x] Add starred list/tuple expansion by normalizing each source-order
        segment through public `ctx->h_ListType`/`ctx->h_TupleType` calls and
        concatenating owned segments with `HPy_Add`; cover generic iterables,
        multiplication, non-iterable failures, and normal/debug cleanup.
  - [x] Add Ellipsis through `ctx->h_Ellipsis` plus owned `HPy_Dup`.
  - [x] Add f-strings through owned `HPy_Str`/`HPy_Repr`/`HPy_ASCII`,
        `__format__` via `HPy_CallMethod`, and piece concatenation with
        `HPy_Add`, with normal/debug generated-oracle coverage.
  - [x] Add walrus (`:=`) for simple local and module-global names: evaluate
        RHS once, store, return owned `HPy_Dup`; promote walrus targets in
        conditionals/loops with ordinary assignments.
  - [x] Under Universal handle ownership, keep unspecified inferred locals as
        Python objects so assignments such as `x = len(y)` stay on the
        supported handle path instead of typed C locals.
  - [x] Add sequence unpacking (`a, b = seq`, starred/nested), parallel
        `a, b = 1, 2`, cascaded `a = b = x`, and `for a, b in [literal]:`
        through `HPy_Length`/`HPy_GetItem_i`/`HPyListBuilder` with
        ValueError length parity and ownership-safe failure cleanup.
  - [x] Add list/dict comprehensions over fixed list/tuple literals
        (nested fors, `if` filters, unpack targets) via `ListType()` +
        `HPy_CallMethod` `append` and `HPyDict_New`/`HPy_SetItem`; keep set
        comprehensions rejected on HPy 0.9.
  - [x] Extend sequence-index `for` loops and list/dict comprehensions to
        dynamic expressions (locals/parameters/calls returning sequences),
        including empty sequences and `else`; keep generator expressions and
        GetIter/IterNext loops rejected on HPy 0.9.
  - [ ] Add remaining unsupported ExprNodes behind their individual ownership
        tests.
- [x] Support attribute and item get/set/delete operations.
  - [x] Support owned attribute and item reads over implemented expressions,
        including success and exception cleanup under HPy Debug Mode.
  - [x] Support attribute/item assignment and deletion in linear statement
        bodies, including success and negative-status cleanup under Debug Mode.
  - [x] Add HPy in-place mutation for locals, attributes, and non-slice items,
        preserving one-time receiver/key evaluation and setter failure cleanup.
  - [x] Add slice construction through `ctx->h_SliceType` plus slice read,
        assignment, deletion, and in-place mutation with one-time bound
        evaluation.
- [ ] Support Python calls, positional arguments, keyword names, and methods.
  - [x] Support zero-argument, one-positional-argument, and bound-method calls
        over implemented expressions through `HPy_Call`, including runtime
        exception cleanup under Debug Mode.
  - [x] Support multiple positional arguments through a scoped owned-handle
        array passed to `HPy_Call`, with reverse-order cleanup.
  - [x] Add explicit keyword-name and mixed positional/keyword calls through
        HPy `args+nargs+kwnames`, including failure cleanup.
  - [x] Add starred positional arguments and duplicate-checked dynamic keyword
        mappings through public tuple/mapping normalization and
        `HPy_CallTupleDict`; cover generic mappings, non-mapping errors,
        duplicate errors, and normal/debug cleanup.
  - [x] Add direct method-call layout optimization through `HPy_CallMethod`
        with args[0] as receiver, owned UTF-8 method-name handles, positional
        and keyword layouts, and no bound-method GetAttr materialization.
- [x] Support comparisons, truth testing, arithmetic, and in-place operations.
  - [x] Support HPy truth testing for one-clause conditional early returns,
        including error cleanup and branch-local lifetime state restoration.
  - [x] Support multi-clause all-returning conditionals without merging
        branch-local handles into an outer scope.
  - [x] Support Python-object add/subtract/multiply, true/floor divide,
        remainder, shifts, bitwise operations, and power through the matching
        HPy number APIs, including operand cleanup and runtime failures.
  - [x] Support the six rich comparison operators through `HPy_RichCompare`
        with owned boolean results and operand cleanup.
  - [x] Support `is`/`is not` through `HPy_Is` and owned context-boolean
        duplication.
  - [x] Support `in`/`not in` through `HPy_Contains`, including negative-status
        exception propagation and operand cleanup.
  - [x] Support unary plus, minus, and invert through `HPy_Positive`,
        `HPy_Negative`, and `HPy_Invert`, including failure cleanup.
  - [x] Support value-preserving `and`/`or` short-circuiting and boolean `not`,
        including truth-protocol failures and branch ownership convergence.
  - [x] Support short-circuiting cascaded comparisons with one-time middle
        operand evaluation and falsey comparison-result preservation.
  - [x] Support regular and in-place matrix multiply plus all other public HPy
        in-place number operations, including three-argument power semantics.
- [ ] Support general structured control flow with lifetime-safe branch and
      loop merges.
  - [x] Support continuing and nested `if/elif/else` statements with stable
        local HPy slots, definite-assignment validation, and truth failures.
  - [x] Support value-producing conditional expressions with single-branch
        evaluation and a converged owned result slot.
  - [x] Support `while`, `break`, `continue`, and `while...else` with stable
        loop-carried locals and distinct normal/break completion paths.
  - [x] Add mixed terminating/continuing branches and return/raise from loops
        with ownership-safe cleanup under normal/Debug execution.
  - [x] Support `assert` / `assert cond, msg` through public
        `ctx->h_AssertionError` under `#ifndef CYTHON_WITHOUT_ASSERTIONS`,
        including truth failures and Debug Mode cleanup.
  - [x] Support counted `range` / `for-from` loops with untyped Python targets
        via `HPy_ssize_t` iteration and `HPyLong_FromSsize_t`.
- [ ] Support imports, module globals, builtins lookup, and constants.
  - [x] Emit absolute imports, `from` bindings, module assignments and
        overwrite, referenced function objects, and builtin calls through a
        real `HPy_mod_exec` plus interpreter-owned module attributes.
  - [x] Resolve function global reads dynamically through module attributes,
        then the module-owned builtins object, including external rebinding,
        positive builtin fallback, and exact missing-name `NameError` in the
        generated-module subset.
  - [x] Add function-level global assignment, in-place update, and deletion,
        including missing-delete `NameError`, normal/debug cleanup, and process
        teardown coverage.
  - [x] Add local/argument `del` through stable null slots with
        `UnboundLocalError` on later reads, multi-target `del a, b`,
        rebind-after-delete, conditional deletion, and Debug Mode cleanup.
  - [x] Support function-scope `locals()` / zero-arg `vars()` via
        `FuncLocalsExprNode` with null-slot exclusion, `HPy_Dup` failure
        propagation, and normal/Debug generated-oracle coverage; module-scope
        `locals()`/`globals()` use the owned module dictionary.
  - [x] Evaluate reads before module initialization at runtime instead of
        rejecting them at compile time; keep relative/star imports rejected.
  - [x] Add the remaining constant caches for `None`, booleans, integers, and
        floats through the same interpreter-owned `__pyx_hpy_const_*` module
        attributes used by Unicode/bytes/tuple literals, with identity-stable
        normal/Debug generated-oracle coverage.
- [ ] Support argument parsing, default values, keyword-only, and positional-only
      arguments for declared signatures.
  - [x] Support required untyped ordinary, multiple, and positional-only
        arguments; reject missing, duplicate, unknown, and positional-only
        keyword misuse with `TypeError`; default handling is covered below.
  - [x] Support required keyword-only arguments and reject excessive positional
        arguments before HPy 0.9 parsing.
  - [x] Add interpreter-owned storage and optional parsing for side-effect-free
        scalar/list/tuple/dict defaults, including positional-only and
        keyword-only use, mutable-default identity, required-argument failures,
        tracker cleanup, and normal/debug execution.
  - [x] Add source-ordered evaluation for effectful defaults: type-method
        defaults evaluate before type publication; module-function defaults
        evaluate after imports/assignments; unsupported expressions keep their
        source diagnostics.
  - [ ] Keep Python-function `__defaults__`/`__kwdefaults__` introspection
        blocked while HPy module methods are not Python function objects.
- [ ] Support exception raising, matching, propagation, chaining, formatting,
      and cleanup.
  - [x] Support `raise BuiltinError("literal")` for HPy 0.9 context-provided
        exception classes, closing locals and argument trackers before error
        return.
  - [x] Extend context-provided builtin exceptions to bare types and calls with
        zero, one, or multiple arbitrary supported positional payloads without
        tuple unpacking; preserve source-order evaluation failures, route
        NUL/lone-surrogate Unicode through `HPyErr_SetObject`, use
        `HPyErr_NoMemory` for exact argless `MemoryError`, and pass
        normal/trace/debug cleanup gates.
  - [x] Support dynamically evaluated exception instances, exception subclasses,
        positional/keyword constructor calls, exact instance identity, invalid-
        operand diagnostics, and constructor-failure propagation using only
        public HPy type/subtype operations.
  - [x] Add the HPy 0.9 current-error-only terminal handler slice: a linear
        try body ending in return/raise, direct builtin or tuple-normalized
        builtin matching, multiple/default clauses, literal-return handlers,
        internal failure labels, checkpointed handle/builder/tracker cleanup,
        unmatched propagation, and normal/Trace/Debug execution.
  - [ ] Add general handler bodies, `except as`, reraise, traceback, cause,
        chaining, `else`/`finally`, nested handlers, and complete observable
        handler-state semantics after a public exception-state design exists.
- [ ] Support iteration for the declared builtin containers.
  - [x] Support fixed, non-empty list/tuple literal iteration through
        `HPy_Length` and `HPy_GetItem_i`, including `break`, `continue`, `else`,
        comparison failures, and target ownership.
  - [x] Support dynamic sequence-index `for` loops and list/dict comps over
        any owned expression whose value implements `HPy_Length`/
        `HPy_GetItem_i` (including empty sequences); reject generator
        expressions with an actionable HPy 0.9 iterator-protocol diagnostic.
  - [x] Support counted `for i in range(...)` / `for i from ...` loops (and
        matching list/dict comps) via `HPy_ssize_t` C iteration plus
        `HPyLong_FromSsize_t` Python targets; reject typed C loop targets.
  - [ ] Add generic iterator-protocol loops when the selected public HPy API
        provides `GetIter`/`IterNext`; HPy 0.9 has no such public operations.

### Universal ABI enforcement

- [x] Add a generated-source scanner for forbidden legacy headers, types,
      conversion helpers, and API symbols in the executable bootstrap corpus.
- [x] Add an `nm` undefined-symbol audit that rejects CPython imports from the
      generated Universal `.hpy0` artifact.
- [x] Reject `cpython.*` cimports in Universal mode with a source-positioned
      public-HPy migration diagnostic.
- [x] Reject direct `PyObject *`/`cpy_PyObject *` declarations and
      `HPy_FromPyObject`/`HPy_AsPyObject` legacy conversions in the strict
      compatibility preflight, with comment/string masking, exact source
      positions, stable migration action IDs, tests, and no ABI fallback.
- [x] Permit an audited Python-independent external-C subset: concrete safe
      headers, direct standard scalar parameters/results, checked HPy-to-C
      narrowing, source-ordered argument evaluation, and no Python exception
      contract; reject `Python.h`, inline code, external typedefs, pointers,
      aggregates, variables, variadics, and optional parameters.
- [x] Never compile a rejected source by changing ABI mode automatically;
      strict compiler negatives require no generated output, scanner negatives
      never retry another backend, and ADR 0002 makes this a release invariant.

### M3 exit gate

- [ ] Compile and import the initial corpus as `.hpy0` modules.
  - [x] Compile and import the generated bootstrap module as `.hpy0`, then run
        its semantics under normal and HPy Debug Mode with explicit leak
        detection.
  - [ ] Expand the generated corpus to the full M3 semantic surface.
- [ ] Load the same built binary on supported CPython, PyPy, and GraalPy lanes.
- [ ] Pass Debug Mode, forbidden-symbol, sanitizer, and semantic parity tests.

## M4 - Globals, module state, and interpreter isolation

- [ ] Register only semantically safe generated `HPyGlobal` caches in
      `HPyModuleDef.globals`; HPy 0.9 process-shared storage failed the mutable
      subinterpreter isolation test, so the current emitter generates none.
- [x] Replace the historical `HPyField`-owned-by-None global workaround.
- [x] Define initialization, load, overwrite, external rebinding, and
      interpreter-exit semantics through interpreter-owned module attributes.
- [ ] Port builtin, type, string, tuple, default-argument, and code-object caches.
  - [x] Keep the builtins module as an interpreter-owned private module value
        while resolving builtin names dynamically for Python rebinding parity.
  - [x] Deduplicate function Unicode, bytes, and recursively immutable tuple
        literals into interpreter-owned private module attributes; initialize
        them in `HPy_mod_exec`, return owned call-scoped loads, and cover
        identity, failure cleanup, Debug Mode, and reserved-name collisions.
  - [x] Store the supported default-argument subset in per-definition,
        interpreter-owned module attributes with mutable identity preserved.
  - [x] Create pure HPy extension types from
        `HPyType_Spec` and store each interpreter's type object in its module
        namespace; cover construction, identity, generic object-field GC,
        normal/debug cleanup, and forbidden-symbol scanning.
  - [ ] Port richer type caches as more field/method/slot families become
        executable and extend default storage to effectful expressions; the
        initial same-module inheritance slice loads its base from the current
        interpreter's module-owned type attribute.
  - [ ] Keep code-object caches blocked on HPy 0.9, which exposes neither a
        public code-object constructor nor a `CodeType` context handle; do not
        emulate them with CPython APIs.
- [x] Port referenced builtin lookup plus Unicode, bytes, and immutable tuple
      caches plus the supported default-argument subset through module-owned
      values; type, code-object, and effectful-default caches remain.
- [x] Ensure failed module initialization leaves no live handles and removes
      published methods before returning, breaking the failed module/function
      cycle that otherwise exposes HPy 0.9 loader-owned `PyModuleDef` lifetime
      corruption during later GC.
- [x] Support module re-import and failed-import retry behavior in the
      validated HPy 0.9 normal lane after asserting `sys.modules` removal and
      collecting the failed loader state; generated-method failure cleanup
      also makes the failed Debug Mode path and later process teardown safe.
- [x] Document immediate failed-import retry without an explicit GC boundary as
      an HPy 0.9 / loader lifetime upstream gap (intermittent `SystemError`
      after `sys.modules` removal); retain the explicit `gc.collect()` gate in
      the generated oracle. Closing true GC-free retry remains U0-blocked until
      a public HPy error/module-state API or upstream loader fix exists.
- [x] Test independent state in multiple subinterpreters.
- [x] Test concurrent initialization and module-owned global access under the
      interpreter import lock.
- [x] Track HPy module-state API evolution and migrate only to a stable public
      accessor when available.
- [x] Document globals that cannot safely exist in Universal mode.

### M4 exit gate

- [x] Repeated import, reload, teardown, concurrent import, and subinterpreter
      stress tests pass on the pinned HPy 0.9 CPython lane.
- [x] No Python object is stored in an unregistered C global in generated
      bootstrap output.

## M5 - Pure HPy extension types and garbage collection

- [x] Add a strict initial fieldless/methodless `cdef class` slice using a pure
      native struct, `HPyType_HELPERS`, `HPyType_Spec`,
      `HPyType_FromSpec`, and interpreter-owned module publication; reject
      methods, bases, and non-private class declarations at compile time.
- [x] Add the first generic Python-valued field slice for private, public, and
      readonly `object` declarations; continue rejecting native, builtin-typed,
      extension-typed, and weak-reference fields.
- [x] Add exact native member storage for signed/unsigned byte, short, int,
      long, long long, plus `float`/`double`; expose public/readonly fields with
      their matching `HPyMember_*` kinds, keep them out of GC traversal, and
      validate initialization, conversion errors, overflow, wide values, and
      readonly behavior.
- [x] Lower the currently supported `cdef class` layouts to pure HPy native structs without
      `PyObject_HEAD`.
- [x] Generate `HPyType_HELPERS`, builtin shape, and `HPyType_Spec` for the
      currently supported layout.
- [ ] Generate method, member, get/set, and slot definitions.
  - [x] Preserve valid Unicode `cdef class` names in HPy type specs and module
        publication while encoding only generated C type/helper symbols; cover
        construction, method/property dispatch, qualified `__module__`,
        Unicode closure captures/arguments/public fields, and
        normal/Trace/Debug execution.
  - [x] Generate ordinary undecorated instance methods as `HPyDef_METH`
        entries with correct receiver, one-argument, keyword, and optional
        positional/keyword-only layouts; store supported defaults on the
        defining type, load them through `self.__class__`, preserve inherited
        and mutable-default identity, and keep unsupported special methods
        rejected.
    - [x] Enable slotless two-argument `__format__` as an ordinary
          `HPyDef_METH` method rather than inventing a type slot; use
          `HPyFunc_O` for a positional-only spelling and the ordinary checked
          keyword wrapper when the source signature permits keywords. Validate
          valid strings, runtime non-string rejection, body errors,
          inheritance, and normal/Debug Mode cleanup.
  - [x] Generate user-written extension-type `property` blocks with exact
        Universal `HPyDef_GET`, `HPyDef_SET`, or `HPyDef_GETSET` definitions;
        preserve docstrings, dispatch null-value deletion separately from
        assignment, retain borrowed receiver/value handles, and validate
        getter-only, setter-only, full get/set/delete, body errors, inherited
        descriptors, three subinterpreters, and normal/Debug Mode cleanup.
        Keep Cython's synthesized public-field properties on their existing
        field-descriptor path rather than emitting duplicate definitions.
  - [x] Attach the defining module to every generated type through an
        interpreter-owned hidden attribute; load it from `self.__class__` in
        ordinary and supported special-slot wrappers so dynamic globals,
        builtins, and module constant caches work without static `HPyGlobal`
        state. Reject runtime-cache name collisions and validate init/call,
        value, length, mapping, hash, bool, contains, richcompare, and finalize
        bodies in normal and HPy Debug Mode; prove dynamic type-method globals
        and module-owned finalizer events remain isolated across three
        subinterpreters.
  - [x] Generate the initial `__init__` slot as `HPy_tp_init`, parse its keyword
        dictionary with `HPyArg_ParseKeywordsDict`, and preserve the integer
        success/failure return contract under normal and Debug Mode.
  - [x] Generate required-self `__repr__` and `__str__` as value-returning
        `HPy_tp_repr`/`HPy_tp_str` slots; validate field-backed string results,
        non-string result errors, cleanup, and Debug Mode.
  - [x] Generate required-self `__len__` through both overlapping
        `HPy_sq_length` and `HPy_mp_length` slots; convert through
        `HPyLong_AsSsize_t`, distinguish the `-1` error sentinel, reject
        negative lengths, and validate integer, truth-test, wrong-type,
        overflow, cleanup, and Debug Mode behavior.
  - [x] Generate two-argument `__getitem__` as `HPy_mp_subscript` plus the
        exact `HPy_sq_item` adapter; turn its native index into an owned Python
        integer with `HPyLong_FromSsize_t`, keep receiver/key borrowed, and
        validate sequence iteration, owned results, lookup failures,
        inheritance, cleanup, and Debug Mode.
  - [x] Generate `__setitem__`/`__delitem__` through shared
        `HPy_mp_ass_subscript` and `HPy_sq_ass_item` dispatchers, branch on a
        null value handle, convert and close native sequence indices, keep
        receiver/key/value borrowed, and validate direct sequence/mapping
        mutation, deletion, inheritance, error propagation, and cleanup in
        normal and Debug Mode.
  - [x] Generate required-self `__hash__` as `HPy_tp_hash`; require an integer
        result with `HPy_TypeCheck`, delegate arbitrary-width normalization to
        `HPy_Hash`, and validate small/big/`-1`/wrong-type results and cleanup.
  - [x] Generate required-self `__bool__` as `HPy_nb_bool`, preserving Cython's
        C `int` return conversion rather than Python-class exact-bool rules;
        validate zero/nonzero, wrong-type, overflow, cleanup, and Debug Mode.
  - [x] Generate `__neg__`, `__pos__`, `__abs__`, and `__invert__` through the
        shared unary HPy value-return contract; validate owned-result identity
        and cleanup in normal and Debug Mode.
  - [x] Generate `__int__`, `__float__`, and `__index__` through their exact
        unary HPy slots; let the calling runtime enforce result types and
        validate valid and wrong-type results in normal and Debug Mode.
  - [x] Generate `__contains__` as `HPy_sq_contains`, convert its result through
        Cython's C `int` contract, and validate true/false, wrong-type,
        overflow, borrowed operand, cleanup, and Debug Mode behavior.
  - [x] Generate the initial `__call__` slice as exact `HPy_tp_call`/
        `HPyFunc_KEYWORDS`, reuse checked positional-only/keyword parsing, and
        pair it with `HPy_tp_new` plus `HPy_New` for HPy 0.9 vectorcall-safe
        allocation; pass constructor arguments to a local or inherited
        supported `__init__`, while a callable with no effective initializer
        accepts only an empty constructor call.
  - [x] Generate every two-argument binary numeric family exposed by HPy 0.9:
        merge each root type's normal/reflected methods into the exact
        `HPy_nb_add`, `subtract`, `multiply`, `remainder`, `divmod`,
        `floor_divide`, `true_divide`, shift, bitwise, and matrix-multiply
        slots, and generate all corresponding in-place slots except the
        nonexistent in-place divmod. Use a unique interpreter-owned type marker
        to select normal versus reflected operands without static handles or
        CPython slot inspection. Cover all 13 left/right and 12 in-place
        operations in a real Universal module, plus two aHPy types, same-type
        reflected-only, user-`NotImplemented`, reflected fallback, raised
        errors, Debug Mode, and three subinterpreters.
    - [x] Merge inherited normal/reflected methods when a generated derived type
          overrides either direction; clone the analyzed ancestor body against
          the derived physical field layout and validate runtime subtype
          priority with `Base + Derived`, `Derived + Base`, unrelated operands,
          and inherited/overridden in-place methods in normal and Debug Mode.
    - [x] Generalize the validated marker dispatcher across all remaining
          two-argument binary/reflected/in-place HPy numeric slots.
    - [x] Implement `__pow__`, `__rpow__`, and `__ipow__` through their separate
          ternary `HPy_nb_power`/`HPy_nb_inplace_power` contract. Support both
          Cython's two-argument form and the three-argument form with an
          optional `None` modulus, reject a real modulus for a two-argument
          implementation, merge inherited normal/reflected directions with
          subtype priority, and validate ordinary/reflected/in-place calls,
          explicit modulus, `NotImplemented` fallback, raised errors, and
          cleanup in normal and Debug Mode without a redundant default cache.
  - [x] Merge `__lt__`, `__le__`, `__eq__`, `__ne__`, `__gt__`, and `__ge__`
        into one exact `HPy_tp_richcompare` opcode dispatcher; keep operands
        borrowed, results owned, return an owned context `NotImplemented` for
        missing operations, and validate all opcodes plus partial fallback in
        normal and Debug Mode.
  - [ ] Generate remaining constructors/special slots, custom get/set
        definitions, and remaining method variants.
- [x] Access currently supported generic object storage only through
      `Struct_AsStruct`, `HPyField_Load`, and `HPyField_Store` inside generated
      methods, including direct assignment and in-place update.
- [x] Generate custom `HPyDef_GETSET`/`HPyDef_GET` descriptors for
      public/readonly generic object fields, preserving initial/delete-to-`None`
      and readonly semantics. Do not use HPy 0.9 `HPyMember_OBJECT`: its
      Universal runtime mutates the static member offset during type creation,
      so a second interpreter would apply the object-head offset twice.
  - [x] Reproduce the repeated-type-creation failure in three subinterpreters
        and prove custom `HPyField_Load`/`HPyField_Store` descriptors keep
        constructor-written values isolated and readable in every interpreter.
- [ ] Complete native member storage and method access.
  - [x] Emit fixed signed/unsigned integer and float/double storage with exact
        HPy member kinds and no false GC ownership.
  - [x] Add direct method reads/writes for every enabled fixed scalar,
        including private fields, signed/unsigned HPy conversion-error checks,
        narrowing overflow, wide values, and success/failure handle cleanup.
  - [x] Preserve direct C `+=`, `-=`, `*=`, `&=`, `|=`, and `^=` semantics
        after Cython rewrites native in-place AST nodes through Python coercion
        nodes; range-check RHS conversion and never accidentally call HPy
        number APIs.
  - [ ] Complete native operators across both Python-result and future typed-C
        RHS paths with their exact division/overflow directives.
    - [x] Lower native integral-field `<<=` and `>>=` directly to C after the
          same checked RHS narrowing used by enabled native updates; validate
          values, conversion overflow, absence of HPy number calls, and
          normal/Debug Mode cleanup.
    - [x] Preserve Cython's currently enabled untyped-RHS analysis for native
          `/=`, `//=`, `%=`, and `**=`: materialize the field as an owned
          Python value, use the exact HPy in-place number API, then convert and
          range-check the owned result back into native storage. Validate
          negative floor/modulo, zero division, float division, integer
          true-division result rejection, power overflow, and normal/Debug
          Mode cleanup.
    - [ ] When typed method arguments are enabled, add the separate direct-C
          division/modulo/power lowering with exact `cdivision`,
          `cdivision_warnings`, zero-division, signed-overflow, `cpow`, and
          result-conversion semantics; do not reuse the Python-result path as
          a substitute for typed C behavior.
  - [x] Store `bint` as the `char` representation required by
        `HPyMember_BOOL`; use exact-bool public descriptors, Cython truth-test
        conversion for constructor/private writes, owned `True`/`False` loads,
        no false GC ownership, and explicit in-place-operator rejection.
  - [x] Store `Py_ssize_t` as exact `HPy_ssize_t` with
        `HPyMember_HPYSSIZET`; use checked `HPyLong_AsSsize_t` writes, owned
        integer loads, platform `sys.maxsize` boundary/overflow coverage, and
        no false GC ownership.
  - [x] Store plain `char` with `HPyMember_CHAR`, preserving the intentional
        split between single-ASCII-string public descriptors and numeric
        direct Cython method access; range-check method writes against the
        platform `CHAR_MIN`/`CHAR_MAX` and exclude the field from GC.
  - [x] Resolve non-external local scalar typedef chains to their exact enabled
        base storage/member kind; preserve strict constructor/private-method
        conversion and the matching HPy public-descriptor narrowing behavior
        under normal/debug execution.
  - [x] Store `long double` without pretending it is an HPy double member;
        generate Universal `HPyDef_GETSET`/`HPyDef_GET` descriptors whose
        Python boundary follows Cython's double conversion, including readonly,
        deletion, conversion-error, direct-method, and debug-leak coverage.
  - [x] Define separate behavior for external typedefs and enums: reject
        external declaration blocks with an ABI-owner diagnostic and reject
        enum fields with a compiler-layout diagnostic. Neither may reuse a
        guessed scalar representation or `HPyMember_INT`; enable them only
        behind future external-header and enum ABI validation gates.
- [x] Store supported Python-valued object fields as `HPyField`.
- [x] Generate `HPy_tp_traverse` visiting every owned field exactly once.
- [x] Apply `HPy_TPFLAGS_HAVE_GC` whenever the supported layout owns fields.
- [ ] Test cycles, clearing, finalization, resurrection, and weak references.
  - [x] Test GC tracking and collection of a self-cycle under normal and HPy
        Debug Mode.
  - [x] Prove refcount deallocation clears registered `HPyField` storage through
        HPy 0.9's traverse-driven generic deallocator: an externally observable
        payload finalizer runs only when its pure-HPy owner is released, in
        normal and Debug Mode.
  - [x] Generate `__del__` as `HPy_tp_finalize`; clean owned temporaries before
        `HPyErr_WriteUnraisable`, validate successful one-shot resurrection,
        second deallocation without refinalization, error hook reporting, and
        normal/Debug Mode cleanup.
  - [x] Test that deleting a public object descriptor replaces its `HPyField`
        with `None` and immediately releases the former payload in normal and
        HPy Debug Mode.
  - [x] Prove failed local and derived `__cinit__` paths close the partially
        allocated object and clear both local and inherited `HPyField` payloads
        in normal and HPy Debug Mode.
  - [ ] Define and test weak-reference layout when that surface is enabled.
    - [x] Audit HPy 0.9 and keep `__weakref__` explicitly rejected with an
          actionable diagnostic: the public API has no weak-reference layout,
          offset, or type-spec surface, and a CPython `tp_weaklist` offset is
          not Universal ABI.
    - [ ] Enable weak references only after the minimum HPy version exposes a
          public portable type-layout contract.
- [ ] Support constructors, allocation, initialization, and deallocation rules.
  - [x] Support the strict initial `__init__` slice with required untyped
        arguments, positional/keyword calls, implicit/explicit-`None` success,
        field stores, and complete failure cleanup.
  - [x] Exercise `__init__` stores into native C `int`/`double` fields,
        including positional/keyword construction, conversion failure,
        narrowing overflow, and Debug Mode cleanup.
  - [x] Lower `__cinit__` through a generated `HPy_tp_new`/`HPy_New` path;
        invoke every generated base-to-derived initializer exactly once with
        the original constructor arguments, run it before `__init__`, and
        close the partial object on any failure.
  - [x] Preserve Cython's nullary-`__cinit__` rule that ignores constructor
        arguments intended for a derived initializer; validate positional and
        keyword construction plus base-field visibility in the derived body.
  - [x] Add the constrained callable-type allocation companion: a generated
        `HPy_tp_new` uses `HPy_New` so HPy 0.9 initializes its hidden vectorcall
        field before the effective local or inherited supported `__init__`
        parses arguments.
  - [x] For a callable type with no effective initializer, make generated
        `HPy_tp_new` validate an empty positional/keyword constructor call
        before `HPy_New`; exercise accepted empty construction and rejected
        positional/keyword arguments in normal and HPy Debug Mode.
  - [x] Support side-effect-free literal/list/tuple/dict defaults on
        `__cinit__`, `__init__`, and `__call__`: evaluate each once in module
        exec, copy its owned handle onto the defining type, load it through
        `self.__class__`, preserve inherited lookup and mutable-default identity,
        and cover
        positional/keyword overrides plus normal and HPy Debug Mode cleanup
        without `HPyGlobal` state.
  - [x] Keep `__dealloc__` explicitly rejected until native-resource bodies
        have a separate validator: HPy 0.9 `HPy_tp_destroy` receives only
        `void *`, without `HPyContext` or an `HPy self` handle; direct users to
        supported `__del__` for Python-level finalization.
  - [ ] Define `__new__`, custom allocation, overridden/explicit base
        initialization, and native-resource deallocation individually.
    - [x] Record and test that Cython's frontend rejects extension-type
          `__new__` before the HPy emitter and directs users to `__cinit__`;
          do not weaken that guard until a custom `HPy_tp_new` allocation,
          layout, base-chain, and partial-cleanup contract is designed.
  - [x] Reuse an inherited required-untyped `__init__` through the runtime type
        hierarchy; cover positional/keyword construction and inherited object
        field stores in normal and HPy Debug Mode.
- [x] Support strict single inheritance from an earlier generated pure HPy type
      in the same module: embed the base payload first, pass
      `HPyType_SpecParam_Base`, resolve the base through interpreter-owned
      module state, alias inherited Cython field entries to their physical base
      storage, expose inherited fields/methods, materialize effective
      initializer/callable wrappers, chain traversal exactly once (including a
      local wrapper plus `HAVE_GC` on inherited-only GC layouts), and collect
      cycles spanning base and derived fields.
- [ ] Support multiple inheritance and generated bases declared after their
      derived type, with an explicit compatible-layout policy.
- [ ] Support inheritance from generated types in other extension modules.
- [ ] Support declared built-in base shapes and metaclasses.
- [ ] Support special methods and numeric/sequence/mapping slots incrementally.
  - [x] Support `__init__`, `__repr__`, `__str__`, `__len__`, `__getitem__`,
        `__setitem__`, `__delitem__`, and `__hash__` through their exact HPy
        slot signatures; include `__bool__` with Cython's exact inquiry
        conversion contract and the initial unary numeric slot family.
  - [ ] Enable each remaining return/signature family independently.
    - [x] Audit `__iter__`/`__next__` and reject them with a versioned API
          diagnostic while HPy 0.9 exposes neither `HPy_tp_iter` nor
          `HPy_tp_iternext`; never substitute CPython `Py_tp_*` slots in
          Universal output.
    - [x] Audit attribute hooks (`__getattribute__`, `__getattr__`,
          `__setattr__`, `__delattr__`), descriptor hooks (`__get__`,
          `__set__`, `__delete__`), and async protocol hooks (`__await__`,
          `__aiter__`, `__anext__`); give each family a versioned HPy 0.9
          diagnostic because the public slot enum lacks the corresponding
          `tp_getattro`/`tp_setattro`, `tp_descr_*`, and `am_*` surfaces.
          Keep extension-type `property` support separate through public
          `HPyDef_GET`/`SET`/`GETSET`.
- [ ] Handle remaining callable-type limitations explicitly.
  - [x] Distinguish local, inherited, and absent initializer allocation without
        falling back to HPy 0.9's argument-rejecting `object.__new__` path.
  - [x] Give callable initializer/call defaults interpreter-owned type storage
        with inherited lookup and checked override parsing.
  - [ ] Gate callable custom `__new__` and unsupported initializer signatures
        with their general constructor work.
- [ ] Reject unsupported variable-size layouts and legacy bases clearly.
- [ ] Define or reject `__dict__`, weakref, freelist, finalizer, and fused
      extension type behavior individually.
  - [x] Reject `__dict__` with a versioned ABI diagnostic while HPy 0.9 has no
        public portable instance-dict layout, offset, or type-spec surface.
  - [x] Reject weakref layout with its separate HPy 0.9 API diagnostic.
  - [x] Support `__del__` finalization with resurrection and unraisable-error
        gates as specified above.
  - [ ] Define freelist and fused-extension-type policy independently.

### M5 exit gate

- [ ] Extension type feature suite passes on all interpreter lanes.
- [ ] HPy traverse/debug validation and cyclic-GC stress tests are clean.
  - [x] Normal and HPy Debug Mode collect self-cycles and cycles spanning the
        inherited and derived `HPyField` portions of a generated layout.

## M6 - Advanced Cython feature families

Each family must be enabled independently and may not be declared supported
until its full existing Cython test subset and new HPy-specific tests pass.

- [x] Closures and captured Python values.
      One-level nested `def` in Universal HPy mode (ADR 0005): synthesized
      env/callable extension types with `HPyField` captures, shared env
      mutation, sibling-function capture unions, capture-free environments,
      `TestHPyModuleWriter` emit/reject coverage, and generated corpus oracles.
      C-typed captures, nested-nested, defaults, `*args`/`**kwargs`,
      generators/`yield`, and decorated nested defs remain rejected with
      actionable diagnostics.
- [ ] Generator objects and generator cleanup.
  - [x] Record ADR 0006's suspended-handle/resume requirements and reject
        top-level `yield`, `yield from`, and real generator expressions with
        HPy-0.9-specific diagnostics instead of CPython coroutine utilities.
  - [ ] Enable generator objects only when the selected public HPy surface has
        iterator-next type slots plus the iterator/exception-state operations
        required by the declared generator subset.
- [ ] Native coroutines, `async`/`await`, and async generators.
  - [x] Record ADR 0007's independent async suspension/cancellation model and
        reject native coroutine plus async-generator functions with explicit
        HPy 0.9 public-slot/exception-state diagnostics.
  - [ ] Enable only after the selected public HPy surface can publish and drive
        awaitable/async-iterator objects without CPython coroutine utilities.
- [ ] Buffer protocol acquisition and release.
  - [x] Record ADR 0008's producer-versus-consumer split, owned `HPy_buffer.obj`
        lifecycle, rollback, and neutral frontend seam requirements.
  - [ ] Implement and validate pure-type producer slots through public
        `HPy_bf_getbuffer`/`HPy_bf_releasebuffer` without `Py_buffer` wrappers.
- [ ] Typed memoryviews and memoryview utility types.
  - [x] Reject typed buffer/memoryview arguments immediately after declaration
        analysis with one HPy 0.9 consumer-API diagnostic, before CPython
        memoryview utilities can produce unrelated errors.
  - [ ] Enable acquisition and typed memoryview utilities only after a selected
        HPy version exposes public consumer acquire/release operations.
- [ ] Fused types and specialization dispatch.
  - [x] Record ADR 0009's neutral specialization descriptors, pure-HPy
        callable/subscriptable dispatcher, typed conversion, signature metadata,
        ambiguity ordering, and cleanup requirements.
  - [x] Reject fused `def`/`cpdef` with one source-located diagnostic before
        CPython `__Pyx_FusedFunction`/PyCFunction emission.
  - [ ] Implement independently gated module-function specializations and exact
        Python dispatch parity; fused extension methods remain a later subgate.
- [ ] `nogil`, enter/leave Python execution, and exception reacquisition.
  - [x] Record ADR 0010's public-HPy transition, no-handle interval, native
        library contract, re-entry, and staged typed-conversion requirements.
  - [x] Support non-empty `with nogil` blocks containing only discarded,
        argumentless calls to validated external C functions declared
        `noexcept nogil`, using `HPy_LeavePythonExecution` and
        `HPy_ReenterPythonExecution` with a local `HPyThreadState`.
  - [x] Validate the linked native probe in normal/Debug runtime execution and
        reject argument-bearing or empty blocks without generated C.
  - [ ] Preconvert typed scalar arguments before leaving execution, retain
        native results, re-enter, and only then perform HPy result conversion.
  - [ ] Design nested `with gil`, native failure/exception reacquisition,
        callbacks, and every structured early-exit cleanup path.
- [ ] `prange`, OpenMP, synchronization, and free-threading interactions.
  - [x] Record ADR 0011's backend-neutral scheduling/reduction plan,
        originating-thread transition, native-only worker rules, sequential
        fallback, error transport, and free-threading capability boundaries.
  - [x] Reject `prange` and `cython.parallel.parallel()` with one HPy
        0.9-specific worker-attach/error-transport diagnostic before CPython
        thread-state or exception-triple emission.
  - [ ] Extract a backend-neutral parallel plan while preserving byte-identical
        default/explicit CPython output.
  - [ ] Implement the first native-only counted-loop/static-schedule slice,
        including OpenMP-disabled parity, private/lastprivate state, master
        leave/re-entry, race tests, and no HPy access from workers.
  - [ ] Add reductions, scheduling/chunks, cancellation, native failures, and
        supported-runtime free-threading as independent subgates.
  - [ ] Permit Python-capable workers only after a selected public HPy API
        provides worker attachment, context, error transport, and cleanup.
- [ ] C callbacks carrying Python state.
- [ ] Cython public/API declarations across generated modules.
- [ ] Capsules and cross-module C APIs.
- [ ] C++ compilation, exceptions, STL conversions, and RAII interaction with
      HPy cleanup.
- [ ] Profiling, tracing, coverage, monitoring, and traceback generation.
- [ ] Pickling, signatures, annotations, code objects, and introspection.
- [ ] Embedding and multiple embedded HPy modules.
- [ ] NumPy and third-party C-API interoperability policy.

### M6 exit gate

- [ ] Every feature is marked supported, partial, blocked, or rejected with a
      linked test and rationale.
- [ ] No partially implemented feature is enabled by default.

## M7 - Build, packaging, and developer experience

- [x] Integrate backend selection with `cython`, `cythonize`, and programmatic
      compilation APIs; prove `cythonize(...,
      runtime_backend="hpy-universal")` through a real HPy setuptools build.
- [ ] Integrate HPy include paths, compile macros, output suffixes, and linking.
  - [x] Prove HPy's setuptools lane supplies the public includes, Universal ABI
        macro, `.hpy0` suffix, runtime sources, and platform link command for
        the maintained cythonize example.
  - [x] Define the non-setuptools/direct build contract and its public API:
        schema-versioned toolchain plans, Universal defines/include ordering,
        static/helper-source runtime selection, POSIX/MSVC link contracts,
        `.hpy0` naming, safe output rules, source/binary audits, manifests, and
        public-loader normal/Debug integration.
- [x] Provide a maintained PEP 517 build path with an exact
      `aHPy-compiler` frontend identity, a Universal-only backend wrapper, a
      clean frontend wheel, genuine pip build isolation, source/binary audits,
      install, and normal/Debug execution; keep publication blocked until the
      distribution name is reserved.
- [x] Test setuptools integration with `hpy_ext_modules`, generated-source and
      binary ABI audits, `.hpy0` discovery, a module function, a pure extension
      type, and normal/Debug execution.
- [x] Test Meson integration through a rendered Universal contract,
      `shared_module`, `.hpy0`/binary audits, and normal/Debug execution.
- [x] Test CMake module integration and a separately isolated
      scikit-build-core wheel using installed `ahpy_build_config`, exact build
      tool pins, source/binary audits, pip install, and normal/Debug import.
- [ ] Generate correct Universal HPy wheel names and metadata.
  - [x] Record ADR 0004: current HPy 0.9 `bdist_wheel` contains the audited
        `.hpy0` binary/stub but emits a CPython-specific wheel tag; do not call
        or rename that envelope Universal.
  - [ ] Adopt a standardized HPy/PyPA Universal compatibility tag only after
        the upstream packaging contract exists.
- [x] Test clean source distributions and wheel installation.
  - [x] Build the current host-tagged wheel, inspect its `.hpy0`/stub/WHEEL
        contents, install with pip into an empty target directory, and execute
        it on the validated CPython builder.
  - [x] Add an isolated PEP 517 wheel build and install using the exact locally
        built `aHPy-compiler` frontend wheel.
  - [x] Add a clean aHPy sdist safety audit, no-index wheel-from-sdist build,
        fresh-venv install, clean-directory absence checks, frontend/example
        uninstall/reinstall, normal/Debug execution, and hashed JSON evidence.
  - [ ] Add cross-interpreter package installation after the publication/tag
        blockers are resolved; a host-tagged wheel is not sufficient evidence.
- [x] Add `Tools/ahpy/doctor.py` as the `ahpy doctor` equivalent with text/JSON
      reports, exact stable/development pin validation, venv-safe interpreter
      probing, HPy header checks, compiler/symbol-reader discovery, strict
      early-warning policy, unit tests, and a stable CI gate.
- [x] Add `Tools/ahpy/scan_compatibility.py`: strict compile scanning, generated
      header-boundary verification, direct `cpython.*`/`Python.h` detection,
      stable migration action IDs, text plus schema-versioned JSON, distinct
      rejection/compiler-error exits, tests, documentation, and a CI self-scan.
- [x] Catalog all 150 current strict Universal `unsupported(...)` call sites in
      `diagnostics-catalog.json` with source ownership, message templates, and
      migration actions; rebuild/compare the catalog in tests and document the
      no-fallback diagnostic policy.
- [x] Provide minimal, extension-type, external-C, and packaging examples.
  - [x] Add the maintained `examples/ahpy_setuptools` minimal function + pure
        extension-type example and build its exact files in CI.
  - [x] Extend the maintained setuptools example with a linked
        Python-independent C header/source library, signed/unsigned/bool/float
        results, checked scalar arguments, normal/Debug execution, source and
        binary audits, wheel install, and an overflow regression.
  - [x] Add the maintained `examples/ahpy_pep517` isolated packaging example;
        document that its current host-tagged wheel is not a portability claim.

### M7 exit gate

- [x] A new user can build, install, and import the maintained PEP 517 example
      from a clean environment using the commands in `docs/ahpy/onboarding.md`;
      publication and cross-interpreter package installation remain separate
      gates.

## M8 - Continuous integration and quality engineering

- [x] Linux x86-64 and ARM64 lanes.
  - [x] Declare explicit `ubuntu-24.04` x86-64 GCC/Clang and
        `ubuntu-24.04-arm` GCC jobs without a moving runner alias.
  - [x] Record the first green hosted run for every declared Linux job before
        claiming platform support.
- [x] macOS Intel and Apple Silicon lanes.
  - [x] Declare explicit `macos-15-intel` and ARM64 `macos-15` Apple Clang
        jobs.
  - [x] Record the first green hosted run for both macOS architectures.
- [x] Windows x64 lane.
  - [x] Declare the explicit `windows-2025` MSVC job and make the binary import
        audit fail closed through `dumpbin`, `llvm-nm`, or `objdump`.
  - [x] Record the first green hosted Windows/MSVC run.
- [x] GCC, Clang, and MSVC coverage.
  - [x] Put all three compiler families in the dedicated stable matrix.
  - [x] Promote coverage to supported only after every hosted job is green.
- [ ] Supported CPython, PyPy, and GraalPy versions.
  - [x] Validate the initial CPython 3.11 release and development-revision
        environments locally.
  - [ ] Build once and execute the same Universal binary on the selected PyPy
        and GraalPy versions.
    - [x] Pin PyPy 7.3.23/Python 3.11.15 and GraalPy 25.1.3/Python 3.12 in a
          machine-readable manifest; build and hash one CPython-hosted
          Universal artifact, then download that unchanged artifact in both
          target jobs.
    - [x] Verify every downloaded member digest, separate Python-stub and
          native HPy loading, and isolate module imports/semantics into four
          subprocess stages so a signal identifies its exact boundary.
    - [ ] Record the first green hosted execution on both interpreters and
          remove `continue-on-error` before claiming cross-interpreter support.
- [x] Add the HPy 0.9 release lane and a full-commit-pinned HPy development
      lane; keep the latter early-warning-only and record the current Python
      3.14 `SIGSEGV` separately from the validated Python 3.11 result.
- [x] Interpreter and HPy nightly early-warning lanes that do not silently alter
      release support claims.
  - [x] Add an allowed-failure Python 3.14 job for the pinned HPy development
        revision without changing stable support.
  - [x] Add schedule/manual-only CPython `3.15-dev` with stable HPy and
        CPython 3.11 with HPy `master` as independent allowed-failure jobs;
        record the exact interpreter, installed package source, and resolved
        40-character HPy VCS commit without changing pinned support lanes.
- [x] Keep the existing full Cython CPython regression workflow as the primary
      regression lane and add the focused aHPy C/C++ semantic oracle to the
      dedicated workflow.
- [x] Run the real generated Universal corpus in HPy release, Trace, and Debug
      modes; retain Debug `LeakDetector` as a mandatory gate.
- [ ] ASan, UBSan, LSan/Valgrind, and platform-appropriate memory tooling.
  - [x] Add a Linux GCC ASan/UBSan build-and-execute job with matching
        `libasan` preload and fail-fast diagnostics.
  - [x] Add an Apple Clang ASan/UBSan job that discovers and preloads the
        matching dynamic sanitizer runtime before Python imports the module;
        use a native-architecture ASan-linked `Py_BytesMain` launcher because
        signed Python executables may discard `DYLD_INSERT_LIBRARIES`.
  - [x] Add a separately validated LSan/Valgrind lane with versioned
        suppressions for the uninstrumented host interpreter; do not treat
        unrelated interpreter allocations as backend leaks.
    - [x] Declare a schedule/manual allowed-failure Linux Valgrind job that
          proves the positive control survives suppressions and enforces all
          five generated-corpus runtime processes with definite-leak failures.
    - [x] Record the first hosted green, review every suppression, and promote
          the job only after its uploaded logs prove the clean corpus.
  - [ ] Add Windows Application Verifier or an equivalent reviewed memory
        diagnostic.
    - [x] Declare a schedule/manual `windows-2025` AppVerifier Basics plus
          GFlags full-page-heap job. Require a native heap-overrun positive
          control, verifier injection in all five generated-corpus processes,
          clean XML error parsing, raw logs, and unconditional settings cleanup.
    - [ ] Record the first hosted run, inspect tool discovery and every uploaded
          log, repair any runner/tool mismatch, then remove `continue-on-error`
          only after the positive control and real corpus are both proven.
      - [x] Review probe run `29945115651`, job `89008424404`: both x64 tools
            exist and cleanup passed; replace the unreliable aggregate
            `gflags /p` assertion with direct enable output plus AppVerifier's
            `Heaps`/`Full=true` query.
- [x] Audit generated source plus undefined binary imports on Unix and Windows;
      fail closed when no supported symbol reader exists.
- [x] Add byte-for-byte deterministic Universal source generation from two
      independent output directories; sort the module failure epilogue that
      the new gate exposed as nondeterministic.
- [ ] Reproducible package-build test.
  - [x] Build the CPython-hosted Universal portability artifact twice in
        independent temporary roots with fixed time and debug/file prefix
        maps; require byte-identical `.hpy0` binaries, loader stubs, smoke
        program, and SHA-256 manifest.
  - [x] Build the real `aHPy-compiler` sdist and pure-Python frontend wheel in
        two independent clean roots; normalize tar/gzip metadata, require
        byte-identical archives, and record hashes plus interpreter/build-tool
        provenance.
  - [ ] Apply the same two-root native/archive gate to the future standardized
        Universal extension wheel format; the current CPython-tagged examples
        are not that format.
- [x] Add deterministic model-property tests that exhaust ownership kinds and
      all `use`/`close`/`move`/`return` sequences through depth four, plus
      every three-handle terminal-state, exit-kind, and preserve combination.
- [x] Fault-injection tests for API/allocation failure paths.
  - [x] Interpose `HPyLong_FromLongLong` in a test-only generated Universal
        module and force failure at each of three partially built list
        positions; require exact `MemoryError`, builder cancellation, binary
        ABI audit, and leak-free normal/Debug execution.
  - [x] Expand deterministic interposition to list-builder build, dictionary
        set, calls, attribute reads, and item reads; run every failure and
        no-failure boundary in isolated normal/Debug processes.
  - [x] Inject initial `HPyType_FromSpec` and module `HPy_SetAttr_s` publication
        failures during import; require exact `MemoryError`, removal from
        `sys.modules`, collection, clean Debug state, and successful
        one-past/unselected imports.
  - [x] Classify the one macOS transient `SystemError`: it did not reproduce in
        five bounded concurrent rounds covering 640 fault selectors, generated
        corpus, setuptools, and full fixed fuzz. Replace the unsafe ad-hoc
        orchestration that left compiler descendants behind with isolated
        process groups, recursive timeout cleanup, retained logs, and a
        one-round CI recurrence gate; keep normal O3 release validation
        independent from the documented stress-only O0 profile.
  - [x] Expand deterministic interposition to nested list/tuple builders,
        three dictionary insertions, direct and expanded call shapes,
        three attribute/item reads, attribute/item set/delete, all three type
        creations, every generated module/type publication position, and
        independently owned intermediate cleanup; run 128 isolated
        normal/Debug cases and fix the exposed transactional init rollback.
- [x] Fuzz compiler inputs and selected runtime operation sequences.
  - [x] Generate a fixed-seed 48-function corpus spanning nested containers,
        continuing branches, `while` mutation, fixed-sequence `for`, in-place
        operations, and slices; compare the same source against a pure-Python
        oracle in normal/Debug mode with source/binary ABI audits.
  - [x] Preserve the first discovered crash as a regression: recursively
        flatten transformed nested `StatListNode` sequences before HPy emission.
  - [x] Add a deterministic rejected-input corpus for set construction, generic
        iteration, loop/branch termination, and handlers; require an actionable
        diagnostic and prohibit tracebacks/internal compiler errors.
  - [x] Add deterministic coverage-guided frontend mutation: compile 64 seeded
        candidates under line tracing, greedily retain new compiler/backend
        lines or feature families, combine the selected 16-family corpus, and
        compare randomized executable API/ownership sequences with the Python
        oracle in normal/Debug mode plus source/binary ABI audits.
- [x] Add dependency-free deterministic Python line coverage reporting split
      by backend, frontend seam, quality utilities, and five feature-test
      families; enforce cross-Python conservative CI floors while keeping
      generated/native/subprocess behavior in its dedicated runtime gates.
  - [x] Reach 100% executable Python-line coverage for `HPyModuleWriter.py`,
        `HandleModel.py`, and `RuntimeAPI.py` on CPython 3.11 and 3.14; trace
        562 tests and lock CI floors at backend 100%, frontend seam 45%, and
        quality tools 41% without conflating native/generated-C gates.
- [x] Add benchmark history and regression thresholds.
  - [x] Compare generated Universal HPy with an equivalent handwritten
        public-HPy module for identity/call overhead, arithmetic, containers,
        attributes, nested calls, and exceptions in alternating local repeats.
  - [x] Enforce versioned relative runtime and source/binary footprint budgets,
        verify both binaries in normal and Debug modes, and upload every
        timestamped JSON result as a run-specific append-only CI artifact.

## M9 - Performance and footprint

- [ ] Establish handwritten HPy reference implementations for all benchmark
      families.
  - [x] Maintain equivalent public-HPy references for identity/call,
        arithmetic, containers, attributes, nested calls, and exceptions.
  - [x] Add equivalent type and external-C references; iteration/memoryview
        references remain non-comparable while the generated Universal paths
        are blocked.
- [x] Compare classic Cython, HPy CPython ABI, and HPy Universal ABI separately;
      retain standalone classic timings and independent generated/reference
      ratios for each HPy ABI instead of one cross-ABI overhead number.
- [ ] Measure calls, arithmetic, containers, attributes, exceptions, types,
      iteration, memoryviews, and external-C wrappers.
  - [x] Measure calls, arithmetic, containers, attributes, and exceptions in
        alternating generated/reference repeats with Debug semantics.
  - [x] Add types and external-C wrappers; record iteration/memoryviews as
        blocked rather than fabricating runtime numbers until supported.
- [x] Measure compile time, C compiler time, generated C size, binary size, and
      peak memory.
  - [x] Record frontend time, combined native build time, source/binary sizes,
        and separate-clean-process generated/reference peak RSS in every
        Universal benchmark JSON.
  - [x] Isolate and budget the generated `bootstrap_types.c` native compile:
        every benchmark regenerates the 4.98 MB/87,259-line corpus, measures
        `-O0` and `-O3` independently under a 60-second ceiling. O0 is the
        required C-validity/liveness gate; O3 is diagnostic after Ubuntu GCC 13
        exceeded both 60- and 180-second trials. Apple Clang 21 completed in 1.59/5.29
        seconds (3.32×); the earlier post-stress >15-minute result is not
        reproducible without the discarded concurrent/orphaned process state.
- [x] Use HPy Trace Mode to identify excess API calls and handle churn; record
      exact per-operation API deltas and `ctx_Dup`/`ctx_Close` counts for both
      generated and handwritten modules in benchmark history.
- [ ] Optimize duplicate/close pairs only after ownership proofs and tests.
  - [x] Align generated/reference positional-only call contracts, then borrow
        direct live Name handles for `HPy_GetAttr_s` receivers and zero-argument
        `HPy_Call` callables. Trace proves attribute/call fell from 7 to 1 API
        call per iteration and from 2 Dup/1 Close to zero churn; normal,
        Trace, Debug, 179 emitter tests, and all 128 fault selectors pass.
  - [x] Route two-or-more required positional-only arguments through
        `HPyFunc_VARARGS`, then borrow direct live Name operands for binary APIs
        and fixed sequence-builder items under an evaluation-order proof.
        Arithmetic/container now match the handwritten references at 1/4 API
        calls with zero Dup/Close churn; normal, Trace, Debug, 185 emitter
        tests, and all 128 fault selectors pass.
  - [x] Borrow call-scoped extension-field owners and direct field-store Name
        values, load type/module owners only at their first actual use, and bind
        positional-only initializer slot arrays without a tracker. Type method
        Trace is 2.003/2.002 calls versus the reference; type creation is 3/2
        because generated `__cinit__` requires a separate `AsStruct`. Both have
        zero Dup/Close churn and enforce 1.5× runtime ceilings.
  - [x] Lower safely representable numeric arguments to validated external-C
        scalar functions as explicitly typed portable C literals. Preserve the
        checked HPy conversion path for dynamic, non-finite, plain-`char`
        ambiguous, and out-of-portable-range values. External-C Trace now
        matches the handwritten reference at 1 call/iteration with zero
        Dup/Close churn and enforces a 1.5× runtime ceiling.
- [ ] Define and enforce release performance budgets.
- [x] Document interpreter/HPy reference cost separately from aHPy overhead by
      retaining standalone classic timings and same-ABI handwritten HPy
      baselines; publish no aggregate cross-ABI ratio.

## M10 - Real-library pilots and ecosystem adoption

- [ ] Select a pure Cython pilot with no direct Python C-API dependency.
- [ ] Select a Cython wrapper around a Python-independent C library.
- [ ] Select a project using extension types, GC, and inheritance.
- [ ] Select one deliberately blocked CPython/NumPy C-API project to validate
      diagnostics.
- [ ] Record required source changes, unsupported constructs, build changes,
      test results, and performance for every pilot.
- [ ] Convert recurring source changes into compiler support or documented
      migration rules.
- [ ] Publish a compatibility dashboard generated from CI artifacts.
- [ ] Provide a library-author porting guide and issue template.
- [ ] Share the HPy conformance corpus with the author's programming language
      without coupling that language frontend to Cython internals.

## M11 - Upstreaming, release, and maintenance

- [ ] Agree on the backend seam with Cython and HPy maintainers before large
      implementation growth.
- [ ] Submit backend-neutral Cython refactors as small independent pull requests.
- [ ] Submit HPy API gaps or bugs to HPy with minimal reproductions.
- [ ] Maintain an upstream/rebase log and resolve divergence continuously.
- [ ] Complete user, contributor, architecture, debugging, and release docs.
- [ ] Complete security, vulnerability reporting, and supported-version policy.
- [ ] Produce release candidates and run the full release matrix.
- [ ] Verify source and binary reproducibility and artifact provenance.
- [ ] Publish limitations and known blockers without optimistic fallback claims.
- [ ] Tag the first stable release only after every declared support-tier gate is
      green.
- [ ] Define ongoing Cython, HPy, interpreter, compiler, and platform update
      cadence.

## Universal ABI coverage completion track

Authorized scope: maximize correct HPy 0.9 Universal coverage and complete the
full M2–M11 roadmap. Detail lives in the milestone sections above;
`AGENTTODO.md` Phase U0–U5 is the operational order. A track item is complete
only when its nested milestone checkboxes, tests, docs, and exit gates are
complete. HPy 0.9 public-API absences stay blocked/rejected—never silently
emulated.

### U0 - HPy 0.9 hard gaps (diagnose-only lock)

- [ ] Keep set construction/mutation rejected until a selected public HPy set
      API exists; no private-API emulation.
- [ ] Keep generic iteration and pure-type `__iter__`/`__next__` rejected while
      HPy 0.9 lacks `GetIter`/`IterNext` and the matching slots.
- [ ] Keep general exception-state handlers (`except as`, reraise, traceback/
      cause/chaining, `else`/`finally`, nesting) rejected without a public
      exception-state model.
- [ ] Keep portable `__dict__`, `__weakref__`, and context-bearing `__dealloc__`
      rejected with versioned diagnostics.
- [ ] Keep missing attribute, descriptor-protocol, and async type slots
      rejected; do not substitute CPython `Py_tp_*` / `Py_am_*` slots.
- [ ] Keep code-object caches and HPy-method function-object introspection
      blocked on HPy 0.9.
- [x] Keep mutable `HPyGlobal` unpublished under multi-interpreter isolation;
      document immediate failed-import-without-GC as an upstream loader gap
      (done in `module-state.md` / M4 audit; GC-free retry remains unsupported).
- [ ] Keep Hybrid fallback, `cpython.*`, `PyObject *`, and CPython-only
      third-party/NumPy C-API paths rejected or blocked with migration guidance.

### U1 - Local HPy 0.9 max semantic surface

- [x] U1 closable surface pack (HPy 0.9 public API only): function
      `dir()`/`globals()`, module `locals()`/`dir()` via `__dict__`+sorted
      keys, reject-duplicates keyword merges, imag constant cache, slot/
      property early returns, richer terminal try/except, sequence-safe
      inlined genexps; suite/oracle/fuzz/catalog green. Remaining U1 work
      below is residual/open surface, not this pack.
- [ ] Complete M2 context/cleanup for every remaining return/break/continue/
      goto/exception exit and every remaining Python-interacting utility;
      pure-C helpers stay context-free.
  - [x] Loop break/continue and end-of-iteration body-temp cleanup,
        return/raise-from-loop, mixed terminating/continuing conditional
        branches, `assert`, and counted `range`/`for-from` loops.
  - [x] Effectful argument defaults with source-safe `HPy_mod_exec` evaluation
        order; `__defaults__` introspection remains HPy 0.9 blocked.
  - [x] Bootstrap Universal context policy: no `Cython/Utility` consumption;
        pure-C traverse helpers remain context-free.
  - [x] `HPy_CallMethod` direct method calls and Ellipsis literals.
  - [x] Local extension-type GC stress oracle for cycle, finalize, resurrect,
        and field-clear paths on Python 3.11; hosted all-interpreter promotion
        remains U2-open.
- [x] Close remaining M3 value/container/call/control-flow/default parents that
      HPy 0.9 can express locally in the U1 closable surface pack
      (`dir()`/`globals()`/`__dict__`, reject-duplicates dicts, sorted mapping
      keys, richer terminal try/except, sequence-safe inlined genexps); leave
      U0 gaps (sets, GetIter, `except as`/finally, `__defaults__`) rejected.
- [x] Expand the generated runtime corpus and fault oracles for the U1 closable
      surface pack (function `dir`/`globals`, imag identity, inlined genexp,
      conditional try, slot early returns).
- [x] Complete remaining M4 caches that HPy 0.9 can host for the closable pack
      (imaginary/complex constant cache); keep code-object caches blocked.
- [x] Complete remaining M5 slot early-return lifetime unification for
      `__len__`/`__bool__`/`__hash__`/`__contains__`/property/`__call__` bodies
      that HPy 0.9 can express; compile-time diagnostics now cover freelist,
      multiple inheritance, metaclass, variable-size layout, and `__dealloc__`;
      hosted GC stress promotion remains open.

### U2 - M8 evidence without false claims

- [x] Keep every mandatory workflow green on the current aHPy branch HEAD,
      including the upstream Cython C/C++ and non-CPython regression matrix.
      Run `29900694989` verifies that the focused GraalPy exclusion moved past
      the former Universal-fixture import failure while compile-only aHPy
      fixtures remain covered. Its Windows C++/Python 3.11 full lane later hit
      the known hosted MSVC parallel-link transient `LNK1158` when `link.exe`
      could not launch the otherwise-present Windows SDK `rc.exe`; Windows
      `runtests.py` parallelism was bounded at four, but replacement run
      `29905498043` showed `shared_utility_module` overlapping its internal
      `build_ext -j3` with that outer pool. Both `shared_utility` trees are now
      isolated from the four-worker pass while retaining their internal
      parallel build. At commit `d0026d83b`, push run `29912142526` attempt 2
      and PR run `29912145346` each completed all 103 jobs successfully;
      coverage run `29912145042` completed both jobs successfully. The early
      Windows C/C++ jobs executed the isolated one-tree pass and both
      `memoryview_shared_utility` and `shared_utility_module` passed without
      `LNK1158`.
- [x] Record first green hosted runs for every declared Linux/macOS/Windows
      compiler job. Push run `29685285138` is green at commit `02d9f8cdd` for
      Linux x64 GCC/Clang, Linux ARM64 GCC, macOS Intel/ARM64 Clang, Windows x64
      MSVC, both sanitizer jobs, pinned HPy development on Python 3.11, and the
      complete compiler/quality job; exact job URLs, runner images, compiler
      versions, and portability hashes are in the M8 platform repair audit.
- [ ] Record same-binary PyPy and GraalPy hosted executions and remove
      `continue-on-error` only after green evidence. Run `29685285138` records
      both executions as red allowed-failure early warnings: PyPy terminates at
      its first bridge import and GraalPy has no HPy bridge/native `.hpy0`
      import hook. Neither target is supported.
- [x] Finish local nightly contract tests and support-claim wording guards:
      manifest status sets, stable-vs-nightly separation, evidence-state
      wording, ASan `detect_leaks=0`, job contracts, and exact revision reports.
- [ ] Record first green hosted executions of both moving nightly jobs; retain
      allowed-failure early-warning status and do not alter stable support.
      Manual run `29906185775` records CPython 3.15.0-beta.4 failing in HPy
      0.9's own `-Werror` build before aHPy runs, while HPy `master` passed VCS
      provenance at the already pinned `b57a33c1...` commit but omitted the
      pinned lane's `-O0` profile and hung in the optimized generated build for
      over 90 minutes. Both runtime steps now use `-O0` and a 30-minute timeout.
  - [ ] CPython `3.15-dev` with HPy 0.9 remains externally red at the HPy build
        boundary and has no green execution.
  - [x] CPython 3.11 with HPy `master` completed its first bounded green in
        manual run `29912162645`, job `88897432348`; provenance resolved the
        expected full commit and the `-O0` generated runtime finished in 19
        seconds. It remains an allowed-failure early warning.
- [ ] Add reviewed Linux LSan/Valgrind and Windows Application Verifier lanes
      with independent positive native-memory controls.
  - [x] Promote the Linux job after manual run `29906185775`, job
        `88878105102`, detected the 64-byte positive control, produced five
        clean real-corpus logs, and confirmed zero active suppressions.
  - [x] Declare the Windows AppVerifier/GFlags diagnostic as an allowed-failure
        schedule/manual job with fail-closed tool discovery, a native overrun
        positive control, five verified generated-runtime processes, XML/raw
        evidence, and settings cleanup.
  - [ ] Review the first hosted Windows artifact and promote the diagnostic only
        after AppVerifier injection and full-page-heap detection are proven.
- [ ] Apply reproducibility gates to future aHPy sdist and Universal wheel
      formats after U4 packaging exists.

### U3 - M6 advanced feature families

- [ ] Enable each M6 family only behind an ownership/context design, dedicated
      tests, support-matrix status, and no default partial implementation:
      closures, generators, async, buffers/memoryviews, fused types, `nogil`/
      parallelism, C callbacks/capsules/public APIs, C++/RAII, profiling/
      introspection, embedding, and NumPy/third-party Universal policy.

### U4 - M7 packaging and onboarding

- [ ] Ship direct-build, PEP 517, Meson, and CMake/scikit-build-core paths where
      applicable; adopt Universal wheel tags only after HPy/PyPA standardize
      them; prove clean sdist/install/uninstall and new-user documented builds.
      The local build paths, clean sdist/install/uninstall, and documented
      new-user gate are complete and frontend archives are byte-reproducible;
      standardized tags, publication, cross-interpreter packaging, hosted
      evidence, and standardized Universal extension-wheel reproducibility keep
      U4 open.

### U5 - M9 / M10 / M11 release readiness

- [ ] Keep README status, support/validation matrices, audit evidence,
      `AGENTTODO.md`, and draft PR metadata synchronized to the same published
      HEAD after each hosted fix; do not advertise stale or mixed-run evidence.
- [ ] Satisfy M9 performance budgets with hosted history and separate
      interpreter/HPy overhead accounting.
- [ ] Complete the four M10 pilots and publish dashboard/porting guidance.
- [ ] Finish M11 upstreaming, docs, security, provenance, and release cadence;
      tag a stable release only when the definition of done below is fully true.

## Stable-release definition of done

- [ ] All tasks for the declared support tiers are complete.
- [ ] All mandatory CI lanes are green from clean builds.
- [ ] HPy Debug Mode reports no backend-originated handle defect.
- [ ] Universal artifacts contain no forbidden CPython dependency.
- [ ] The same Universal binary passes the declared cross-interpreter matrix.
- [ ] CPython backend regressions are zero or explicitly accepted upstream.
- [ ] Performance and footprint remain within published budgets.
- [ ] Documentation, diagnostics, examples, migration tooling, and pilot reports
      match actual behavior.
- [ ] Every deferred feature is explicitly marked partial, blocked, or
      unsupported.
- [ ] U0 HPy 0.9 hard gaps remain explicitly blocked/rejected (never claimed
      supported on 0.9).
- [ ] U1 local max surface and U2–U5 roadmap gates matching the declared
      support tiers are complete.
