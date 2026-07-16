# M8 moving-nightly lane validation record

Date: 2026-07-16
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
Status: local workflow contract green; hosted executions pending

## Separation contract

`tests/ahpy/hpy-versions.toml` keeps moving inputs distinct from stable and
commit-pinned development revisions. The workflow declares two
schedule/manual-only, allowed-failure early warnings:

- CPython `3.15-dev` with stable HPy;
- CPython 3.11 with HPy installed from the upstream `master` ref.

Neither moving dependency appears in a stable support job. A nightly result
cannot silently change `docs/ahpy/support-matrix.md` or a pinned manifest row.

## Provenance checks

`Tools/ahpy/report_nightly_environment.py` verifies the expected interpreter
minor, installation kind, HPy repository and ref, and a resolved 40-character
VCS commit for the branch-tip lane. Unit tests cover malformed or mismatched
status sets and provenance. Workflow contract tests also retain the explicit
hosted-pending wording and the mixed-runtime ASan `detect_leaks=0` policy.

The complete local quality-tool suite passed 70 tests (one expected local
Valgrind availability skip), and the workflow YAML parses successfully.

## Open evidence

The authorized repository and push now exist at
`https://github.com/mburakmmm/aHPy`; the first push-triggered aHPy workflow is
run `29490045367`. The two schedule/manual-only nightlies have not yet produced
reviewed hosted evidence. They remain allowed-failure, and their first results,
runner identities, resolved versions, commits, and logs must be recorded before
any hosted-green claim.

The first ordinary push run (`29490348041`) failed during action preparation,
before checkout or project code executed: seven `actions/upload-artifact`
references were one hexadecimal character short. They now use the full
40-character upstream commit, and the quality suite parses every external
`uses:` entry so shortened hashes cannot recur. This is workflow bootstrapping
evidence, not a hosted platform green; the replacement run still requires
review.
