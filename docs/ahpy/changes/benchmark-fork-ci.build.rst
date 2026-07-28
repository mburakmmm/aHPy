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
downstream branch-trigger drift.
