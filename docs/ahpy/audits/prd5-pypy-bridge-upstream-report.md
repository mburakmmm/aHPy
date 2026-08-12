# Guarded upstream report: PyPy generated Universal HPy import crash

Status: hosted failure confirmed, but the handwritten oracle passes; do not
file until the ten-stage diagnostic artifact identifies the smallest failing
generated-code rung.

Target issue tracker: `https://github.com/pypy/pypy/issues`

## Proposed title

`PyPy 7.3.23 exits with SIGSEGV while importing an aHPy-generated Universal HPy 0.9 module`

## Environment

- Builder: CPython 3.11.15, HPy 0.9.0, setuptools 80.9.0, Ubuntu 24.04 x86-64.
- Target: `pypy3.11-v7.3.23` from `actions/setup-python`.
- Artifact: unchanged `.hpy0.so` plus HPy's generated `hpy.universal` loader
  stub; no rebuild occurs under PyPy.
- Current evidence: GitHub Actions run `31573340325`, job `94040063173`.

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
pypy3 -m pip install setuptools==80.9.0
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

The artifact's handwritten `ahpy_minimal.hpy0.so` has SHA-256
`5b62871da8259c7976cd553b2378c16c4d542c4c685c2657da6c4cc5baf35cce`.
PyPy passed both its isolated import and semantics, then terminated with signal
11 while importing `bootstrap_answer` in run `31573340325`, job `94040063173`.
This excludes the handwritten HPy runtime operations from the report and
assigns the next reduction step to generated output.

## Filing guard

Rerun the expanded artifact and retain its JSON. It tests generated
constant-only, single-function, and heap-type rungs before the large function
corpus. Replace this guard with the first failing rung, its binary digest, full
stderr, signal classification, and a native backtrace before filing. Do not
describe the passing handwritten module as the reproducer.
