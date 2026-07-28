aHPy changelog
==============

Unreleased
----------

Bootstrap
~~~~~~~~~

* Repaired benchmark CI for the downstream aHPy fork by fetching the exact
  Cython upstream release branches and tags, propagating benchmark-command
  failures through ``pipefail``, validating timing/size CSV sets before
  rendering, and uploading the actual CSV files with fail-closed artifact
  handling; expensive push triggers now run only on downstream main/release
  branches so topic branches with open PRs do not execute duplicate matrices.
  A machine-readable policy now classifies every job in all ten workflows and
  locks required, mixed, allowed-failure, scheduled/manual, release, upstream,
  and reusable behavior. The stable ``aHPy required checks`` context aggregates
  only mandatory families for branch protection and excludes experimental
  cross-interpreter and scheduled/manual early-warning jobs. The Turkish
  production roadmap is explicitly outside the English-only codespell scan,
  with the configuration covered by a regression test.
* Added pure-type synchronous context managers through ordinary Universal
  ``HPyDef_METH`` definitions for ``__enter__`` and ``__exit__``; success,
  exception suppression/propagation, inheritance, body failures, exact source
  arities, and normal/Trace/Debug execution are covered without fictitious HPy
  slots.
* Added pure-type ``__bytes__``, ``__complex__``, and optional-argument
  ``__round__`` through ordinary Universal ``HPyDef_METH`` definitions;
  builtin dispatch, inheritance, invalid result types, and body failures pass
  normal/Trace/Debug without fictitious HPy slots.
* Added explicit, non-empty ``with gil`` islands between Universal HPy
  ``with nogil`` external-C intervals; supported Python bodies execute after
  re-entry, while linked normal/Trace/Debug callback success and failure prove
  ordering and prevent a following native call on error.
* Added the exact signed-integer ``except -1`` external-C errno contract for
  held and ``nogil`` calls: generated code clears errno before the native call,
  snapshots it before re-entry, raises public-HPy ``OSError`` afterward, and
  reports a missing errno as deterministic ``RuntimeError``; linked
  normal/Trace/Debug, discarded-result, and installed-wheel oracles cover
  success/failure.
* Extended the strict Universal HPy ``noexcept nogil`` external-C lane so
  retained scalar results may be assigned after re-entry to Python
  local/global, attribute, item, and slice targets; attribute/item arguments are
  evaluated and checked before leaving execution, with compiler ordering and
  linked normal/Trace/Debug/wheel oracles.
* Extended current-error-only terminal ``try``/``except`` handlers from one
  return to multi-statement assignments, expressions, deletions, supported
  control flow, and a terminal return or explicit raise, with normal/Trace/Debug
  cleanup and translated-error execution.
* Reached 100% executable Python-line coverage for the Universal backend on
  CPython 3.11 and 3.14, expanded the focused run to 582 tests, and raised CI
  floors to 100% backend, 45% frontend seam, and 41% quality tools. Coverage
  schema 2 now reports missing lines/ranges and forces measured imports through
  source files so stale native extensions cannot mask gaps.
* Added qualified package-module generation: dotted runtime names retain their
  full identity while `HPy_MODINIT` exports the leaf-name symbols required by
  the Universal loader; a real packaged `.hpy0` passes normal, Trace, and Debug
  imports.
* Preserved valid Unicode Python function and extension-method names while
  deterministically encoding only their private generated C-symbol fragments;
  real Unicode calls pass normal, Trace, and Debug modes.
* Extended the same boundary to Unicode `cdef class` names, preserving HPy
  type/module identity while encoding private generated C type/helper symbols;
  Unicode properties, closure captures, arguments, and public fields are
  exercised in the real package fixture.
* Made generated C strings use Cython's UTF-8-aware literal encoder; multiline
  property documentation containing quotes, backslashes, controls, and Unicode
  now compiles and round-trips, while unrepresentable NUL-bearing HPy
  definition docs receive an explicit diagnostic.
