# Guarded upstream report: PyPy generated Universal HPy import crash

Status: hosted failure reduced to the generated Fibonacci semantics rung while
the handwritten and constant-only oracles pass. The bounded native-backtrace
collector is implemented; a hosted capture and owner filing authorization
remain required.

Target issue tracker: `https://github.com/pypy/pypy/issues`

## Proposed title

`PyPy 7.3.23 exits with SIGSEGV while importing an aHPy-generated Universal HPy 0.9 module`

## Environment

- Builder: CPython 3.11.15, HPy 0.9.0, setuptools 83.0.0, Ubuntu 24.04 x86-64.
- Target: `pypy3.11-v7.3.23` from `actions/setup-python`.
- Artifact: unchanged `.hpy0.so` plus HPy's generated `hpy.universal` loader
  stub; no rebuild occurs under PyPy.
- Current evidence: GitHub Actions run `34030366000`, job `101478712931`.

## Minimal source

`tests/ahpy/minimal_universal.c` is handwritten public HPy and has no Cython or
aHPy-generated code. It defines three small methods using `HPyLong_FromLong`,
`HPy_Dup`, and `HPyListBuilder`. `Tools/ahpy/build_portability_artifact.py`
builds it together with the larger diagnostic corpus and records every file's
size and SHA-256. `Tools/ahpy/portability_smoke.py` rehashes the downloaded
artifact and runs the handwritten module first, in isolated `import-minimal`
and `minimal-semantics` subprocesses.

## Reproduction

On an Ubuntu 24.04 x86-64 builder with CPython 3.11 and the repository's
pinned requirements:

```console
python -m pip install -r tests/ahpy/requirements-hpy09.txt
CFLAGS=-O0 python Tools/ahpy/build_portability_artifact.py \
  --python python --output portability-artifact
```

Transfer `portability-artifact` byte-for-byte to the target, then run:

```console
pypy3 -m pip install setuptools==83.0.0
pypy3 portability-artifact/portability_smoke.py \
  --report portability-result-PyPy-7.3.23.json
```

The driver prints builder/target provenance before launching each isolated
stage. A negative subprocess return code is reported as its terminating
signal, so a bridge crash cannot be confused with an assertion failure.

## Expected result

The Universal module imports and `answer()`, `return_none()`, and `make_pair()`
return `42`, `None`, and `[1, 2]` respectively.

## Current actual result

Run `34030366000`, job `101478712931`, used artifact `9988404334`. Its GitHub
archive digest is
`2644fea636984c723f6cef2a12e28a2ca2e9dc7a119e873ac0546443553c1c36`
and the retained JSON SHA-256 is
`9aaa1af38674e49b60ed1abec7684eeaf5b18d0d13e3f0b29e5f48a6a40ce0d5`.
The byte-identical JSON is retained at
[`evidence/portability-34030366000/portability-result-PyPy-7.3.23.json`](evidence/portability-34030366000/portability-result-PyPy-7.3.23.json).
The artifact's handwritten `ahpy_minimal.hpy0.so` has SHA-256
`fd4be0297fcc40c74941d8db59d443be722b9985b070b6668428dd5376f498b5`.
PyPy passed handwritten import/semantics, generated constant-only
import/semantics, and generated Fibonacci import. The isolated
`fibonacci-semantics` stage then terminated with signal 11 through the
`python-stub` HPy loader. This excludes module discovery, handwritten HPy
operations, generated module initialization, and constant lowering; the first
known failing rung is execution of the small generated Fibonacci function.

## Filing guard

The expanded artifact now supplies the first failing rung, binary digest,
empty stderr, and signal classification. The PyPy workflow now provisions
`gdb` conditionally and asks the smoke driver to rerun only a signal-failing
stage under a 120-second, non-interactive debugger bound. The schema-v2 report
retains the debugger version, detected signal, frame count, bounded output and
failure status without replacing the primary stage failure. Treat this as
instrumentation, not evidence: capture and retain a hosted
`native_backtrace.status == "captured"` result for the small
`fibonacci-semantics` crash, then reduce the generated source/runtime boundary
before filing. Do not describe the passing handwritten module or the passing
Fibonacci import as the reproducer.
