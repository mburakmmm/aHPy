# aHPy agent handoff and ordered work queue

This file is the operational handoff for AI agents continuing aHPy. It does
not replace `TODO.md`: that file is the normative, dependency-ordered project
checklist. `production-todo.md` is the release-readiness execution order. An
agent must keep all three synchronized when implementation status changes.

## 1. Snapshot and source of truth

- PRD-8 evidence reconciliation (2026-09-05): hosted run `31794650087`,
  artifact `9216896185`, and all four pilot JSON reports were revalidated.
  `docs/ahpy/compatibility-dashboard.md` reproduces the hosted artifact byte
  for byte; inputs are retained under `docs/ahpy/audits/evidence/` with hashes
  and scope limits in `m10-hosted-pilot-evidence.md`. Port results are cypack
  pass, murmurhash/frozenlist partial, bezier blocked. Release budgets and
  full upstream-library API compatibility are not implied.
- Current continuation (2026-09-06): PR #2 merged the complete aHPy line into
  `main` as `22d8cbe1b50506f65e01be7ff05081616c656f2d`. Its final source commit
  `880d46d7d348df759ef062711ab3b4876bd648b8` passed all five required
  contexts, including the repaired Python 3.9 Limited API selection. Manual
  performance calibration run `34029830808` is collecting five isolated
  hosted samples from that exact main commit. Continue PRD-7 by reviewing its
  immutable raw artifacts and proposal; never promote the proposed budgets
  automatically.
- Snapshot date: 2026-08-14 (Cursor/Codex continuation, writable scalar and
  fixed-array buffer producer slices, handwritten-first cross-interpreter
  evidence, dynamic fault-count reporting, and local coverage audited and
  reconciled).
