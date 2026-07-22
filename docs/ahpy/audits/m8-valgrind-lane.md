# M8 Linux Valgrind lane validation record

Date: 2026-07-22
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
Status: first hosted run reviewed and green; scheduled/manual Linux gate promoted

## Contract

The schedule/manual `native-memory-valgrind` job is isolated from the mixed
ASan/UBSan lane. It installs pinned stable HPy on CPython 3.11 and Linux, then
runs `Tools/ahpy/run_lsan_hpy.py`.

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
artifact retention, and the absence of an informational `check=False` corpus
invocation. On macOS the executable lane is expectedly unavailable and one
positive-control test skips.

## Reviewed hosted evidence and promotion

Manual run
[29906185775](https://github.com/mburakmmm/aHPy/actions/runs/29906185775), job
[88878105102](https://github.com/mburakmmm/aHPy/actions/runs/29906185775/job/88878105102),
is green at commit `cfbd94b64475306036a11474d5cc587ab9bf8ac6` on Ubuntu
24.04, CPython 3.11.15, GCC 13.3.0, and Valgrind 3.22.0. Artifact
`ahpy-valgrind-29906185775-1` has digest
`sha256:296535447ec22e70dcdf0cf3046c92ebffc191bcd673e002203aeb90f729a4a2`.

The reviewed artifact contains exactly five PID-distinct generated-runtime
logs. Every log reports `definitely lost: 0 bytes in 0 blocks`, zero errors,
and `suppressed: 0 bytes in 0 blocks`. The positive control independently
reports 64 definitely lost bytes in one block and one error. The versioned
suppression file contains comments and an inactive example only; its recorded
SHA-256 is
`a5101050536cf68e80b9a657fd3ab9df2ee804924ae736eea9aacf2d18cfc680`,
so no interpreter or backend allocation was hidden.

This satisfies the Linux promotion boundary. The schedule/manual job is no
longer `continue-on-error`; a future definite leak or broken positive control
fails that workflow. It remains schedule/manual-only rather than part of every
PR run. Windows Application Verifier or a reviewed equivalent with the same
positive-control principle remains a separate open task.
