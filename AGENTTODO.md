# aHPy agent handoff and ordered work queue

This file is the operational handoff for AI agents continuing aHPy. It does
not replace `TODO.md`: that file is the normative, dependency-ordered project
checklist. An agent must update both files when implementation status changes.

## 1. Snapshot and source of truth

- Snapshot date: 2026-07-16 (Cursor continuation audited and reconciled).
- Workspace: `/Users/melihburakmemis/Documents/aHPy`.
- Branch: `codex/ahpy-bootstrap`.
- Cython base/HEAD: `b99cb0e3b5425e11414cadd24168a6cc850e8000`.
- Stable local environment: `.venv-hpy09`, CPython 3.11.15, HPy 0.9.0.
- Additional local coverage interpreter: `python3`, CPython 3.14.6.
- The verified aHPy implementation is committed through `39c7c6830`; preserve
  later user/agent work and do not reset, clean, overwrite, or discard it.
- `.DS_Store` and
  `docs/examples/userguide/wrapping_CPlusPlus/rect_with_attributes.cpp` are
  user-owned/unrelated. Leave them untouched.
- `origin` is `https://github.com/mburakmmm/aHPy.git`; upstream Cython baseline
  `b99cb0e3b` is published as `main`, and `codex/ahpy-bootstrap` is pushed.
  The first hosted aHPy workflow is run `29490045367`; it is still in progress,
  so do not claim a hosted green before every required job and artifact is
  reviewed.
- User mandate (2026-07-15): complete **HPy 0.9 max Universal coverage** and the
  **full M2–M11 roadmap** (options 1+3). Work the ordered queues below; never
  mark a HPy-0.9 API gap as supported; never claim hosted lanes without green
  hosted evidence.

Read these before changing code:

1. `TODO.md` — normative scope, dependencies, and exit gates.
2. `docs/ahpy/README.md` — project contract.
3. `docs/ahpy/support-matrix.md` — current support claims.
4. `docs/ahpy/validation-matrix.md` — actual validation evidence.
5. `docs/ahpy/adr/` — architecture and release decisions.
6. The milestone audit matching the code being changed in
   `docs/ahpy/audits/`.

## 2. Non-negotiable implementation rules

- Never silently fall back from `hpy-universal` to CPython, HPy Hybrid, or HPy
  CPython ABI.
- Use only public HPy APIs for Universal output. Generated source must not
  include `Python.h`, use `PyObject *`, or import CPython runtime symbols.
- Preserve default and explicit CPython code generation. A frontend change
  needs CPython C/C++ oracle coverage.
- Treat every `HPy` as an ownership/lifetime value. Prove borrowed, owned,
  moved, closed, field, global, and context-constant behavior before emitting
  cleanup.
- Keep syntax decisions in compiler nodes and runtime differences behind the
  typed Runtime API/emitter seams. Do not spread string-based backend checks.
- An unsupported feature must fail at its source location with an actionable
  diagnostic; an internal traceback is a defect.
- Every executable Universal case must have normal semantics, Debug
  `LeakDetector`, source-boundary, and undefined-binary-import coverage.
- Every fixed crash, leak, invalid handle, cleanup error, ABI violation, or
  nondeterminism needs a focused regression test.
- Do not mark a TODO item complete until implementation, failure paths, tests,
  documentation, and the stated exit gate are all complete.
- Do not turn declared/allowed-failure hosted jobs into support claims without
  recording a real green hosted run.
- Preserve upstreamability: prefer a neutral compiler seam followed by a small
  HPy implementation change over a monolithic alternate compiler.

## 3. Verified state at this snapshot

Completed implementation layers include the Runtime API seam, handle model,
context and cleanup planning, strict Universal module/function generation,
module globals/imports/defaults, implemented expressions/containers/calls and
control flow, restricted current-error exception handlers, pure HPy extension
types/fields/GC/inheritance/slots/finalizers, diagnostics/scanner/doctor,
setuptools plus external-C integration, portability/reproducibility tooling,
fault injection, deterministic and coverage-guided fuzzing, focused coverage,
and the first performance regression gate.

Last verified local gates:

- Focused compiler suite: 354 tests pass (includes U1 closable surface and
  closure-registry regressions:
  `dir()`/`globals()`/`__dict__`, reject-duplicates keywords, imag constant
  cache, richer terminal try, sequence-safe inlined genexps, slot early
  returns).
