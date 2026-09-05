# M8 moving-nightly lane validation record

Date: 2026-07-22
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
Status: HPy-master first green reviewed; both moving lanes remain early warnings

## Separation contract

`tests/ahpy/hpy-versions.toml` keeps moving inputs distinct from stable and
commit-pinned development revisions. The workflow declares two
schedule/manual-only, allowed-failure early warnings:

- CPython `3.15-dev` with stable HPy;
- CPython 3.11 with HPy installed from the upstream `master` ref.

Neither moving dependency appears in a stable support job. A nightly result
cannot silently change `docs/ahpy/support-matrix.md` or a pinned manifest row.

## Provenance and bounded-execution checks

`Tools/ahpy/report_nightly_environment.py` verifies the expected interpreter
minor, installation kind, HPy repository and ref, and a resolved 40-character
VCS commit for the branch-tip lane. Unit tests cover malformed or mismatched
status sets and provenance. Workflow contract tests retain the support
boundary, a 30-minute bound on both runtime steps, and the mixed-runtime ASan
`detect_leaks=0` policy.

The complete local quality-tool suite passes 129 tests (one expected local
Valgrind availability skip), and the workflow YAML parses successfully.

## First hosted evidence

Manual run
[29906185775](https://github.com/mburakmmm/aHPy/actions/runs/29906185775)
executed both lanes at commit
`cfbd94b64475306036a11474d5cc587ab9bf8ac6` on `ubuntu-24.04`:

- CPython `3.15-dev` resolved to `3.15.0-beta.4`, but stable `hpy==0.9.0`
  failed while building its own source distribution, before the aHPy backend
  ran. Python 3.15's `pyconfig.h` defines `_POSIX_C_SOURCE=202405L`; the system
  glibc headers had already defined `200809L`, and HPy's `-Werror` converted
  that redefinition into a build failure. This is reviewed red early-warning
  evidence for the external HPy 0.9/interpreter combination, not an aHPy
  semantic failure or support claim. Evidence artifact
  `ahpy-nightly-interpreter-29906185775-1` has digest
  `sha256:425e8a5085d5260b5c1bfb62d4a816fb3c9e4efef8801b7de8ef0c87c47c4dcf`.
- CPython 3.11 installed HPy `0.9.1.dev100+gb57a33c1c` from upstream `master`
  at commit `b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381` and passed exact VCS
  provenance. This is the same commit already green in the pinned `-O0`
  development lane, but the nightly omitted that semantic profile and
  `test_generated_hpy.py` ran under the default optimized build without a time
  bound for more than 90 minutes. The manual workflow was cancelled after all
  other jobs completed. A hang is not compatibility evidence; both nightly
  runtime steps now use `CFLAGS=-O0` and a 30-minute timeout so the
  unconditional artifact step can record the next bounded result. Artifact
  `ahpy-nightly-hpy-29906185775-1` has digest
  `sha256:5c62384c52697ea75406e3e5029860b876acce039799cd8ff72df4e5b78deef9`.

Manual run
[29912162645](https://github.com/mburakmmm/aHPy/actions/runs/29912162645),
job
[88897432348](https://github.com/mburakmmm/aHPy/actions/runs/29912162645/job/88897432348),
provided the first bounded green HPy-master execution at commit
`d0026d83b3880663c1aff6c69accbac93556f13c`. The provenance report again
resolved HPy `0.9.1.dev100+gb57a33c1c` to the full upstream commit
`b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381`; with `CFLAGS=-O0`, the generated
runtime completed in 19 seconds and the job finished in 40 seconds. The lane
remains an allowed-failure early warning and does not promote HPy `master`.

The CPython `3.15-dev`/HPy 0.9 lane still has no green execution: its reviewed
failure occurs while HPy builds, before aHPy runs. A future green must retain
the exact provenance and timeout evidence before it can close the remaining
nightly checkbox; it still cannot change stable support by itself.

## Historical workflow bootstrap

The first ordinary push run (`29490348041`) failed during action preparation,
before checkout or project code executed: seven `actions/upload-artifact`
references were one hexadecimal character short. They now use the full
40-character upstream commit, and the quality suite parses every external
`uses:` entry so shortened hashes cannot recur. This is workflow bootstrap
evidence, not a hosted platform green. Stable replacement run `29685285138` is
reviewed and green; the moving lanes remain outside that stable claim.
