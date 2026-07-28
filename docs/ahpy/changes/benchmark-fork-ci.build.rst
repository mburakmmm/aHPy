Repair benchmark CI in the downstream aHPy repository by fetching Cython
release branches and tags from the upstream remote, propagating pipeline
failures, validating timing and size CSV sets before summary rendering, and
uploading the real CSV artifacts with fail-closed handling. Expensive
workflows now reserve push runs for downstream main/release branches while
topic branches use their pull-request validation run.

The machine-readable ``tests/ahpy/ci-policy.toml`` manifest classifies every
workflow job as required, mixed, allowed-failure, scheduled/manual, release,
upstream-only, or reusable. Focused quality tests reject missing or duplicate
classifications, job-level YAML key duplication, failure-policy drift, and
downstream branch-trigger drift. A stable ``aHPy required checks`` aggregate
collects mandatory aHPy families without allowing experimental or
scheduled/manual diagnostics to break branch protection.
The Turkish production roadmap is explicitly excluded from the English-only
codespell scan and that configuration is regression-tested.
Benchmark and coverage workflows always publish stable required aggregate
contexts; lightweight selectors skip expensive bodies for irrelevant changes
without leaving branch protection pending. The versioned production ruleset
requires those aggregates together with the aHPy, Cython, and sanitizer
aggregates on ``main`` and ``ahpy/**``.
The regular benchmark’s five interpreters run as independent matrix entries
with isolated cache keys and artifacts, fail-fast disabled, and a 90-minute
per-entry timeout. This preserves the complete comparison set while avoiding
the 3–4 hour wall time observed for the inherited sequential upstream job.