- Generated oracle + Debug: green (`CFLAGS=-O0`, normal/trace/debug).
- Deterministic fuzz: 48 cases green (`--seed 0xA4F9`).
- Quality-tool suite: 112 tests pass (one expected Valgrind availability skip
  on macOS).
- Focused coverage (post–clean-checkout direct-build regression, Python 3.11):
  466 tests
  traced.
  - backend 74.02%, frontend_seam 28.78%, quality_tools 35.47%.
  - CI floors remain 71%, 25%, and 35%; do not lower them to hide new code.
  - Python 3.14.6: backend 73.20%, frontend seam 28.65%, quality tools
    35.57%; current dual-interpreter floors remain satisfied.
- Fault injection: 128 isolated normal/Debug cases pass sequentially.
- Bounded parallel HPy stress: five full rounds, 640 fault selectors, twenty
  child gates, no timeout or `SystemError`; recursive descendant cleanup is
  unit-tested and one round recurs in CI.
- Fixed-seed supported-surface fuzz: 48 cases pass (`dir()`/`globals()` side
  effects, method-call, Python `type()` surface, plus five M5 reject samples).
- Coverage-guided fuzz: 16 of 64 mutations retained across 16 families and a
  4,075-line compiler frontier; normal/Debug oracle and ABI audits pass.
- Performance gate: generated and handwritten Universal HPy modules pass nine
  versioned runtime budgets, footprint budgets, binary audits, and Debug leak
  checks. CI writes a timestamped JSON history artifact.
- Diagnostic catalog, Python compileall, CI YAML parsing, and `git diff
  --check` pass.
- Clean release artifact: the warning-free, self-contained
  `ahpy_compiler-3.3.0.1.dev0.tar.gz` passes safety/completeness; the no-index
  wheel installs in a new venv with exact HPy 0.9.0/setuptools 80.9.0; the
  frontend and maintained PEP 517 example pass normal/Debug plus verified
  uninstall/reinstall. CI execution is declared; hosted evidence is pending.

The generated runtime, fault, fuzz, reproducibility, setuptools/wheel,
portability, sanitizer declarations, and CPython semantic oracles have dedicated
tools under `Tools/ahpy/`. Do not replace them with Python-only unit assertions.

## 3b. Unified coverage track — authorize options 1 + 3

Normative checklist remains `TODO.md`. This section is the operational order
agents must follow after A1. HPy 0.9 API gaps stay `blocked`/`rejected` with
actionable diagnostics until a newer selected HPy exposes a public surface.
Externally blocked M8/M11 items stay open until the user supplies hosting or
authorization; do not invent greens.

### Phase U0 — Lock HPy 0.9 hard gaps (diagnose-only; no emulation)

Keep and defend strict diagnostics for every item. Do not implement approximate
fallbacks. Update support/validation matrices when diagnostics or messages
change.

1. Set literals / set mutation — no public SetType / set construction API.
2. Generic iterator protocol (`GetIter` / `IterNext`) and pure-type
   `__iter__` / `__next__` slots.
3. Full exception-state handlers: `except as`, reraise, traceback/cause/
   chaining, `else`/`finally`, nested/nonterminal handlers.
4. Portable `__dict__` / `__weakref__` layout; context-bearing `__dealloc__`.
5. Attribute / descriptor / async type slots missing from HPy 0.9 enums.
6. Code-object caches and Python function introspection for HPy methods.
7. Safe mutable `HPyGlobal` under multi-interpreter isolation; immediate
   failed-import retry without an explicit GC boundary (document upstream gap).
8. Hybrid ABI, `cpython.*`, `PyObject *`, and NumPy/third-party C-API without
   a Universal path.

### Phase U1 — Local HPy 0.9 max semantic surface (do next, in order)

Corresponds to section 5 below; every item needs supported+rejected examples,
ownership/cleanup, normal/Debug/failure oracles, support-matrix update, and
audit/changelog fragments in the same change.

1. Context/cleanup on every remaining exit and Python-interacting utility;
   keep pure-C helpers context-free. Include break/continue body-temp cleanup
   and return/raise-from-loop lifetime safety. **(done for loop/conditional/
   assert/range lane)**
2. Remaining value/container expressions; refuse sets until public API exists.
   **(U1 closable pack done: `dir`/`globals`/`SortedDictKeys`/reject-duplicates/
   imag cache/inlined sequence genexp; sets/GetIter still refused)**
