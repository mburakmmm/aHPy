# aHPy CI policy

`tests/ahpy/ci-policy.toml` is the machine-readable source of truth for
production CI classification. It lists every `.yml` workflow and every job
identifier exactly once. A new workflow or job must update the manifest in the
same commit.

The policy separates these categories:

- `required_jobs`: required pull-request and main/release evidence;
- `mixed_required_allowed_failure_jobs`: matrix jobs whose individual entries
  carry different required/experimental policy;
- `allowed_failure_jobs`: early-warning jobs that cannot fail a release gate;
- `schedule_manual_required_jobs`: expensive native-memory or recurrence gates
  that are required when explicitly scheduled or dispatched;
- `schedule_manual_allowed_failure_jobs`: experimental scheduled/manual
  diagnostics;
- `manual_required_jobs`: downstream manual gates;
- `release_or_build_jobs`: packaging jobs selected by release or build policy;
- `upstream_only_jobs`: inherited jobs deliberately disabled in the downstream
  repository; and
- `reusable_jobs`: workflow-call implementations whose caller owns the release
  policy.

The manifest also fixes the downstream branch policy. Topic branches validate
through `pull_request`; expensive `push` matrices run only for `main` and
`ahpy/**` release branches. This prevents a branch with an open pull request
from running the same expensive matrix twice while preserving post-merge and
release-line evidence.

`Tools/ahpy/test_ci_policy.py` enforces:

1. every workflow and job is classified once and only once;
2. required and allowed-failure categories match `continue-on-error`;
3. scheduled/manual categories retain their event guards;
4. mixed matrices retain their per-entry experimental expression;
5. downstream branch triggers match the manifest; and
6. job-level YAML mappings do not contain duplicate keys.

This classification does not itself prove a hosted run green. Exact run and
job evidence remains in `validation-matrix.md` and the corresponding M8 audit.
