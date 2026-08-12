# Prepared upstream report: PyPy Universal HPy bridge import crash

Status: prepared locally; do not file until the new handwritten-oracle hosted
run reproduces the failure.

Target issue tracker: `https://github.com/pypy/pypy/issues`

## Proposed title

`PyPy 7.3.23 exits with SIGSEGV while importing a CPython-built Universal HPy 0.9 module`

## Environment

- Builder: CPython 3.11.15, HPy 0.9.0, setuptools 80.9.0, Ubuntu 24.04 x86-64.
- Target: `pypy3.11-v7.3.23` from `actions/setup-python`.
- Artifact: unchanged `.hpy0.so` plus HPy's generated `hpy.universal` loader
  stub; no rebuild occurs under PyPy.
- Existing evidence: GitHub Actions run `30428968553`, job `90501653601`.

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

## Existing actual result

The previous unchanged aHPy corpus reached PyPy's bundled `hpy.universal`
bridge and terminated with signal 11 during its first module import in run
`30428968553`, job `90501653601`. That establishes the bridge-stage failure but
does not yet prove that the new handwritten minimum reproduces it.

## Filing guard

Replace this section with the new run/job URL, exact `ahpy_minimal.hpy0.so`
SHA-256, subprocess stage, exit/signal, stderr, and any native backtrace from
the uploaded `ahpy-portability-PyPy-7.3.23` JSON evidence before filing. If the
handwritten module passes, do not file this report as written;
bisect from `minimal-semantics` toward the generated function/type corpora and
report the smallest failing public-HPy operation instead.