3. Direct method-call layout optimization after evaluation-order parity tests.
   **(done: `HPy_CallMethod` with receiver as `args[0]`; eval-order oracle and
   fault injection cover the new family)**
4. Mixed terminating/continuing branches; return/raise from loops; keep
   generic iterators blocked on HPy 0.9. **(done for module functions + slot
   early-return unification; GetIter still blocked)**
5. Effectful default evaluation order; keep general handlers blocked on HPy
   0.9 exception-state. **(defaults done; richer terminal try/except lane
   done; `except as`/else/finally still blocked)**
6. Expand generated runtime corpus and intermediate API failure coverage.
   **(done for U1 closable pack plus dir/globals/method-call/Python-type fuzz
   templates and five new M5 reject corpus samples; hosted expansion remains
   open)**
7. Richer global/type/default caches; keep code-object caches blocked.
   **(imag/complex constant cache done; code objects still blocked)**
8. Document or close failed-import-without-GC with evidence.
   **(done as documented upstream/loader gap; immediate retry without GC remains
   blocked on HPy 0.9)**
9. Remaining M5 type constructors/slots/native typed-C operators/getset/
   MI/cross-module/builtin bases/metaclasses/var-size/freelist/callable
   `__new__` gates; keep weakref/`__dict__`/iter slots rejected on 0.9.
   **(compile-time diagnostics added for freelist, multiple inheritance,
   metaclass, variable-size layout, and existing `__dealloc__` wall; slot early
   returns done for len/bool/hash/contains/call/property)**
10. Close M5 local GC/clear/finalize/resurrection stress; hosted
    all-interpreter promotion waits on Phase U2.
    **(local cycle/finalize/resurrect/field-clear oracle green on Python
    3.11; hosted promotion open)**

### Phase U2 — M8 evidence and native memory (continue M8 without false claims)

A1 is done. Proceed when unblocked:

- A2 hosted platform/compiler matrix — origin/push prerequisite complete;
  inspect and repair the first hosted run before promoting any support claim.
  **(first push run `29490348041` failed before checkout because seven
  `actions/upload-artifact` references used a 39-character SHA; all occurrences
  now use the full upstream 40-character commit and a workflow-wide regression
  test rejects shortened external action pins. Replacement run `29490936993`
  then exposed a clean-checkout import failure in the direct-build CLI; the CLI
  now derives the repository root from its own file and a cwd/PYTHONPATH-isolated
  subprocess regression guards that contract. Hosted rerun evidence pending.)**
- A3 same-binary PyPy/GraalPy hosted hashes — blocked until hosted jobs.
- A4 nightly contract tests / wording guards (local remaining pieces).
  **(manifest status-set guards, stable-vs-nightly separation, hosted-pending
  wording checks, ASan `detect_leaks=0` documentation, and nightly job
  contract tests are local-green; hosted evidence remains open)**
- A5 Linux LSan/Valgrind positive-control lane; Windows AppVerifier when a
  Windows environment exists.
  **(the schedule/manual Linux job now makes the positive control and all five
  real generated-corpus runtime processes mandatory under Valgrind; it remains
  allowed-failure/hosted-pending until suppression review and a first green.
  Windows remains open.)**
- A6 package reproducibility — after Phase U3 Universal packaging formats.

### Phase U3 — M6 advanced families (one gated family at a time)

Ownership/context/storage design first; then section 6 items 1–10. No default-
enabled partial support.

### Phase U4 — M7 packaging and onboarding

Section 7 items 1–7, including PEP 517, Meson/CMake, Universal wheel tags only
after HPy/PyPA standardize them, clean sdist/install, and new-user scripts.
**(local clean sdist, offline wheel/install, frontend/example
uninstall/reinstall, normal/Debug, and documented new-user execution are now
green; frontend archives are byte-reproducible; publication, standardized
tags, cross-interpreter package installation, standardized Universal
extension-wheel reproducibility, and hosted evidence remain open.)**

### Phase U5 — M9 performance, M10 pilots, M11 upstreaming/release

Section 8 items 1–9 plus the stable-release definition in `TODO.md`. Tag no
stable release until every declared support-tier gate is green.

## 4. Immediate queue — finish M8 without false claims

Work on these in order unless an earlier dependency is externally blocked.
After A1, prefer Phase U1 local semantic work while A2/A3 remain externally
blocked.

### A1. Resolve the parallel fault-gate transient — completed

Current evidence:

