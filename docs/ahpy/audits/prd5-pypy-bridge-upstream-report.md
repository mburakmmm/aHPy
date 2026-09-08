# Guarded upstream report: PyPy generated Universal HPy import crash

Status: hosted failure reduced to the generated Fibonacci semantics rung while
the handwritten and constant-only oracles pass. A bounded hosted native
backtrace reaches PyPy's `pypy_g_HPy_Length`; hosted execution of the new
handwritten keyword-call reproducer and owner filing authorization remain
required.

Target issue tracker: `https://github.com/pypy/pypy/issues`

## Proposed title

`PyPy 7.3.23 exits with SIGSEGV while importing an aHPy-generated Universal HPy 0.9 module`

## Environment

- Builder: CPython 3.11.16, HPy 0.9.0, setuptools 83.0.0, Ubuntu 24.04 x86-64.
- Target: `pypy3.11-v7.3.23` from `actions/setup-python`.
- Artifact: unchanged `.hpy0.so` plus HPy's generated `hpy.universal` loader
  stub; no rebuild occurs under PyPy.
- Current evidence: GitHub Actions run `34265271840`, job `102193146755`,
  exact source head `97080f7e8cfeb0b58e02180e46eaec07ee0bd312`.

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

Run `34265271840`, job `102193146755`, used artifact `10071585536`. Its GitHub
archive digest is
`8ec18d6e2c803edadec98031c50e7d39e3ed50ac01755059396e754871780f42`
and the retained JSON SHA-256 is
`8d63a0a27de937214e4b697d7924e5e4273ad05fc1e87034125f484efcdcc9c1`.
The byte-identical JSON is retained at
[`evidence/portability-34265271840/portability-result-PyPy-7.3.23.json`](evidence/portability-34265271840/portability-result-PyPy-7.3.23.json).
The artifact's handwritten `ahpy_minimal.hpy0.so` has SHA-256
`fd4be0297fcc40c74941d8db59d443be722b9985b070b6668428dd5376f498b5`.
PyPy passed handwritten import/semantics, generated constant-only
import/semantics, and generated Fibonacci import. The isolated
`fibonacci-semantics` stage then terminated with signal 11 through the
`python-stub` HPy loader. This excludes module discovery, handwritten HPy
operations, generated module initialization, and constant lowering; the first
known failing rung is execution of the small generated Fibonacci function.
The schema-v2 report then reran that exact stage under GDB 15.1 and captured
`SIGSEGV` with 65 frames. Its first four native frames are
`pypy_g_HPy_Length`, `pypy_g_ctx_HPy_Length__star_2`, the artifact's
`HPy_Length`, and `__pyx_hpy_def_0_fib_impl`. The same-run build artifact
`10071556337` retains the unchanged Fibonacci binary
`575cd832c38e6edd495f66ea69231a1f95b36f19d053b823fb47bad34c6656f8`.

## Filing guard

The expanded artifact now supplies the first failing rung, binary digest,
empty stderr, and signal classification. The PyPy workflow now provisions
`gdb` conditionally and asks the smoke driver to rerun only a signal-failing
stage under a 120-second, non-interactive debugger bound. The schema-v2 report
retains the debugger version, detected signal, frame count, bounded output and
failure status without replacing the primary stage failure. Run `34265271840`
now retains a hosted `native_backtrace.status == "captured"` result for the
small `fibonacci-semantics` crash. The next artifact adds positional and named
stages around a handwritten `HPyFunc_KEYWORDS` method; retain its PyPy result
before filing so the report does not assign a generated-call-contract defect
to PyPy without direct evidence. Do not describe the passing handwritten
no-argument methods or the passing Fibonacci import as the reproducer.