- Workspace: `/Users/melihburakmemis/Documents/aHPy`.
- Integration branch: `codex/ahpy-bootstrap` (merged into `main` by PR #2).
- Current evidence branch: `codex/production-evidence`, based on
  `22d8cbe1b50506f65e01be7ff05081616c656f2d`.
- Upstream Cython baseline: `86b94cef002aa23aea0b390335ea3d9e9b62c19e`.
- The accepted base was merged as
  `a1dc62c0084cc426090b38137eefb3c9ef82dcab` with the exact two parents and
  six conflict decisions recorded in
  `docs/ahpy/audits/current-cython-rebase-2026-08-12.md`; the clean release
  artifact gate is green on that commit, while hosted runs `31590065924`,
  `31590065944`, `31590065930`, `31590066370`, `31590066388`, and
  `31590065928` remain pending/queued under the Actions quota.
- The first post-merge full C/C++ developer run exposed and repaired two
  defects already present in accepted upstream HEAD: astral-Unicode source
  encoding compared a character with an integer, and non-reference C++
  template deduction failed to apply function-to-pointer decay. Independent
  compiler regressions pass in both C and C++ selections. The authoritative
  `CI=1` macOS profile selected 22,025 tests across four partitions: 21,847
  passed, 178 followed upstream skip contracts, and the command exited zero.
- A subsequent fresh four-pilot rerun exposed current Cython's exact-`str`
  `PyTypeTestNode` around `str.format()` results. Universal generation now
  implements only that proven runtime check through public HPy and keeps all
  other type-test families fail-closed. The generated normal/Trace/Debug
  oracle, frozenlist pilot, complete pilot dashboard and dual-interpreter
  focused coverage pass after the repair.
- Hosted checks for remote HEAD `2924030e7015fecd536987393c6106c6da85e999`
  exposed three fork-integration defects in addition to that pilot failure:
  the upstream CI changelog probe assumed a Cython-named distribution,
  `setup_minimal.py` required HPy during ordinary C/C++/pydebug imports, and
  codespell interpreted the MSVC `/Iinclude` oracle as prose. The current
  local tree repairs all four roots; 441 compiler/seam tests, 532 quality-tool
  tests, focused C/C++ fixture import, dual-interpreter coverage, and generated
  Universal normal/Trace/Debug execution pass. Hosted same-HEAD confirmation
  remains mandatory after commit and push.
- Last fully green dedicated-aHPy reference:
  `20e401ca71a0440ed91e9b6f9d083f3d6a24ef25`; always obtain the live branch
  HEAD with `git rev-parse HEAD` before reporting or changing evidence.
- Stable local environment: `.venv-hpy09`, CPython 3.11.15, HPy 0.9.0.
- Additional local coverage interpreter: `/tmp/ahpy-docdeps314/bin/python`,
  CPython 3.14.2 with the current documentation dependency lock.
- The dedicated aHPy and sanitizer sets are verified through `20e401ca7`;
  the last complete coverage set is verified through `b8dc12f67`. Preserve
  later user/agent work and do not reset, clean, overwrite, or discard it.
- `.DS_Store` and
  `docs/examples/userguide/wrapping_CPlusPlus/rect_with_attributes.cpp` are
  user-owned/unrelated. Leave them untouched.
- `origin` is `https://github.com/mburakmmm/aHPy.git`; `main` now contains the
  aHPy integration, and merged PR
  [#2](https://github.com/mburakmmm/aHPy/pull/2) retains its full review and
  required-check history.
- Live repository ruleset
  [19886870](https://github.com/mburakmmm/aHPy/rules/19886870) protects `main`
  and future `ahpy/**` release branches without bypass actors. It requires
  pull requests, resolved review threads, deletion/non-fast-forward
  protection, and the five GitHub Actions contexts declared in
  `tests/ahpy/ci-policy.toml`, all bound to Actions integration ID `15368`.
- At pre-repair HEAD `cfbd94b64475306036a11474d5cc587ab9bf8ac6`, dedicated
  aHPy run
  [29905497837](https://github.com/mburakmmm/aHPy/actions/runs/29905497837),
  coverage run
  [29905497811](https://github.com/mburakmmm/aHPy/actions/runs/29905497811),
  and sanitizer run
  [29905498058](https://github.com/mburakmmm/aHPy/actions/runs/29905498058)
  are green. General Cython run
  [29905498043](https://github.com/mburakmmm/aHPy/actions/runs/29905498043)
  confirmed the GraalPy fixture isolation but reproduced Windows/MSVC
  `LNK1158` inside `shared_utility_module`: its own `build_ext -j3` overlapped
  the bounded four-worker outer pool. The stronger local repair excludes both
  `tag:shared_utility` trees from that pool and runs them alone while retaining
  their internal parallel build. Replacement hosted confirmation remains
  mandatory; do not call the complete matrix green before it lands.
- Later full Cython run
  [30439469712](https://github.com/mburakmmm/aHPy/actions/runs/30439469712)
  at `b173e6f3797298723d8b5c325a68ad5d5aa6e577` proved that outer isolation
  alone is still insufficient: isolated Windows C++/Python 3.11 job
  [90542124435](https://github.com/mburakmmm/aHPy/actions/runs/30439469712/job/90542124435)
  reproduced `LNK1158` inside the fixture's own `build_ext -j3`. The current
  local repair changes all eight shared-utility fixture builds to `-j1` while
  retaining separate parallel-build coverage elsewhere; both real local
  shared-utility trees and the quality contract pass. Replacement hosted
  confirmation remains mandatory.
- User mandate (2026-07-15): complete **HPy 0.9 max Universal coverage** and the
  **full M2–M11 roadmap** (options 1+3). Work the ordered queues below; never
  mark a HPy-0.9 API gap as supported; never claim hosted lanes without green
  hosted evidence.

Read these before changing code:

1. `TODO.md` — normative scope, dependencies, and exit gates.
2. `production-todo.md` — ordered production and release gates.
3. `docs/ahpy/README.md` — project contract.
4. `docs/ahpy/support-matrix.md` — current support claims.
5. `tests/ahpy/ci-policy.toml` — machine-readable workflow/job policy.
6. `.github/rulesets/production-branches.json` — live ruleset source.
7. `docs/ahpy/validation-matrix.md` — actual validation evidence.
8. `docs/ahpy/adr/` — architecture and release decisions.
9. The milestone audit matching the code being changed in
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

- Focused compiler suite: 441 tests pass (includes U1 closable surface,
  writable scalar/fixed-array buffer producers, and
  closure-registry regressions:
  `dir()`/`globals()`/`__dict__`, reject-duplicates keywords, imag constant
  cache, richer terminal try, sequence-safe inlined genexps, slot early
  returns).
- Full upstream macOS C/C++ profile after the current Cython rebase repairs:
  22,025 selected, 21,847 passed and 178 skipped by upstream
  platform/dependency contracts (`CI=1`, four workers, exit zero).
- Generated oracle + Debug: green (`CFLAGS=-O0`, normal/trace/debug).
- Deterministic fuzz: 48 cases green (`--seed 0xA4F9`).
- Quality-tool suite: 532 tests pass (two expected platform/tool availability
  skips on macOS).
- Focused coverage (2026-08-12): 971 tests traced on both interpreters.
  - CPython 3.11: backend 9614/9614 (100.00%), frontend_seam 52.89%,
    quality_tools 9430/9430 (100.00%).
  - CPython 3.14.2: backend 9500/9500 (100.00%), frontend_seam 53.02%,
    quality_tools 9439/9439 (100.00%).
  - CI floors are 100%, 45%, and 100%; do not lower them to hide new code.
  - Full backend coverage means executable Python lines in
    `HPyModuleWriter.py`, `HandleModel.py`, and `RuntimeAPI.py`; native and
    generated-C behavior remains governed by its dedicated gates.
- Fault injection: 150 isolated normal/Debug cases pass sequentially, including
  scalar and fixed-array buffer exporter `HPy_Dup` failure/one-past boundaries.
- Bounded parallel HPy stress: five full rounds, 750 fault selectors, twenty
  child gates, no timeout or `SystemError`; recursive descendant cleanup is
  unit-tested and one round recurs in CI.
- Fixed-seed supported-surface fuzz: 48 cases pass (`dir()`/`globals()` side
  effects, method-call, Python `type()` surface, plus five M5 reject samples).
- Coverage-guided fuzz: 16 of 64 mutations retained across 16 families and a
  4,141-line compiler frontier; normal/Debug oracle and ABI audits pass.
- Performance gate: generated and handwritten Universal HPy modules pass ten
  versioned runtime budgets, footprint budgets, binary audits, and Debug leak
  checks. CI writes a timestamped JSON history artifact.
- Diagnostic catalog, Python compileall, CI YAML parsing, and `git diff
  --check` pass.
- The build-once portability artifact now contains the frontend-independent
  handwritten `ahpy_minimal` oracle followed by constant-only, single-function,
  heap-type and large function-corpus generated rungs. All ten isolated stages
  pass locally on CPython 3.11/HPy 0.9. Hosted run `31573340325` proved the
  handwritten oracle on PyPy before the old artifact crashed at
  `import-answer`, while GraalPy failed native discovery at `import-minimal`;
  rerun the ten-stage ladder to narrow PyPy further. The smoke writes verified
  hashes, provenance, ordered stdout/stderr and exit/signal classification to
  JSON even on failure; CI uploads it with `if: always()`.
- Clean release artifact: the warning-free, self-contained
  `ahpy_compiler-3.3.0.1.dev0.tar.gz` now requires unchanged committed release
  inputs and proves every non-generated member is tracked and byte-identical;
  its six-component license/SBOM evidence and all artifact hashes are
  independently required by the no-upload publisher. The no-index
  wheel installs in a new venv with exact HPy 0.9.0/setuptools 83.0.0; the
  frontend and maintained PEP 517 example pass normal/Debug plus verified
  uninstall/reinstall. Exact clean commit `3f30148ca` locally passed all 736
  sdist-member checks and TestPyPI no-upload selection on 2026-08-12. Hosted
  Linux execution is historical-green in run `29685285138`; current-HEAD
  replacement evidence remains pending quota.

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
   returns done for len/bool/hash/contains/call/property; slotless
   `__format__`/`__bytes__`/`__complex__`/`__round__` and synchronous
   `__enter__`/`__exit__` methods green)**
10. Close M5 local GC/clear/finalize/resurrection stress; hosted
    all-interpreter promotion waits on Phase U2.
    **(local cycle/finalize/resurrect/field-clear oracle green on Python
    3.11; hosted promotion open)**

### Phase U2 — M8 evidence and native memory (continue M8 without false claims)

A1 is done. Proceed when unblocked:

- A2 hosted platform/compiler matrix — complete for the initial stable
  CPython 3.11/HPy 0.9 baseline.
  **(push run `29685285138` is green for all six Linux/macOS/Windows compiler
  jobs, both sanitizer jobs, pinned HPy development on Python 3.11, portability,
  and compiler/quality. Exact URLs, runner images, compiler versions, and
  binary hashes are recorded in `docs/ahpy/audits/m8-platform-ci-repairs.md`.)**
- A3 same-binary PyPy/GraalPy hosted hashes — evidence captured; compatibility
  remains blocked on the target runtimes.
  **(run `29685285138` revalidated the unchanged artifact hashes, then PyPy
  terminated at its first bundled-bridge import and GraalPy reported no bridge
  or native `.hpy0` import hook. Both remain allowed-failure early warnings.)**
- A4 nightly contract tests / wording guards (local remaining pieces).
  **(manifest status-set guards, stable-vs-nightly separation, support wording,
  ASan `detect_leaks=0`, 30-minute runtime bounds, and nightly job contracts
  are local-green. Manual run `29906185775` records HPy 0.9 failing to build on
  CPython 3.15.0-beta.4 before aHPy and HPy master resolving to the pinned
  `b57a33c1...` commit before its missing `-O0` profile caused an optimized
  build hang. Both runtime steps now use `-O0` plus a 30-minute bound. Manual
  run `29912162645`, job `88897432348`, is the first bounded green HPy-master
  execution (19-second runtime); the CPython 3.15/HPy 0.9 lane remains
  externally red.)**
- A5 Linux LSan/Valgrind positive-control lane; Windows AppVerifier when a
  Windows environment exists.
  **(Linux is promoted: manual run `29906185775`, job `88878105102`, detected
  the 64-byte positive control, recorded five clean real-corpus logs, and used
  no active suppression. Its schedule/manual job is now required. Windows is
  also promoted: manual run `30431371077`, job `90509136349`, proved full-page
  heap, the native-overrun positive control, verifier injection in all five
  clean real-corpus processes, and successful cleanup.)**
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
extension-wheel reproducibility remain open; hosted Linux packaging is green
in run `29685285138`.)**

### Phase U5 — M9 performance, M10 pilots, M11 upstreaming/release

Section 8 items 1–9 plus the stable-release definition in `TODO.md`. Tag no
stable release until every declared support-tier gate is green.

## 4. Immediate queue — production-readiness closure order

Work on these in order unless an earlier dependency is externally blocked.
This list is the operational priority view; the detailed acceptance criteria
remain in the phase and milestone sections below and in `TODO.md`.

1. PRD-0 is closed: all five required aggregate contexts passed on final
   source commit `880d46d7d348df759ef062711ab3b4876bd648b8`, and PR #2 merged as
   `22d8cbe1b50506f65e01be7ff05081616c656f2d`.
2. Freeze PRD-1's first-release support contract: exact Cython/HPy/Python
   revisions, OS/compiler/build-frontend matrix, product tier, status
   vocabulary, and HPy public-API limitations.
3. Close PRD-2 and PRD-3 for the declared release scope: core
   ownership/cleanup/module-state and pure HPy extension-type/GC/finalizer
   correctness, including normal/Trace/Debug and fault paths.
4. Resolve every PRD-4 advanced family independently: fully implement and
   prove it or reject it fail-closed with a source-located diagnostic and
   migration guidance.
5. Complete PRD-5 cross-interpreter, platform, compiler, sanitizer, and
   native-memory evidence without promoting PyPy/GraalPy or moving nightlies
   before real green hosted proof.
6. Complete PRD-6 and PRD-7 packaging, reproducibility, provenance,
   publication rehearsal, performance, and footprint gates.
7. Complete PRD-8's four real-world pilots, compatibility dashboard, porting
   guide, and shared conformance corpus for the author's language runtime.
8. Complete PRD-9 upstream/rebase, security, maintenance, and ownership
   obligations.
9. Complete PRD-10 release-candidate and stable-release gates. Do not merge the
   draft PR or tag a stable release without explicit user authorization and
   every declared release gate green.

Current item: **PRD-7 hosted release-performance calibration**. Run
`34029830808` binds five isolated samples to exact main commit
`22d8cbe1b50506f65e01be7ff05081616c656f2d`; review every raw artifact and
the proposal before versioning any ceiling. PRD-5 remains externally open
only for publication of the exact HPy Python 3.14 upstream crash report.
PRD-0 CI-policy implementation head
`e791c8983bcb1a3c38aa932617a91ea976cb5c55` has green aHPy, benchmark,
coverage, and sanitizer required aggregates. HPy development on Python 3.14
and same-binary PyPy/GraalPy remain the three expected allowed failures. Its
full Cython graph found a PyPy 3.9-only fixture error before backend execution:
`SimpleNamespace(self=...)` conflicts with PyPy's named receiver. Replacement
commit `1b3805e30` assigns the same AST field after construction and passes all
248 `TestHPyModuleWriter` tests under both local CPython and PyPy, plus the
full 431 compiler and 153 quality suites under CPython. Roadmap HEAD
`7ad48c495e9410ec1aa0ab28cdd2a7201282e991` exposed a cold-cache capacity
failure rather than a test assertion: Ubuntu shared-utility C++ job
`90261190485` continued compiling and passing tests until its 80-minute
timeout, with only 19.78% ccache hits and seven outer workers. The local repair
bounds non-Windows shared-utility mode to four outer workers and gives only
that heavy lane a 120-minute fail-closed ceiling; its focused regression and
all 153 quality tests pass. Repair HEAD
`8ed77677ee6bd69fdc93a81bdfe3e704ea7d924b` now has green
[`aHPy required checks` job 90283757405](https://github.com/mburakmmm/aHPy/actions/runs/30361153504/job/90283757405),
[`benchmark required checks` job 90296401321](https://github.com/mburakmmm/aHPy/actions/runs/30361153497/job/90296401321),
[`coverage required checks` job 90291908521](https://github.com/mburakmmm/aHPy/actions/runs/30361153526/job/90291908521),
and
[`sanitizers-success` job 90296760091](https://github.com/mburakmmm/aHPy/actions/runs/30361153809/job/90296760091).
The repaired shared-utility C++ job `90281110328` passed in 14m39s, PyPy 3.9
job `90288783333` is green, and the complete 103-job Cython graph passed with
[`ci-success` job 90328870116](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90328870116).
All five required contexts are therefore green on the same repair HEAD, and
the final evidence is published in the repository documentation and draft PR.
PRD-0 is closed. PRD-1 freezes an unpublished `preview` in
`tests/ahpy/release-contract.toml`: `aHPy-compiler==3.3.0.1.dev0`, Cython
`3.3.0b1` at base `86b94cef002aa23aea0b390335ea3d9e9b62c19e`,
CPython 3.11, HPy 0.9.0/setuptools 83.0.0, and the six hosted
platform/compiler lanes. The compiler CLI is supported within the documented
source subset; direct build, setuptools/cythonize, PEP 517, CMake, Meson, and
scikit-build-core retain exact partial scopes. The separate
known-limitations document locks HPy 0.9 gaps, and a quality test prevents
manifest/code/CI/document drift. `release_contract.py` now exposes the same
exact schema, repository-pin, six-platform, seven-frontend, hosted-evidence and
documentation checks as a standalone JSON/text CLI that is explicitly invoked
by the Universal workflow. Verify the documentation-only evidence
commit's required contexts without creating a recursive evidence commit.
PRD-2 is closed for the preview scope: 432 compiler/seam tests, 159 quality
tests, generated normal/Trace/Debug execution, all 150 isolated fault
selectors, and 38 CPython C/C++ oracle executions pass; source/binary audits
show no CPython/Hybrid leakage, and M2/M3/M4 records assign every excluded
family a fail-closed non-supported status. PRD-3 is also closed for the
preview: the M5 record binds constructor/partial-object cleanup,
traverse/cyclic GC, finalizer error/resurrection, inheritance, fields,
descriptors, numeric/mapping slots, and three-subinterpreter isolation to the
same executable gates; unsupported HPy 0.9 type shapes have exact diagnostics.
PRD-4 is closed through `tests/ahpy/advanced-surface.toml` and its audit:
all 18 advanced families are either the fully tested narrow `nogil` partial
slice or deterministic blocked/rejected preview behavior with migration
guidance; C++, annotation, profile, linetrace, embedded signatures, and C-line
traceback instrumentation now fail before output. PRD-5's same-binary,
stable/development HPy, platform/compiler, sanitizer, Valgrind, AppVerifier,
and reproducible portability gates are complete; publish the prepared HPy
Python 3.14 heap-type crash report without promoting the three allowed-failure
early warnings.

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
zero, no timeout, and all 750 fault selectors. The subsequent sequential
128-case fault gate passed. The generated corpus also passed five times in the
stress profile. A post-stress ordinary O3 retry remained inside Apple Clang's
`bootstrap_types.c` optimization beyond 15 minutes and was terminated/reaped;
  that historical run was not green. A later isolated, single-compiler M9 gate
  regenerated the current 4.98 MB/87,259-line corpus and measured Apple Clang
  21 at 1.59 seconds `-O0` and 5.29 seconds `-O3`; both are now guarded by a
  required 60-second O0 liveness ceiling. O3 remains a bounded diagnostic after
  Ubuntu GCC 13 exceeded both 60- and 180-second hosted trials. The earlier >15-minute state is not
  reproducible in a single-compiler run. During the first borrowed-handle
  validation, accidentally launching the same full-corpus command twice made
  two `bootstrap_answer.c -O3` compiler processes exceed four CPU minutes;
  terminating the older owned process let the bounded O0 semantic rerun finish
  in 10.50 seconds. This directly confirms concurrency as a major trigger,
  while the isolated large-type liveness gate remains the timing authority.

### A2. Hosted platform/compiler matrix

The workflow declares Linux x64 GCC/Clang, Linux ARM64 GCC, macOS Intel/ARM64
Clang, and Windows x64 MSVC. Push run `29685285138` validated every mandatory
platform job from commit `02d9f8cdd`.

- Preserve `origin` as `https://github.com/mburakmmm/aHPy.git` and keep
  `upstream` pointed at official Cython.
- Preserve run/job URLs, exact runner images, compiler versions, and artifact
  hashes in `docs/ahpy/audits/m8-platform-ci-repairs.md`.
- Keep all six jobs mandatory and repair future regressions with focused tests.
- Do not extend this baseline to alternate interpreters or moving nightlies;
  their independent evidence remains allowed-failure.

### A3. Same-binary PyPy/GraalPy evidence

- Run the declared build-once portability artifact on pinned PyPy 7.3.23 and
  GraalPy 25.1.3 hosted jobs.
- Confirm downloaded `.hpy0` hashes match the CPython-built manifest exactly.
- Resolve failures before removing `continue-on-error`.
- Update `tests/ahpy/interpreters.toml`, support/validation matrices, and an
  audit with hosted URLs. A rebuilt target artifact does not satisfy this gate.
- Preserve the handwritten-first `import-minimal`/`minimal-semantics` stages;
  publish neither prepared upstream report until a hosted run records the
  exact minimal binary digest and failure classification.

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
   one actionable diagnostic before CPython MemoryView utilities run. The
   writable one-dimensional fixed native-scalar/private fixed-array producer is implemented with
   object-owned shape/stride storage, one runtime-owned duplicated exporter
   handle, public HPy slots, all 13 enabled format mappings for both layouts,
   `long`/`double` scalar and four-element `long` array retained-view mutation,
   ordinary derived-type slot inheritance, Normal/Trace/Debug execution, and
   both Dup failure paths. Readonly, broader exporters, and all consumers
   remain gated.)**
5. Fused types and specialization dispatch.
   **(ADR 0009 defines neutral specialization descriptors, a pure-HPy
   callable/subscriptable dispatcher, typed conversion, and interpreter-owned
   metadata. Fused `def`/`cpdef` now fail closed before CPython fused-function
   machinery; implementation remains open.)**
6. `nogil`, Python-state transitions, exception reacquisition, `prange`,
   OpenMP, synchronization, and free-threading.
   **(ADR 0010 and runtime-tested slices now permit non-empty blocks of
   discarded or retained scalar calls to validated external C functions
   declared `noexcept nogil` or exact signed `except -1 nogil`; emission
   preconverts arguments, supports local/global/attribute/item/slice targets,
   snapshots errno before public-HPy re-entry, and validates held/released/
   discarded error paths. Explicit non-empty `with gil` islands between native
   intervals now run their supported Python body while execution is active and
   pass callback success/failure oracles. Compound targets, other native
   failures, and C-boundary callbacks remain open. ADR 0011 now defines the neutral
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
   all six hosted stable-matrix executions are green in run `29685285138`.)**
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
   `docs/ahpy/onboarding.md`; hosted Linux evidence is green in run
   `29685285138`.)**
8. Sign approved release artifacts and publish strict verification guidance.
   **(the tag-only `ahpy-release-attestations.yml` gate now rebuilds clean and
   reproducible evidence, creates keyless Sigstore SLSA/SPDX attestations, and
   retains offline bundles; the item stays open until an approved
   `ahpy-v<version>` tag is signed and verified.)**
9. Rehearse TestPyPI without granting build code a publishing credential.
   **(`prepare_publish_dist.py` copies only the exact frontend sdist/pure wheel
   from a validated bundle; the manual workflow defaults to no upload and
   isolates OIDC to an explicit `testpypi` environment job. Actual index
   configuration/upload still requires project-owner approval.)**

## 8. Performance, pilots, upstreaming, and release queue

1. Keep the generated and handwritten HPy benchmark references aligned across
   the current ten operations. Supported sequence-index iteration now has an
   equivalent reference; typed memoryviews remain HPy 0.9
   blocked/non-comparable, so do not fabricate a memoryview number.
2. Keep the completed classic Cython, HPy CPython ABI, and HPy Universal ABI
   benchmark profiles separate; never combine their overheads into one number.
   Add hosted history before enforcing non-Universal release budgets.
3. Record compile time, native compiler time, C size, binary size, peak memory,
   HPy Trace API counts, and handle churn. Optimize duplicate/close pairs only
   after ownership proofs and tests.
   **(Trace measurement completed for all ten comparable operations: exact
   per-API deltas and dup/close churn are in benchmark JSON; arithmetic,
   container, attribute, call, extension-type, and external-C overhead is
   quantified. Sequence-index iteration is 36 generated versus 18 handwritten
   calls per iteration after borrowing only its call-scoped source argument;
   rebindable owned locals remain materialized. Its historical 1.86–2.00×
   local range was superseded by the 1.65–1.97× hosted range and reviewed
   2.36× release ceiling. Separate-clean-process peak RSS,
   frontend/native build times, and source/binary sizes are also recorded.
   Typed memoryviews remain blocked; remove no cleanup without
   ownership/failure proofs.)**
   **(The first ownership-proven optimization is complete: benchmark call
   contracts are genuinely positional-only on both sides, and direct live Name
   handles are borrowed for attribute receivers and zero-argument callables.
   Both paths now match the reference at 1 API call/iteration with zero
   Dup/Close churn; normal/Trace/Debug and 150 fault selectors are green.)**
   **(The second ownership-proven optimization is complete: two-or-more
   required positional-only functions use `HPyFunc_VARARGS` without a keyword
   parser/tracker; direct live Names feed borrowing binary and fixed sequence
   builder APIs under a left-to-right evaluation proof. Arithmetic/container
   now match the references at 1/4 API calls with zero Dup/Close churn and
   0.97×/1.07× historical ratios. Their release ceilings are 1.27×; 185 emitter tests,
   normal/Trace/Debug, and 150 fault selectors are green. Closure call slots
   accept empty `**{}` but reject non-empty keywords for no-, one-, and
   multi-argument positional-only nested functions.)**
   **(The third ownership-proven optimization is complete: extension-field
   owners/values stay borrowed under call-lifetime and evaluation-order proofs;
   type/module owners load lazily; positional-only initializers bypass keyword
   trackers. Historical type creation/method ratios are 1.02×/0.96×; their
   release ceilings are 1.25×/1.24×. Trace is 3/2 and 2.003/2.002 calls with
   zero generated Dup/Close,
   and 186 emitter tests plus normal/Trace/Debug and 150 fault selectors are
   green. Lazy owner names are part of branch lifetime snapshots; the isolated
   4.65 MB large-type C corpus compiles at O0/O3.)**
   **(The fourth ownership-proven optimization is complete: representable
   numeric literals in validated external-C scalar calls emit portable typed C
   literals directly, while dynamic, non-finite, ambiguous `char`, and
   out-of-portable-range values retain checked HPy conversion. External-C
   Trace is now 1/1 call with zero Dup/Close churn, Universal/HPy-CPython
   ratios are 0.99×/1.00×, its release ceiling is 1.22×, and 188 emitter tests plus
   normal/Trace/Debug and 150 fault selectors are green.)**
   **(The large-type compile is now isolated in this gate: current Apple Clang
   21 evidence is 1.59 seconds `-O0`, 5.29 seconds `-O3`, ratio 3.32×, under a
   60-second per-profile ceiling. O0 is required; O3 is diagnostic because
   Ubuntu GCC 13 exceeded both 60- and 180-second hosted trials while O0 stayed
   near 5 seconds. Preserve further hosted history before changing policy.)**
4. Maintain the promoted release budgets from reviewed hosted history. Every
   new report records exact source and
   GitHub run provenance plus its complete machine-readable budget policy.
   Run `34029830808` supplied five exact-main hosted schema-v3 reports and a
   reviewed proposal. The checked-in policy now promotes all 19 proposal
   ceilings exactly, records its calibration source, and uses enforced
   `hosted-checkout` release binding; inconsistent states fail closed.
   `calibrate_performance_budgets.py` rejects local,
   mixed, duplicate, failing, or byte-unstable evidence and requires five
   same-commit hosted records before emitting a proposal; a CLI minimum cannot
   weaken the policy minimum. The manual read-only
   `ahpy-performance-calibration.yml` workflow collects five isolated samples
   for one selected commit and aggregates only after all pass. The reviewed
   proposal covers
   runtime ratios, frontend/native build time, peak RSS, footprint, and
   large-type frontend/O0 evidence; absolute values remain cohort-bound.
   Platform, compiler command/flags, peak iterations, and native timeout are
   cohort identity and may not be pooled.
   The approved release policy records its reviewed calibration-source commit
   and uses `candidate_binding = "hosted-checkout"`. Do not try to place
   a commit's own hash inside the versioned file that determines that hash.
   Candidate identity belongs to the immutable schema-v3 report; release mode
   passes only in GitHub Actions when source commit equals hosted GitHub SHA.
   Local, invalid, or stale-checkout evidence fails before ratios can be
   treated as a release result.
   The report now embeds the complete validated budget contract, not just its
   path and compact policy. Calibration rejects policy/contract, environment,
   measurement, large-type enforcement, or cross-sample contract drift and
   retains the exact input contract in the proposal. Never infer an applied
   ceiling from a mutable repository path alone.
   Regression policy must not contain `release_absolute`. A future approved
   release contract requires exactly six calibrated limits for frontend/native
   build time, generated peak RSS and ratio, and large-type frontend/O0 time;
   missing, non-finite, or exceeded evidence fails closed. Do not populate
   these fields from local samples.
   `validate_performance_budget_promotion.py` now verifies that all ten runtime,
   three footprint, and six absolute ceilings exactly match the reviewed
   schema-v3 proposal and rejects input-contract, calibration-source,
   environment/measurement/native-policy, or sample-floor drift. It is
   read-only and does not replace maintainer review or same-HEAD hosted proof.
   Document interpreter/HPy overhead separately from backend overhead.
5. The four pilot categories are selected and pinned in
   `tests/ahpy/pilots.toml`: cython-package-example, murmurhash, frozenlist, and the
   deliberately blocked NumPy C-API bezier source. `pilot_matrix.py` validates
   exact commits, licenses, source paths, expected initial diagnostics, and
   recorded port changes; `run_pilots.py` verifies pristine detached checkouts
   and produces strict initial-scan evidence. The dashboard now merges that
   matrix with per-pilot integration reports gate by gate, validates port
   contracts, and fails on equal-timestamp conflicts. The full local merge
   reports cypack `pass`, murmurhash and frozenlist as their declared partial
   contracts, and bezier `blocked`; the workflow retains all four JSON inputs
   plus the rendered dashboard. Run `31794650087` artifact `9216896185` is
   retained and independently reproduced in
   `docs/ahpy/audits/m10-hosted-pilot-evidence.md`. Convert recurring changes
   into support or migration rules.
   The maintained cypack 0.1.7 port fixture already passes three-module
   setuptools Universal generation/build, source/binary audits, selected
   upstream semantics, and normal/Trace/Debug locally. Its exact-one-wheel
   audit, no-dependency isolated install, installed normal/Trace/Debug modes,
   and provenance-bound comparable `axpy`/Fibonacci measurement also pass
   locally and in the retained hosted workflow artifact; no release
   performance ceiling is inferred from the pilot sample.
   The deliberately blocked bezier source now has an exact manifest contract
   for `numpy-c-api` diagnostics at upstream `_speedup.pyx:37:1` and `:38:1`;
   `run_pilots.py` rejects missing or shifted locations, not just a matching
   action label.
   The murmurhash manifest header paths were corrected against its pinned Git
   tree. A maintained scalar adapter now links the exact upstream
   `MurmurHash3.cpp`/header, keeps pointers inside a C++ shim, and passes
   generate/build, source/binary audit, normal/Trace/Debug, semantic-reference,
   pre-native conversion-failure checks, and a provenance-bound seven-sample
   `hash_u64`/Python-oracle comparison locally. The full upstream
   `hash(str | bytes)` API remains explicitly unsupported; CI retains the
   complete exact checkout matrix plus this pilot's execution JSON. The
   comparison is subset-only and never an enforced release budget.
   The frozenlist supported-subset fixture now passes object-field cyclic GC,
   same-module inheritance, mutation/freeze/hash, constructor-failure cleanup,
   source/binary audit, and normal/Trace/Debug. It exposed and drove a real
   `__hash__` emitter fix: fitting `HPy_hash_t` values are converted directly,
   overflow alone falls back to `HPy_Hash`, and `-1` maps to `-2`. Atomic
   free-threading, iterators, rich comparison, copying, and MutableSequence
   registration remain explicitly outside the result; the supported
   construct/mutate/freeze/hash subset has its own provenance-bound Python
   comparison, while omitted surfaces receive no number. Checkout/run JSON is
   wired into CI.
   Recurring pilot changes are now stable scanner rules instead of generic
   advice: `compiled-entry-point`, `cython-module-cimport`, and
   `cpp-runtime-boundary` join the existing pointer, CPython, and NumPy boundary
   actions. Cypack and frozenlist manifests require these precise IDs and the
   exact pinned rescans pass.
6. Publish a compatibility dashboard, porting guide, and issue template. The
   checksummed `ahpy-universal-conformance-v1` JSON now shares 21 semantic
   cases through a standard-library runner and explicit surface-to-module
   mappings, without Cython imports, `.pyx` paths, or frontend nodes. Preserve
   that boundary when adding language-specific adapters; the retained hosted
   pilot dashboard proves only the declared subsets.
7. Coordinate the backend seam with Cython/HPy maintainers, submit neutral
   refactors as small PRs, maintain a rebase log, and file HPy gaps with minimal
   reproductions.
   The first build-layer dependency inversion is implemented locally:
   `Cython.Build.register_runtime_backend_build_hook()` owns a neutral,
   fail-closed registry and installed entry-point discovery; `ahpy_hpy_compat`
   registers from the integration side, so Cython build core no longer imports
   or names an aHPy module. Clean wheels must expose exactly one provider.
   CPython and Universal compilations also start concurrently in a regression
   test and retain disjoint generated-runtime boundaries. `ModuleNode` now asks
   the immutable runtime service for a validated complete-module emitter;
   CPython keeps the established default writer and the Universal writer owns
   its validation, rendering and output transaction. The
   proposed independent upstream slices, evidence requirements and maintainer
   questions are frozen in `docs/ahpy/upstream-seam-plan.md`; no upstream
   acceptance or PR is claimed yet.
8. Complete security, support, contributor, debugging, release, provenance,
   limitation, and maintenance-cadence documentation before a release candidate.
   Local PRD-9 preparation now includes a strict machine-readable maintenance
   policy, explicit `@mburakmmm` CODEOWNERS and one-person bus-factor disclosure,
   an operational GitHub private vulnerability reporting channel verified as
   enabled through the repository API on 2026-08-12,
   supported-line/EOL/backport/deprecation/cadence procedures, expanded
   Dependabot coverage, and immutable CodeQL v4.36.0 plus Dependency Review
   v5.0.0 workflow pins. Keep the publication/automation tasks open until the
   first hosted security scans are retained on the pushed commit.
   The machine-readable recovery policy and
   `release_recovery_drill.py` exercise a no-publication correctness backport
   with `cherry-pick -x`, its original regression test, unchanged support scope
   and mandatory matrix. Ordinary defects require a reasoned yank plus a new
   version; deletion is exceptional and security work remains private until
   disclosure. Universal CI retains the JSON result, but the drill never
   creates a real release branch or mutates a package index.
   The append-only `rebase-log.toml` now records the initial exact Cython base
   without mislabeling it as a transition; its validator chains future rebases,
   requires per-path conflict classifications and decisions, and matches the
   final commit to package/release metadata. No newer upstream base has been
   accepted yet.
   `debugging.md` now preserves the first failing source/compiler/generated-C/
   native/import/runtime/ownership boundary, and `upstream-dependencies.md`
   distinguishes hosted evidence, handwritten reproductions, prepared reports,
   filed links, and unsupported/blocked status. Do not publish the prepared HPy
   crash report or new PyPy/GraalPy reports without owner authorization.
   The production documentation contract now freezes 28 user, contributor,
   architecture, debugging and release documents across five exact categories.
   Its validator requires critical headings, index reachability and all local
   Markdown link targets, and Universal CI retains the schema-versioned JSON.
   Keep that manifest synchronized whenever a production-facing document moves
   or gains a replacement.
   Maintenance policy v1 also freezes all six compatibility surfaces, the
   preview/stable notice and removal boundary, four mandatory notice channels,
   three migration evidence classes and owner-approved emergency exceptions.
   Keep release/support matrices, CODEOWNERS and the monthly/quarterly cadence
   synchronized with that machine contract.
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
    --fail-under backend=100 \
    --fail-under frontend_seam=45 \
    --fail-under quality_tools=100

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