- The mandatory sequential 128-case fault gate is green.
- An earlier ad-hoc run concurrent with three independent HPy build gates once
  raised import `SystemError` without an active exception.
- A new first parallel round completed fault, setuptools, and fuzz successfully;
  the generated corpus result was not captured after the tool wait window.
- A second four-way round did not complete within two minutes and its
  orchestration was terminated. That orchestration left two generated-corpus
  process trees alive because it did not own/terminate their process groups;
  they were identified and explicitly cleaned up.
- A clean single generated-corpus retry showed that Apple Clang can spend more
  than 4 minutes 36 seconds of CPU compiling the large `bootstrap_types.c` at
  `-O3`. A two-minute timeout is therefore invalid evidence of a hang.
  That was the last point at which parallel safety was unproven; the bounded
  O0 stress profile below then proved five clean concurrent rounds. Ordinary
  O3 compile time was then tracked as a separate M9 debt.

Required next implementation:

- Add a bounded `Tools/ahpy/stress_parallel_hpy.py` runner instead of relying
  on shell/background orchestration.
- Launch fault injection, generated corpus, setuptools integration, and fixed
  fuzz in separate process groups with unique temporary roots.
- Give every child an explicit timeout, continuously retain stdout/stderr,
  terminate the entire child process group on timeout, and report the exact
  command/round/exit/signal.
- Calibrate the timeout above a measured clean single-run upper bound, or use a
  documented stress-only native optimization profile that preserves the
  runtime/failure semantics under test. Never label a known-long O3 compile as
  hung merely because it crossed an arbitrary short timeout.
- Add unit tests for success, nonzero exit, timeout, output retention, and
  deterministic command construction.
- Run at least five consecutive local rounds. If a failure occurs, preserve the
  smallest reproduction and diagnose it; do not merely increase the timeout.
- Re-run the sequential fault and generated gates after stress.
- Only then classify the TODO item as fixed, reproducible external HPy defect,
  bounded resource-pressure limitation, or non-reproduced with quantified
  evidence. Update `TODO.md`, the validation matrix, and an M8 audit together.

Acceptance result: five bounded rounds finished with every child exit code
zero, no timeout, and all 640 fault selectors. The subsequent sequential
128-case fault gate passed. The generated corpus also passed five times in the
stress profile. A post-stress ordinary O3 retry remained inside Apple Clang's
`bootstrap_types.c` optimization beyond 15 minutes and was terminated/reaped;
  that historical run was not green. A later isolated, single-compiler M9 gate
  regenerated the current 4.98 MB/87,259-line corpus and measured Apple Clang
  21 at 1.59 seconds `-O0` and 5.29 seconds `-O3`; both are now guarded by a
  60-second per-profile liveness ceiling. The earlier >15-minute state is not
  reproducible in a single-compiler run. During the first borrowed-handle
  validation, accidentally launching the same full-corpus command twice made
  two `bootstrap_answer.c -O3` compiler processes exceed four CPU minutes;
  terminating the older owned process let the bounded O0 semantic rerun finish
  in 10.50 seconds. This directly confirms concurrency as a major trigger,
  while the isolated large-type liveness gate remains the timing authority.

### A2. Hosted platform/compiler matrix

The workflow already declares Linux x64 GCC/Clang, Linux ARM64 GCC, macOS
Intel/ARM64 Clang, and Windows x64 MSVC. The repository and authorized push now
exist; first hosted aHPy run `29490045367` started from commit `39c7c6830`.

- Preserve `origin` as `https://github.com/mburakmmm/aHPy.git` and keep
  `upstream` pointed at official Cython.
- Treat the first run as pending evidence until every required job completes.
- Record run URLs, exact runner images, compiler versions, and artifact hashes.
- Fix failures with focused regressions.
- Promote a platform/compiler only after its required job is green from a clean
  checkout. Remove no mandatory lane to make the matrix green.

### A3. Same-binary PyPy/GraalPy evidence

- Run the declared build-once portability artifact on pinned PyPy 7.3.23 and
  GraalPy 25.1.3 hosted jobs.
- Confirm downloaded `.hpy0` hashes match the CPython-built manifest exactly.
- Resolve failures before removing `continue-on-error`.
- Update `tests/ahpy/interpreters.toml`, support/validation matrices, and an
  audit with hosted URLs. A rebuilt target artifact does not satisfy this gate.

### A4. Nightly early-warning lanes

