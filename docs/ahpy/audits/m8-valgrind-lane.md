# M8 Linux Valgrind lane declaration record

Date: 2026-07-16
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
Status: enforcing workflow declared; first hosted run and suppression review pending

## Contract

The schedule/manual `native-memory-valgrind` job is isolated from the mixed
ASan/UBSan lane and remains `continue-on-error`. It installs pinned stable HPy
on CPython 3.11 and Linux, then runs `Tools/ahpy/run_lsan_hpy.py`.

The runner compiles a 64-byte definite-leak positive control and executes it
through the same versioned suppression file used for the real corpus. The
expected Valgrind error exit and `definitely lost` marker are mandatory, so a
suppression cannot make the lane green by hiding all leaks.

The generated Universal module is built once per corpus run. Only its five
runtime subprocesses—failed-import retry, normal semantics, Trace semantics,
Debug retry, and Debug semantics—receive the strict Valgrind prefix. Any
definite leak returns the reserved nonzero exit and fails the enclosing corpus
gate; the runner does not ignore that result.

## Evidence artifact

Every hosted attempt uploads:

- the exact suppression file and SHA-256;
- Python, compiler, and Valgrind identities;
- the positive-control log and binary;
- five PID-distinct generated-runtime Valgrind logs.

Local unit tests verify command construction, definite-leak-only policy,
positive-control behavior when Valgrind is installed, workflow scheduling,
allowed-failure status, artifact retention, and the absence of an
informational `check=False` corpus invocation. On macOS the executable lane is
expectedly unavailable and one positive-control test skips.

## Promotion boundary

This record is not a green memory-tooling claim. The first hosted result must
be reviewed, every interpreter-owned suppression must have a narrow recorded
rationale, the clean generated corpus must pass, and the evidence URL must be
added before the lane can become required. Windows Application Verifier or a
reviewed equivalent remains a separate open task.
