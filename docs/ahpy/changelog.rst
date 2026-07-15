aHPy changelog
==============

Unreleased
----------

Bootstrap
~~~~~~~~~

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
  recursively cleans up timeouts, and passed five rounds/580 fault selectors.
* Added isolated schedule/manual-only CPython prerelease and HPy branch-tip
  allowed-failure jobs with exact installed interpreter/package/VCS provenance.

Release entries will state the exact Cython base revision, HPy revision,
supported feature tiers, interpreter/platform matrix, known limitations, and
performance gates.