- Keep branch-tip HPy and interpreter nightlies separate from pinned release
  and development-revision jobs.
- Make them allowed-failure early warnings with explicit labels and reported
  revisions. Never let a moving dependency change stable support implicitly.
- Add workflow-contract tests for separation and support-claim wording.

### A5. Native memory tooling

- Add Linux LSan/Valgrind with reviewed, versioned suppressions for the
  uninstrumented interpreter. Demonstrate that a test leak is detected and a
  clean generated corpus passes.
- Add Windows Application Verifier or a reviewed equivalent with the same
  positive-control principle.
- Do not interpret unrelated interpreter allocations as backend leaks and do
  not count HPy Debug Mode as a substitute for native memory tooling.

### A6. Future package reproducibility

The real `aHPy-compiler` sdist and pure-Python frontend wheel now build
byte-identically in two independent roots with fixed epoch/hash seed,
normalized tar/gzip ownership/time/name metadata, and recorded
Python/platform/build/setuptools provenance. The first gate caught 40 generated
directory/`PKG-INFO` timestamp differences with identical payload content; the
streaming normalizer fixed them. The future standardized Universal extension
wheel still needs its own two-root native compiler/linker/archive gate. The
current `.hpy0` portability artifact and CPython-tagged example wheels do not
complete that future-format item.

## 5. Backend semantic completion queue

After locally actionable M8 work, close the still-open M2–M5 semantic parents
in this order. For every item, first write a supported and rejected example,
then implement ownership/cleanup, then execute normal/Debug/failure oracles.

1. Complete context/cleanup propagation through every remaining
   Python-interacting utility and all return/break/continue/goto/exception
   exits; keep provably pure-C helpers context-free.
   - Done for loop break/continue body-temp cleanup, return/raise from loops,
     mixed terminating/continuing branches, bootstrap `ctx` threading, and the
     documented Universal policy of not consuming `Cython/Utility/*.c`.
2. Expand M3 expressions and containers: remaining values and constant caches,
   set literals only when the selected public HPy API supports them, and no
   private API emulation.
   - Ellipsis, f-strings, walrus, sequence unpacking, list/dict
     comprehensions, dynamic sequence-index `for`/comps, `assert`,
     counted `range`/`for-from`, None/bool/int/float constant caches,
     local/argument `del`, and function-scope `locals()`/`vars()` are done;
     other ExprNodes remain.
3. Add direct method-call layout optimization only after identical evaluation
   order, exception, and ownership tests exist.
   - Done via `HPy_CallMethod` with receiver as `args[0]`.
4. Generalize structured control flow: mixed terminating/continuing branches,
   return/raise from loops, and generic iterator-protocol loops when supported.
   - Mixed branches, return/raise from loops, dynamic sequence-index
     `for`/comps, `assert`, and counted `range`/`for-from` are done; true
     GetIter/IterNext iterators remain HPy 0.9 blocked.
5. Generalize defaults and handlers: effectful default evaluation order,
   general handler bodies, `except as`, reraise, traceback/cause/chaining only
   with a valid public HPy exception-state model. Keep unavailable semantics
   rejected rather than approximated.
   - Effectful defaults are done (type defaults before type publish; module
     defaults after imports/assignments). `__defaults__` introspection and
     general exception-state handlers remain HPy 0.9 blocked.
6. Expand the generated runtime corpus to the full implemented semantic surface
   and cover every intermediate API/allocation failure.
7. Port richer global/type/default caches. Keep code-object caches explicitly
   blocked while HPy 0.9 lacks public creation/introspection support.
   - Module literal caches now cover Unicode/bytes/tuple/None/bool/int/float;
     code-object caches remain blocked.
8. Make immediate failed-import retry deterministic without requiring an
   explicit garbage collection, if the public HPy/module loader model permits
   it; otherwise document the minimal upstream gap.
9. Complete remaining pure-type constructors, special slots, native operators,
   custom get/set definitions, weak-reference policy, multiple/cross-module
   inheritance, built-in base shapes, metaclasses, variable-size-layout
   diagnostics, freelist policy, and callable custom-`__new__` gates.
10. Close the extension-type milestone only after cyclic GC, clearing,
    finalization, resurrection, weak-reference, and all-interpreter stress gates
    are clean.
    **(local cyclic GC, field-clear, finalize, and resurrection oracle green;
    hosted all-interpreter promotion remains open)**

## 6. Advanced feature queue