* Preserved module, module-function, pure-type, and ordinary-method docstrings
  through `HPyModuleDef`, `HPyDef_METH`, and `HPyType_Spec`, with real
  normal/Trace/Debug introspection and explicit diagnostics for NUL-bearing
  definition docs.
* Removed the artificial callable/type requirement: empty, documentation-only,
  pass-only, and assignment-only modules now emit a valid `HPy_mod_exec`; a real
  constant-only Universal module passes normal, Trace, and Debug imports.
* Based aHPy development on current Cython ``master`` at commit
  ``b99cb0e3b5425e11414cadd24168a6cc850e8000``.
* Added the implementation roadmap, Universal ABI boundary, backend
  architecture, HPy dependency policy, release policy, and support matrix.
* Added a context-local typed Runtime API and explicit runtime backend compiler
  option while preserving byte-identical CPython output.
* Routed lifecycle, calls, container construction, primitive conversions, and
  core exception state through typed runtime contracts, with explicit HPy
  capability failures where public HPy has no CPython exception-triple model.
* Routed dynamic module-global, builtin, and class-namespace resolution through
  immutable lookup metadata while keeping registered ``HPyGlobal`` storage and
  HPy module construction as explicit ownership/structure milestones.
* Added registered-global ownership metadata and module-object hooks with exact
  public HPy mappings, an explicit multi-phase module-definition contract, and
  diagnostics for CPython-only manual creation and module-registry operations.
* Routed method layouts/tables, type slots/specifications, and module
  slots/definitions through structural runtime hooks; added static architecture
  guards and closed M1 with a clean 4,550-test, 2,831-module regression run.
* Added the emitter-independent M2 handle model for local, field, global, and
  context-constant storage; owned, borrowed, and immortal ownership; and
  live, moved, and closed state validation. Added exhaustive ownership
  contracts for the M1 HPy handle-operation surface and integrated distinct
  handle generations with function temporary allocation, expression disposal,
  absorbed-result moves, runtime-specific empty-handle spelling, control-flow
  planning, and ownership-aware global loads.
* Added call-scoped HPy context contracts, pure-C versus Python-interacting
  function classification, explicit advanced-entry-point gates, and context
  persistence rejection.
* Added exact `HPy` and opaque builder compiler C types plus a non-stealing,
  terminal-state-checked HPy list/tuple builder emitter path.
* Added a pinned HPy 0.9.0 handwritten Universal reference module that builds
  as `.hpy0` and passes normal execution plus Debug Mode leak detection.
* Enabled the first strict generated Universal HPy tier for argument-free
  module functions returning ``None`` or signed 64-bit integer literals. The
  generated public-HPy translation unit builds as ``.hpy0`` and passes normal
  execution, forbidden-C-API scanning, and Debug Mode leak detection.
* Added a versioned performance regression gate that compares generated
  Universal HPy with an equivalent handwritten reference, enforces relative
  runtime and footprint budgets, and retains run-specific JSON history in CI.
* Replaced unsafe ad-hoc parallel HPy validation with a bounded process-group
  stress gate that isolates temporary roots, preserves hashed child logs,
  recursively cleans up timeouts, and passed five rounds/640 fault selectors.
* Added isolated schedule/manual-only CPython prerelease and HPy branch-tip
  allowed-failure jobs with exact installed interpreter/package/VCS provenance.
* Recorded the first fully green required hosted matrix across Linux x64/ARM64,
  macOS Intel/ARM64, Windows MSVC, sanitizers, portability, pinned HPy
  development, packaging, performance, fault/stress, and fuzz gates; PyPy,
  GraalPy, and Python 3.14 remain explicit allowed-failure early warnings.
* Added the first one-level nested-``def`` Universal slice with owned
  ``HPyField`` environments/callables, shared mutation and sibling capture
  unions, capture-free callables, runtime/Debug oracles, and strict rejection
  of C-typed and deferred closure forms.
