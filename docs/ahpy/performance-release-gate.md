# Release performance budget calibration

aHPy's ordinary benchmark gate uses conservative relative ceilings to catch
large regressions on shared CI runners. Those ceilings are not automatically
release budgets. A release budget must be derived from repeated, immutable
GitHub Actions evidence for one exact release-candidate commit and one
measurement cohort.

`Tools/ahpy/calibrate_performance_budgets.py` implements that boundary. It is a
proposal generator, not a budget editor. It never modifies
`tests/ahpy/performance-budgets.toml`.

## Evidence contract

Every input must be an unmodified `ahpy-performance-<run-id>-<attempt>`
artifact produced by `.github/workflows/ahpy-universal.yml`. The benchmark
report and proposal use schema v3. Older reports predate either mandatory
resource/build provenance or the explicit regression-versus-release budget
classification and are rejected rather than silently pooled. Each report
records:

- the full source commit;
- repository, workflow ref, job, run ID, run attempt, and GitHub SHA;
- exact Python, HPy, platform, machine, compiler, compiler-command/flags,
  peak-memory iteration, timeout, and measurement identities;
- all generated/reference samples and same-ABI ratios;
- byte footprint, large-type compile evidence, Debug result, and violations.
- the exact budget policy proving whether its ceilings are regression-only or
  approved release gates.
- the complete validated budget contract, including every runtime/footprint
  ceiling, environment pin, measurement setting, and native compile policy.

Calibration fails closed unless all reports:

1. are successful GitHub Actions evidence rather than local measurements;
2. have no budget violations and contain a passing HPy Debug check;
3. identify the requested repository and exact 40-character release commit;
4. have unique run ID/run-attempt pairs;
5. share one Python/HPy/platform/compiler/build-configuration/resource/
   measurement cohort;
6. contain the complete ten-operation release corpus; and
7. reproduce the generated/reference source and binary byte sizes exactly.

Reports whose compact `budget_policy` differs from their embedded
`budget_contract.policy` are rejected. Measurement, HPy/interpreter identity,
native timeout, and enforced optimization profiles must also match the embedded
contract. All reports in one calibration cohort must carry the exact same full
contract; a matching file path or policy label alone is insufficient. The
proposal retains that input contract so an immutable artifact remains
auditable after the repository budget file changes.

The checked-in policy is deliberately `classification = "regression"`,
`release_enforced = false`, and `calibration_status =
"hosted-history-pending"`. It also declares a minimum of five hosted reports
with `candidate_binding = "unbound"` and no calibration source commit. The
loader rejects inconsistent combinations;
therefore these conservative ceilings cannot be presented as approved release
budgets. A future release budget must be explicitly approved and enforced, use
`candidate_binding = "hosted-checkout"`, and cite the full commit from which
its reviewed calibration proposal was derived.

Candidate identity is executable, not self-referential metadata. A versioned
file cannot contain the Git hash of the commit that contains that same value.
Regression-only ceilings may run locally to detect obvious changes, but an
approved release policy passes only when benchmark provenance is GitHub Actions
and the checked-out source commit equals the hosted GitHub SHA. The resulting
schema-v3 report records the exact candidate commit together with the policy
and its earlier calibration source. Missing provenance, a local run, an invalid
source commit, or a checkout/SHA mismatch is a performance-gate violation
before runtime ratios are considered.

At least five hosted reports are required. Re-running one workflow is allowed
because each attempt is immutable and separately identified; copying one
attempt more than once is rejected.

## Collect and calibrate

The preferred path is the manual
`.github/workflows/ahpy-performance-calibration.yml` workflow. It checks out
one exact selected commit, launches five isolated Ubuntu/Python 3.11/HPy 0.9
matrix jobs, records an explicit sample identity in every report, downloads
all five immutable artifacts, and runs the proposal generator only after every
sample succeeds. The workflow and jobs have read-only repository/actions
permissions and no OIDC or publication credentials. Each measurement sample
has a 90-minute hard timeout and the proposal job has a 10-minute timeout, so
runner stalls cannot consume an unbounded calibration window.

The resulting
`ahpy-release-performance-proposal-<run-id>-<attempt>` artifact is the review
input. The five raw `ahpy-performance-sample-*` artifacts remain the evidence.

Existing separately triggered benchmark reports can also be calibrated
manually. Download each selected run into its own directory:

```console
gh run download RUN_ID \
  --repo mburakmmm/aHPy \
  --pattern 'ahpy-performance-*' \
  --dir /tmp/ahpy-performance-history/RUN_ID
```

Then name the downloaded `benchmark.json` files explicitly:

```console
python Tools/ahpy/calibrate_performance_budgets.py \
  /tmp/ahpy-performance-history/RUN_1/benchmark.json \
  /tmp/ahpy-performance-history/RUN_2/benchmark.json \
  /tmp/ahpy-performance-history/RUN_3/benchmark.json \
  /tmp/ahpy-performance-history/RUN_4/benchmark.json \
  /tmp/ahpy-performance-history/RUN_5/benchmark.json \
  --expected-commit FULL_40_CHARACTER_COMMIT \
  --repository mburakmmm/aHPy \
  --output /tmp/ahpy-release-performance-proposal.json
```

The output records every run, raw ratio series, median, nearest-rank p95,
observed maximum, and a ceiling proposal with 20% headroom. Frontend/native
build time, generated/reference peak RSS and their ratio, footprint bytes,
binary ratio, large-type frontend/required-`-O0` distributions, and diagnostic
`-O3` timeout count are retained separately. Absolute time/RSS proposals remain
valid only for that exact hosted cohort.

The proposal includes headroom-adjusted maxima for generated C bytes,
generated binary bytes, and their generated/reference binary ratio. After a
maintainer reviews the raw artifacts and proposal, construct the candidate
release TOML and verify that it is an exact promotion:

```console
python Tools/ahpy/validate_performance_budget_promotion.py \
  /tmp/ahpy-release-performance-proposal.json \
  tests/ahpy/performance-budgets.toml \
  --json
```

This verifier requires schema v3, proposal-only/non-automatic flags, a full
calibration source commit, the declared hosted-report floor, and the complete
validated regression input contract. It compares all ten runtime ceilings,
three footprint ceilings, and six absolute ceilings exactly with the reviewed
proposal; environment, measurement, large-type compile policy, sample floor,
and calibration-source drift fail closed. It emits a schema-versioned result
but never rewrites the budget or grants approval.

The checked-in regression policy intentionally has no `release_absolute`
table. An approved release policy must add exactly six positive finite limits:
`cython_seconds`, `native_build_seconds`, `generated_peak_rss_bytes`,
`generated_to_reference_peak_rss_ratio`, `large_type_frontend_seconds`, and
`large_type_o0_seconds`. They map directly to the proposal's build-time,
peak-memory, and large-type distributions. Release-mode benchmarking fails on
missing/non-finite evidence or any exceeded limit; regression mode rejects an
absolute table rather than presenting uncalibrated local values as portable
release budgets.

`proposal_only: true` and `apply_automatically: false` are mandatory. A
maintainer must review the raw hosted artifacts, runner noise, proposed
headroom, and support contract before changing the versioned budget. The
budget change then needs its own same-HEAD hosted validation; local absolute
timings and unlike host cohorts must never be pooled.