Do not start these before their ownership/context/storage designs are written.
Implement one independently gated family at a time:

1. Closures and captured Python values.
   **(one-level nested `def` slice green locally: env/callable HPy types,
   `HPyField` captures per ADR 0005, shared sibling-capture union, capture-free
   envs, mutation visibility, runtime oracles, and explicit C-typed-capture
   rejection; normal/Trace/Debug generated corpus is green. Nested-nested,
   defaults, starargs, generators, and decorators remain rejected)**.
2. Generators and generator cleanup.
   **(ADR 0006 and source-located HPy 0.9 diagnostics now cover top-level
   `yield`, `yield from`, and real generator expressions. Implementation stays
   blocked on public iterator-next slots and iterator/exception-state APIs;
   CPython coroutine utilities are forbidden.)**
3. Native coroutines, `async`/`await`, and async generators.
   **(ADR 0007 and source-located HPy 0.9 diagnostics cover native coroutine
   and async-generator functions. Implementation is blocked on public async
   protocol slots and exception-state/cancellation operations.)**
4. Buffer acquire/release and typed memoryviews.
   **(ADR 0008 separates HPy 0.9's available producer slots from its missing
   public consumer API. Typed buffer/memoryview arguments now fail early with
   one actionable diagnostic before CPython MemoryView utilities run; producer
   implementation remains open.)**
5. Fused types and specialization dispatch.
   **(ADR 0009 defines neutral specialization descriptors, a pure-HPy
   callable/subscriptable dispatcher, typed conversion, and interpreter-owned
   metadata. Fused `def`/`cpdef` now fail closed before CPython fused-function
   machinery; implementation remains open.)**
6. `nogil`, Python-state transitions, exception reacquisition, `prange`,
   OpenMP, synchronization, and free-threading.
   **(ADR 0010 and a runtime-tested first slice now permit only non-empty
   blocks of discarded, argumentless calls to validated external C functions
   declared `noexcept nogil`; emission uses public HPy leave/re-enter APIs and
   a local `HPyThreadState`. Typed arguments/results, nested `with gil`, native
   failures, and callbacks remain open. ADR 0011 now defines the neutral
   parallel plan and native-only worker path; `prange`/`parallel()` fail closed
   because HPy 0.9 has no public arbitrary-worker attach/error transport.
   OpenMP implementation and free-threading remain open.)**
7. C callbacks with Python state, public/API declarations, capsules, and
   cross-module C APIs.
8. C++ exceptions, STL conversions, and RAII interaction with handle cleanup.
9. Profiling/tracing/coverage/monitoring/tracebacks and introspection features.
10. Embedding, multiple embedded HPy modules, NumPy, and third-party C-API
    interoperability policy.

Acceptance for each family: support matrix status, strict diagnostic for every
deferred form, normal/Debug semantics, injected failures, binary audit,
sanitizers where applicable, CPython regression, and no default-enabled partial
implementation.

## 7. Build, packaging, and onboarding queue

1. Define the public non-setuptools/direct-build contract.
   **(completed: `direct_build.py` exposes a versioned plan/API/CLI with exact
   Universal compile/link inputs, safe artifact rules, source/binary audits,
   POSIX/MSVC plan tests, and real public-loader normal/Debug integration;
   hosted stable-matrix executions remain evidence-pending.)**
2. Add a maintained isolated PEP 517 backend/path.
   **(completed locally: `aHPy-compiler` has a separate exact versioned
   identity, `ahpy_build_backend` rejects Cython/unrelated-`ahpy` substitution
   and non-Universal ABI requests, and a real pip-isolated example wheel passes
   source/binary audits plus normal/Debug install execution. The PyPI name is
   not reserved or published; standardized Universal tags remain open.)**
3. Add Meson and CMake/scikit-build-core integrations where applicable.
   **(completed locally: installed `ahpy_build_config` feeds strict CMake and
   Meson contracts; both native examples pass normal/Debug and ABI audits; a
   no-index isolated scikit-build-core wheel also passes pip install/import.
   Hosted Linux/Windows evidence and cross-compilation remain open.)**
4. Adopt Universal wheel naming/tags only after HPy/PyPA standardize them; do
   not publish CPython-tagged wheels as portable.
