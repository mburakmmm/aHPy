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
report records:

- the full source commit;
- repository, workflow ref, job, run ID, run attempt, and GitHub SHA;
- exact Python, HPy, machine, compiler, and measurement identities;
- all generated/reference samples and same-ABI ratios;
- byte footprint, large-type compile evidence, Debug result, and violations.

Calibration fails closed unless all reports:

1. are successful GitHub Actions evidence rather than local measurements;
2. have no budget violations and contain a passing HPy Debug check;
3. identify the requested repository and exact 40-character release commit;
4. have unique run ID/run-attempt pairs;
5. share one Python/HPy/compiler/measurement cohort;
6. contain the complete nine-operation release corpus; and
7. reproduce the generated/reference source and binary byte sizes exactly.

At least five hosted reports are required. Re-running one workflow is allowed
because each attempt is immutable and separately identified; copying one
attempt more than once is rejected.

## Collect and calibrate

Download each selected run into its own directory:

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
observed maximum, and a ceiling proposal with 20% headroom. Footprint bytes,
binary ratio, required `-O0` large-type compile distribution, and diagnostic
`-O3` timeout count are retained separately.

`proposal_only: true` and `apply_automatically: false` are mandatory. A
maintainer must review the raw hosted artifacts, runner noise, proposed
headroom, and support contract before changing the versioned budget. The
budget change then needs its own same-HEAD hosted validation; local absolute
timings and unlike host cohorts must never be pooled.
