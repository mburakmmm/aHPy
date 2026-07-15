# aHPy agent handoff and ordered work queue

This file is the operational handoff for AI agents continuing aHPy. It does
not replace `TODO.md`: that file is the normative, dependency-ordered project
checklist. An agent must update both files when implementation status changes.

## 1. Snapshot and source of truth

- Snapshot date: 2026-07-15 (handoff + coverage-track authorization).
- Workspace: `/Users/melihburakmemis/Documents/aHPy`.
- Branch: `codex/ahpy-bootstrap`.
- Cython base/HEAD: `b99cb0e3b5425e11414cadd24168a6cc850e8000`.
- Stable local environment: `.venv-hpy09`, CPython 3.11.15, HPy 0.9.0.
- Additional local coverage interpreter: `python3`, CPython 3.14.6.
- The worktree intentionally contains the complete uncommitted aHPy
  implementation. Do not reset, clean, overwrite, or discard unrelated files.
- `.DS_Store` and
  `docs/examples/userguide/wrapping_CPlusPlus/rect_with_attributes.cpp` are
  user-owned/unrelated. Leave them untouched.
- No `origin` remote exists yet. Do not invent hosting or claim hosted CI runs.
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

- Focused compiler suite: 323 tests pass (includes U1 closable surface:
  `dir()`/`globals()`/`__dict__`, reject-duplicates keywords, imag constant
  cache, richer terminal try, sequence-safe inlined genexps, slot early
  returns).
- Generated oracle + Debug: green (`CFLAGS=-O0`, normal/trace/debug).
- Deterministic fuzz: 48 cases green (`--seed 0xA4F9`).
- Quality-tool suite: 51 tests pass.
- Focused coverage (post–U1 closable pack, Python 3.11): 382 tests traced.
  - backend 72.82%, frontend_seam 26.20%, quality_tools 41.11%.
  - CI floors remain 71%, 25%, and 35%; do not lower them to hide new code.
  - Prior Python 3.14 snapshot (pre–U1 pack): backend 71.65%, frontend
    seam 25.07%, tools 40.62% — re-measure on 3.14 after large emitter
    deltas before claiming the dual-interpreter floor.
- Fault injection: 116 isolated normal/Debug cases pass sequentially.
- Bounded parallel HPy stress: five full rounds, 580 fault selectors, twenty
  child gates, no timeout or `SystemError`; recursive descendant cleanup is
  unit-tested and one round recurs in CI.
- Fixed-seed supported-surface fuzz: 48 cases pass.
- Coverage-guided fuzz: 16 of 64 mutations retained across 16 families and a
  3,864-line compiler frontier; normal/Debug oracle and ABI audits pass.
- Performance gate: generated and handwritten Universal HPy modules pass six
  versioned runtime budgets, footprint budgets, binary audits, and Debug leak
  checks. CI writes a timestamped JSON history artifact.
- Diagnostic catalog, Python compileall, CI YAML parsing, and `git diff
  --check` pass.

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
4. Mixed terminating/continuing branches; return/raise from loops; keep
   generic iterators blocked on HPy 0.9. **(done for module functions + slot
   early-return unification; GetIter still blocked)**
5. Effectful default evaluation order; keep general handlers blocked on HPy
   0.9 exception-state. **(defaults done; richer terminal try/except lane
   done; `except as`/else/finally still blocked)**
6. Expand generated runtime corpus and intermediate API failure coverage.
   **(closable-pack corpus/oracle/fuzz green; further M3/M5 expansion open)**
7. Richer global/type/default caches; keep code-object caches blocked.
   **(imag/complex constant cache done; code objects still blocked)**
8. Document or close failed-import-without-GC with evidence.
9. Remaining M5 type constructors/slots/native typed-C operators/getset/
   MI/cross-module/builtin bases/metaclasses/var-size/freelist/callable
   `__new__` gates; keep weakref/`__dict__`/iter slots rejected on 0.9.
   **(slot early returns done for len/bool/hash/contains/call/property)**
10. Close M5 local GC/clear/finalize/resurrection stress; hosted
    all-interpreter promotion waits on Phase U2.

### Phase U2 — M8 evidence and native memory (continue M8 without false claims)

