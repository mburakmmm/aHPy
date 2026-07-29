# ADR 0003: HPy dependency policy

- Status: accepted for bootstrap
- Date: 2026-07-14

## Context

HPy 0.9.0, published in September 2023, is the latest official release at the
start of aHPy development. Current HPy documentation also describes APIs that
may continue to evolve before a later major release.

## Decision

1. The release compatibility lane uses HPy 0.9.0 until a newer stable release is
   explicitly validated.
2. A second CI lane uses one full, pinned HPy repository commit. It is an early
   warning lane and does not silently expand release compatibility claims.
3. Generated code uses only documented public HPy API.
4. Any required HPy API gap is reported upstream with a minimal handwritten C
   reproducer before aHPy introduces a workaround.
5. Compatibility shims are isolated, version-gated, tested in both lanes, and
   forbidden from using interpreter-private API.
6. The support matrix records the exact HPy revisions used for each aHPy
   release.
7. The HPy 0.9 validation environment pins `setuptools==80.9.0` because its
   generated Universal loader imports the deprecated `pkg_resources` module,
   which is absent from newer setuptools releases.
8. Moving interpreter and HPy branch-tip jobs run only on schedules or explicit
   dispatch, remain allowed-failure, and are separate from the release and
   full-commit-pinned development lanes. Their exact resolved revisions are
   uploaded as provenance rather than converted into support claims.

The initial development lane is pinned to HPy commit
`b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381` (observed as
`0.9.1.dev100+gb57a33c1c`) and is validated on Python 3.11. The same revision
built on Python 3.14.6 but its generated semantic corpus terminated with
`SIGSEGV` both locally on macOS arm64 (2026-07-15) and in hosted Ubuntu job
`88188395904` (2026-07-19). Python 3.14 therefore remains an explicitly
experimental early-warning lane; it is not included in the validated support
claim. On 2026-07-29 the failure was reduced both to a handwritten public-HPy
heap type in `tests/ahpy/hpy_dev_type_reproducer.c` and to the five-line
generated closure in `tests/ahpy/hpy_dev_closure_reproducer.pyx`: CPython 3.11
passes both in normal/Trace/Debug, while CPython 3.14.6 reaches
`_PyObject_GC_New` through HPy's `ctx_New`/`HPy_New` and faults at address
`0x10` during the handwritten allocation, before generated code runs. The
dedicated reproducer runs before the full development corpus, and the ready-to-file
upstream report is
`docs/ahpy/audits/prd5-hpy-dev314-upstream-report.md`. The machine-readable
record is `tests/ahpy/hpy-versions.toml`.

The independent moving lanes select CPython `3.15-dev` with stable HPy 0.9 and
CPython 3.11 with HPy's official `master` branch. GitHub's official
`setup-python` documentation defines the `X.Y-dev` selector, and HPy's official
quickstart documents installing from the development repository. aHPy also
checks the installed HPy `direct_url.json`: repository, requested `master` ref,
and resolved full commit must all match before branch-tip evidence is accepted.

## Consequences

HPy development changes cannot unexpectedly alter stable aHPy builds, while the
project still receives early notice of future incompatibilities.