5. Test clean sdist, isolated wheel, install, uninstall/reinstall, and
   reproducibility in empty environments.
   **(clean sdist safety, no-index wheel-from-sdist, fresh-venv install,
   frontend/example uninstall/absence/reinstall, normal/Debug, and artifact
   hashes and two-root byte reproducibility of the frontend sdist/wheel are
   completed locally; standardized Universal extension-wheel reproducibility
   remains open.)**
6. Add isolated minimal, extension-type, external-C, and packaging examples.
7. Have a new-user clean-environment script execute documentation literally.
   **(completed locally by `release_artifact_integration.py` and
   `docs/ahpy/onboarding.md`; hosted evidence remains open.)**

## 8. Performance, pilots, upstreaming, and release queue

1. Extend the handwritten HPy benchmark reference beyond the current nine
   operations to iteration and memoryviews once those generated Universal
   paths exist. Extension-type creation/method calls and a shared
   Python-independent external-C wrapper now have equivalent generated and
   handwritten references; do not fabricate iteration/memoryview numbers.
2. Keep the completed classic Cython, HPy CPython ABI, and HPy Universal ABI
   benchmark profiles separate; never combine their overheads into one number.
   Add hosted history before enforcing non-Universal release budgets.
3. Record compile time, native compiler time, C size, binary size, peak memory,
   HPy Trace API counts, and handle churn. Optimize duplicate/close pairs only
   after ownership proofs and tests.
   **(Trace measurement completed for all nine comparable operations: exact
   per-API deltas and dup/close churn are in benchmark JSON; arithmetic,
   container, attribute, call, extension-type, and external-C overhead is
   quantified. Separate-clean-process peak RSS, frontend/native build times,
   and source/binary sizes are also recorded. The currently blocked
   iteration/memoryview families remain open; remove no cleanup without
   ownership/failure proofs.)**
   **(The first ownership-proven optimization is complete: benchmark call
   contracts are genuinely positional-only on both sides, and direct live Name
   handles are borrowed for attribute receivers and zero-argument callables.
   Both paths now match the reference at 1 API call/iteration with zero
   Dup/Close churn; normal/Trace/Debug and 128 fault selectors are green.)**
   **(The second ownership-proven optimization is complete: two-or-more
   required positional-only functions use `HPyFunc_VARARGS` without a keyword
   parser/tracker; direct live Names feed borrowing binary and fixed sequence
   builder APIs under a left-to-right evaluation proof. Arithmetic/container
   now match the references at 1/4 API calls with zero Dup/Close churn and
   0.97×/1.07× tightened-budget ratios. Their ceilings are 1.5×; 185 emitter tests,
   normal/Trace/Debug, and 128 fault selectors are green. Closure call slots
   accept empty `**{}` but reject non-empty keywords for no-, one-, and
   multi-argument positional-only nested functions.)**
   **(The third ownership-proven optimization is complete: extension-field
   owners/values stay borrowed under call-lifetime and evaluation-order proofs;
   type/module owners load lazily; positional-only initializers bypass keyword
   trackers. Type creation/method ratios are 1.02×/0.96× under new 1.5×
   ceilings, Trace is 3/2 and 2.003/2.002 calls with zero generated Dup/Close,
   and 186 emitter tests plus normal/Trace/Debug and 128 fault selectors are
   green. Lazy owner names are part of branch lifetime snapshots; the isolated
   4.65 MB large-type C corpus compiles at O0/O3.)**
   **(The fourth ownership-proven optimization is complete: representable
   numeric literals in validated external-C scalar calls emit portable typed C
   literals directly, while dynamic, non-finite, ambiguous `char`, and
   out-of-portable-range values retain checked HPy conversion. External-C
   Trace is now 1/1 call with zero Dup/Close churn, Universal/HPy-CPython
   ratios are 0.99×/1.00×, its ceiling is 1.5×, and 188 emitter tests plus
   normal/Trace/Debug and 128 fault selectors are green.)**
   **(The large-type compile is now isolated in this gate: current Apple Clang
   21 evidence is 1.59 seconds `-O0`, 5.29 seconds `-O3`, ratio 3.32×, under a
   60-second per-profile timeout. Preserve hosted history before tightening.)**
4. Turn the current conservative regression ceilings into release budgets only
   after hosted history exists. Document interpreter/HPy overhead separately
   from backend overhead.
5. Select and report four pilots: pure Cython, Python-independent C wrapper,
   extension type with GC/inheritance, and deliberately blocked CPython/NumPy
   API project. Convert recurring changes into support or migration rules.