A1 is done. Proceed when unblocked:

- A2 hosted platform/compiler matrix — blocked until `origin` + authorized push.
- A3 same-binary PyPy/GraalPy hosted hashes — blocked until hosted jobs.
- A4 nightly contract tests / wording guards (local remaining pieces).
- A5 Linux LSan/Valgrind positive-control lane; Windows AppVerifier when a
  Windows environment exists.
- A6 package reproducibility — after Phase U3 Universal packaging formats.

### Phase U3 — M6 advanced families (one gated family at a time)

Ownership/context/storage design first; then section 6 items 1–10. No default-
enabled partial support.

### Phase U4 — M7 packaging and onboarding

Section 7 items 1–7, including PEP 517, Meson/CMake, Universal wheel tags only
after HPy/PyPA standardize them, clean sdist/install, and new-user scripts.

### Phase U5 — M9 performance, M10 pilots, M11 upstreaming/release

Section 8 items 1–9 plus the stable-release definition in `TODO.md`. Tag no
stable release until every declared support-tier gate is green.

## 4. Immediate queue — finish M8 without false claims

Work on these in order unless an earlier dependency is externally blocked.
After A1, prefer Phase U1 local semantic work while A2/A3 remain externally
blocked.

### A1. Resolve the parallel fault-gate transient — completed

Current evidence:

- The mandatory sequential 116-case fault gate is green.
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
  Parallel safety is still not proven.

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
zero, no timeout, and all 580 fault selectors. The subsequent sequential
116-case fault gate passed. The generated corpus also passed five times in the
stress profile. A post-stress ordinary O3 retry remained inside Apple Clang's
`bootstrap_types.c` optimization beyond 15 minutes and was terminated/reaped;
do not call that run green. Ordinary O3 validation and its compile-time budget
remain independent release/M9 gates.

### A2. Hosted platform/compiler matrix

The workflow already declares Linux x64 GCC/Clang, Linux ARM64 GCC, macOS
Intel/ARM64 Clang, and Windows x64 MSVC. This task requires an actual hosted
repository and is externally blocked until the user supplies/authorizes it.

- Add `origin` only after the real hosting URL exists.
- Push through an authorized workflow; never infer permission.
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

This depends on the packaging work in section 7. Once real aHPy sdist and
Universal wheel formats exist, build each twice in independent roots with
normalized timestamps, archive metadata, file/debug prefix maps, and provenance;
require byte-identical content. The current `.hpy0` portability artifact gate
does not complete this future-format item.

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

## 6. Advanced feature queue

Do not start these before their ownership/context/storage designs are written.
Implement one independently gated family at a time:

1. Closures and captured Python values.
2. Generators and generator cleanup.
3. Native coroutines, `async`/`await`, and async generators.
4. Buffer acquire/release and typed memoryviews.
5. Fused types and specialization dispatch.
6. `nogil`, Python-state transitions, exception reacquisition, `prange`,
   OpenMP, synchronization, and free-threading.
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
2. Add a maintained isolated PEP 517 backend/path.
3. Add Meson and CMake/scikit-build-core integrations where applicable.
4. Adopt Universal wheel naming/tags only after HPy/PyPA standardize them; do
   not publish CPython-tagged wheels as portable.
5. Test clean sdist, isolated wheel, install, uninstall/reinstall, and
   reproducibility in empty environments.
6. Add isolated minimal, extension-type, external-C, and packaging examples.
7. Have a new-user clean-environment script execute documentation literally.

## 8. Performance, pilots, upstreaming, and release queue

1. Extend the handwritten HPy benchmark reference beyond the current six
   operations to types, iteration, memoryviews, and external-C wrappers.
2. Compare classic Cython, HPy CPython ABI, and HPy Universal ABI separately;
   never combine their overheads into one number.
3. Record compile time, native compiler time, C size, binary size, peak memory,
   HPy Trace API counts, and handle churn. Optimize duplicate/close pairs only
   after ownership proofs and tests.
   Start by isolating why Apple Clang `-O3` on the generated type corpus exceeds
   15 minutes while the same O0 stress build finishes in 10.40–13.81 seconds.
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
