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

The `aHPy required checks` aggregate depends only on the compiler/quality,
stable-platform, required HPy-development, sanitizer, and portability-artifact
families. Experimental cross-interpreter and scheduled/manual early-warning
jobs are deliberately excluded, so they cannot make the required branch
protection context red.

Benchmark and coverage workflows always publish the stable
`benchmark required checks` and `coverage required checks` contexts. A
lightweight path selector skips their expensive bodies for irrelevant changes,
while the aggregate remains green; selected failures and cancellations remain
fail-closed. Together with `ci-success` and `sanitizers-success`, these form
the five required contexts in `tests/ahpy/ci-policy.toml`.
Every context is bound to the verified GitHub Actions App integration ID, so a
different integration cannot satisfy a production rule by publishing the same
context name.

`.github/rulesets/production-branches.json` is the reviewable repository
ruleset source for `main` and `ahpy/**`. It requires pull requests, resolved
review threads, up-to-date required contexts, and blocks branch deletion and
non-fast-forward pushes. It grants no bypass actor. The committed source and
the live GitHub API result must both pass audit before branch protection is
claimed.

`.github/workflows/ahpy-release-attestations.yml` is deliberately outside
ordinary branch and pull-request CI. Only an exact `ahpy-v<package-version>`
tag can start its required signing job. The job rebuilds clean and reproducible
release evidence before GitHub OIDC/Sigstore attestations are created, and all
external actions are pinned to immutable commits. See
[`release-signing.md`](release-signing.md) for the verification policy.

`.github/workflows/ahpy-testpypi.yml` is manual and defaults to a no-upload
rehearsal. Its build job has no OIDC permission. Only a separately classified
`publish-testpypi` job can receive `id-token: write`, and that job additionally
requires the boolean publish input plus the `testpypi` environment. The
frontend-only selection and recovery policy are in
[`publishing.md`](publishing.md).

The Universal compiler-and-quality job also runs the isolated release recovery
drill and retains its JSON beside packaging evidence. This validates backport
source provenance, regression-test carriage, unchanged support scope, and the
reasoned-yank/exceptional-delete/security-disclosure policy without performing
any external publication action.

The same job validates `tests/ahpy/documentation-contract.toml` and retains its
JSON in the packaging artifact. The contract covers the complete user,
contributor, architecture, debugging and release corpus, required operational
headings, documentation-index reachability and every local Markdown link.

`.github/workflows/ahpy-performance-calibration.yml` is manual-only and
read-only. Five isolated matrix jobs benchmark one exact selected commit and
upload distinct immutable sample artifacts. A dependent job can produce only
a proposal-only release calibration after all samples pass; it cannot modify
the versioned budget, publish a package, or obtain OIDC credentials. The
evidence and review contract is in
[`performance-release-gate.md`](performance-release-gate.md).

`.github/workflows/ahpy-security.yml` runs a pull-request dependency review
and fail-closed CodeQL `security-extended` analysis for Python and C/C++ on
pull requests, `main`, release branches, manual dispatches and a weekly
schedule. Security-event write permission is scoped only to the CodeQL job;
dependency review and checkout remain read-only. The first hosted results must
be reviewed before a stable branch-protection context is added. See
[`maintenance.md`](maintenance.md) for ownership, cadence and triage policy.

The live repository ruleset is
[`19886870`](https://github.com/mburakmmm/aHPy/rules/19886870). GitHub reports
it as active with `current_user_can_bypass: never`; both `main` and a
non-existent probe branch named `ahpy/3.2` resolve to the deletion,
non-fast-forward, pull-request, and required-status-check rules.

The manifest also fixes the downstream branch policy. Topic branches validate
through `pull_request`; expensive `push` matrices run only for `main` and
`ahpy/**` release branches. This prevents a branch with an open pull request
from running the same expensive matrix twice while preserving post-merge and
release-line evidence.

The reusable Cython job keeps ordinary lanes at an 80-minute fail-closed
ceiling and GraalPy at 150 minutes. Shared-utility mode recompiles the full
selected corpus with larger translation units, so it is independently bounded
to four outer test workers and 120 minutes. This preserves the complete test
surface on a cold or low-hit compiler cache without allowing seven outer
workers to oversubscribe concurrent `g++`/`cc1plus` processes.

`Tools/ahpy/test_ci_policy.py` enforces:

1. every workflow and job is classified once and only once;
2. required and allowed-failure categories match `continue-on-error`;
3. scheduled/manual categories retain their event guards;
4. mixed matrices retain their per-entry experimental expression;
5. downstream branch triggers match the manifest; and
6. the aHPy aggregate includes every required family and no early warning;
7. selective workflows always publish stable fail-closed aggregate contexts;
8. the repository ruleset matches the protected branches and required
   contexts in the policy; and
9. job-level YAML mappings do not contain duplicate keys.

This classification does not itself prove a hosted run green. Exact run and
job evidence remains in `validation-matrix.md` and the corresponding M8 audit.