* Declared an allowed-failure Linux Valgrind lane whose versioned suppressions
  must preserve a definite-leak positive control before all five real
  generated-corpus runtime processes can pass; promoted it after reviewed
  hosted evidence showed five clean logs and zero active suppressions.
* Recorded the first bounded green HPy-master nightly, completed both 103-job
  current-head Cython matrices and both coverage jobs, and proved the isolated
  Windows shared-utility pass removes the reproduced ``LNK1158`` contention.
* Declared an experimental Windows Application Verifier and full-page-heap
  diagnostic with fail-closed tool discovery, native overrun positive control,
  per-process verifier-injection proof, XML/raw evidence, and settings cleanup.
* Added ADR-backed HPy 0.9 generator gap diagnostics for top-level ``yield``,
  ``yield from``, real generator expressions, and lambdas, preventing fallback
  to CPython coroutine/code-object machinery.
* Added a separate async-suspension ADR and HPy 0.9 diagnostics for native
  coroutine/``await`` and async-generator functions.
* Split HPy buffer producer capability from the missing 0.9 consumer API and
  added an early typed-memoryview rejection before CPython buffer utilities can
  contaminate Universal diagnostics.
* Restored the CPython ``EarlyReplaceBuiltinCalls`` helper/handler ownership
  after the HPy filter class had accidentally captured the base methods; all 38
  focused C/C++ CPython semantic oracle tests pass again.
* Added the pure-HPy fused-specialization design and exact fail-closed
  diagnostics for fused ``def``/``cpdef`` without changing CPython dispatch.
* Added the first public-HPy execution-state slice for discarded argumentless
  ``noexcept nogil`` external-C calls, with real normal/Debug execution.
* Extended that slice to scalar-argument calls: all HPy evaluation, checked
  narrowing, error propagation, and temporary closure finish before
  ``HPy_LeavePythonExecution``; the linked normal/Debug oracle proves successful
  native mutation and conversion failure without native entry.
* Added used scalar results for that slice: native values survive the
  handle-free interval, are boxed only after re-entry, and may be moved into a
  simple Python local; global and compound targets remain fail-closed.
* Added a neutral parallel-worker design and HPy 0.9-specific fail-closed
  diagnostics before ``prange``/OpenMP can reach CPython thread-state code.
* Added a schema-versioned, non-setuptools direct Universal build API/CLI with
  HPy toolchain discovery, safe plans, source/binary audits, manifests, POSIX
  and MSVC contracts, and public-loader normal/Debug integration.
* Added the collision-safe ``aHPy-compiler`` distribution identity and an
  exact-versioned Universal-only PEP 517 backend whose maintained example
  passes a genuine isolated wheel build, ABI audits, installation, and
  normal/Debug execution.
* Added an installed, schema-versioned Universal toolchain contract and real
  CMake, Meson, and isolated scikit-build-core examples with exact tool pins,
  ABI audits, pip installation, and normal/Debug execution.
* Added a clean frontend sdist safety gate, no-index wheel-from-sdist build,
  fresh-environment installation, maintained PEP 517 onboarding, and verified
  frontend/example uninstall/reinstall with hashed artifact evidence.
* Added byte-for-byte two-root frontend sdist/wheel reproducibility, including
  deterministic tar/gzip metadata normalization and exact build provenance.
* Added per-operation HPy Trace API-call and handle-churn measurements to the
  generated-versus-handwritten performance history, including equivalent
  extension-type and Python-independent external-C reference paths.
* Added separate classic Cython, HPy CPython ABI, and HPy Universal ABI
  benchmark profiles with per-profile build, footprint, and peak-memory
  evidence; no cross-ABI aggregate overhead is reported.
* Corrected benchmark call-contract equivalence and eliminated redundant
  Dup/Close pairs for borrowed direct-name attribute receivers and zero-argument
  callables, reducing both paths to the handwritten reference API count.

Release entries will state the exact Cython base revision, HPy revision,
supported feature tiers, interpreter/platform matrix, known limitations, and
performance gates.