6. Publish a compatibility dashboard, porting guide, and issue template; share
   the conformance corpus with the user's language without coupling frontends.
7. Coordinate the backend seam with Cython/HPy maintainers, submit neutral
   refactors as small PRs, maintain a rebase log, and file HPy gaps with minimal
   reproductions.
8. Complete security, support, contributor, debugging, release, provenance,
   limitation, and maintenance-cadence documentation before a release candidate.
9. Tag no stable release until every declared support-tier gate is green.

## 9. Validation commands

Run the smallest relevant gate while iterating, then the complete applicable
set before marking a task complete. Use the exact selected interpreter path.

```console
python3 Tools/ahpy/build_diagnostic_catalog.py --check \
    docs/ahpy/audits/diagnostics-catalog.json
python3 -m compileall -q Cython Tools/ahpy
python3 -c 'import pathlib,yaml; yaml.safe_load(pathlib.Path(".github/workflows/ahpy-universal.yml").read_text())'
git diff --check

.venv-hpy09/bin/python -m unittest \
    Cython.Compiler.Tests.TestHandleModel \
    Cython.Compiler.Tests.TestRuntimeAPI \
    Cython.Compiler.Tests.TestHPyModuleWriter \
    Cython.Compiler.Tests.TestCmdLine \
    Cython.Compiler.Tests.TestCode
.venv-hpy09/bin/python -m unittest discover -s Tools/ahpy -p 'test_*.py'
.venv-hpy09/bin/python Tools/ahpy/report_coverage.py \
    --fail-under backend=71 \
    --fail-under frontend_seam=25 \
    --fail-under quality_tools=35

.venv-hpy09/bin/python Tools/ahpy/test_generated_hpy.py \
    --python .venv-hpy09/bin/python
.venv-hpy09/bin/python Tools/ahpy/direct_build_integration.py \
    --python .venv-hpy09/bin/python
.venv-hpy09/bin/python Tools/ahpy/pep517_integration.py \
    --python .venv-hpy09/bin/python --output /tmp/ahpy-pep517.json
.venv-hpy09/bin/python Tools/ahpy/build_system_integration.py \
    --python .venv-hpy09/bin/python --system all \
    --output /tmp/ahpy-build-systems.json
.venv-hpy09/bin/python Tools/ahpy/scikit_build_integration.py \
    --python .venv-hpy09/bin/python --output /tmp/ahpy-scikit-build.json
.venv-hpy09/bin/python Tools/ahpy/test_fault_injection.py \
    --python .venv-hpy09/bin/python
.venv-hpy09/bin/python Tools/ahpy/fuzz_supported_surface.py \
    --python .venv-hpy09/bin/python --seed 0xA4F9 --cases 48
.venv-hpy09/bin/python Tools/ahpy/coverage_guided_fuzz.py \
    --python .venv-hpy09/bin/python --seed 0xC0A4F9 --candidates 64
.venv-hpy09/bin/python Tools/ahpy/benchmark_hpy.py \
    --python .venv-hpy09/bin/python --output /tmp/ahpy-benchmark.json
.venv-hpy09/bin/python Tools/ahpy/verify_reproducible_artifact.py \
    --python .venv-hpy09/bin/python
.venv-hpy09/bin/python Tools/ahpy/setuptools_integration.py \
    --python .venv-hpy09/bin/python
.venv-hpy09/bin/python runtests.py -vv --backends=c,cpp ahpy_
```

For broad compiler/frontend changes also run the complete upstream Cython test
suite. For native/runtime changes run the applicable sanitizer and hosted
matrix. Do not run unrelated expensive gates concurrently until A1 is resolved.

## 10. Agent completion protocol

At the end of every independently useful change:

1. Confirm the change stayed inside the selected TODO item.
2. Add focused success, rejection, failure-path, and CPython regression tests.
3. Run and record the exact applicable commands and counts.
4. Update `TODO.md`, support/validation documents, changelog fragment, and audit
   in the same change. Never update evidence before the gate actually passes.
5. Update the snapshot and immediate queue in this file if counts, blockers, or
   ordering changed.
6. Run diagnostic-catalog, compileall, YAML, and diff checks.
7. Report remaining unsupported cases and external blockers explicitly.
8. Do not commit, push, open a PR, change remotes, or publish artifacts unless
   the user separately authorizes that external action.

The project is complete only when the stable-release definition in `TODO.md`
is fully true. Exhausted time, a green local subset, or a declared CI job is not
completion.
