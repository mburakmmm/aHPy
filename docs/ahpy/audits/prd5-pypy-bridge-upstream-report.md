# Guarded upstream report: PyPy generated Universal HPy call crash

Status: hosted failure reduced to the generated Fibonacci semantics rung while
the handwritten no-argument, positional `HPyFunc_KEYWORDS`, named
`HPyFunc_KEYWORDS`, and constant-only oracles pass. A bounded hosted native
backtrace reaches PyPy's `pypy_g_HPy_Length`. The generic keyword-call bridge
boundary is now excluded; one smaller generated reproducer and owner filing
authorization remain required before choosing the upstream tracker.

Target issue tracker: `https://github.com/pypy/pypy/issues`

## Proposed title

`PyPy 7.3.23 exits with SIGSEGV in HPy_Length while calling an aHPy-generated HPyFunc_KEYWORDS function`

## Environment

- Builder: CPython 3.11.16, HPy 0.9.0, setuptools 83.0.0, Ubuntu 24.04 x86-64.
- Target: `pypy3.11-v7.3.23` from `actions/setup-python`.
- Artifact: unchanged `.hpy0.so` plus HPy's generated `hpy.universal` loader
  stub; no rebuild occurs under PyPy.
- Current evidence: GitHub Actions run `34266960354`, job `102206601623`,
  exact source head `d28565fe2e6bbe3406c99ac7ac0e21d4b45d368e`.

## Minimal source

`tests/ahpy/minimal_universal.c` is handwritten public HPy and has no Cython or
aHPy-generated code. It defines four small methods using `HPyLong_FromLong`,
`HPy_Dup`, `HPyListBuilder`, and an `HPyFunc_KEYWORDS` method that calls
`HPy_Length` only for non-null keyword names. `Tools/ahpy/build_portability_artifact.py`
builds it together with the larger diagnostic corpus and records every file's
size and SHA-256. `Tools/ahpy/portability_smoke.py` rehashes the downloaded
artifact and runs the handwritten module first, in isolated `import-minimal`,
`minimal-semantics`, `minimal-keywords-positional`, and
`minimal-keywords-named` subprocesses.

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

The Universal module imports; `answer()`, `return_none()`, and `make_pair()`
return `42`, `None`, and `[1, 2]`; `keyword_count(42)` and
`keyword_count(value=42)` return `0` and `1`; and `fibonacci.fib(10)` returns
`55`.

## Current actual result

Run `34266960354`, job `102206601623`, uploaded report artifact
`10073364591`. Its GitHub archive digest is
`e107d1578e8e21456bf2b654d5c34090ec887f7ff54d248749721a67c8265525`
and the retained JSON SHA-256 is
`414e69311af6d184140456694f4e5d6484de639d6aea60de6d1bfda16f3d00d5`.
The byte-identical JSON is retained at
[`evidence/portability-34266960354/portability-result-PyPy-7.3.23.json`](evidence/portability-34266960354/portability-result-PyPy-7.3.23.json).
The artifact's handwritten `ahpy_minimal.hpy0.so` has SHA-256
`50f645206e8e728b99a022e195154018b9fd3537075d7a99598e68033ace1bdc`.
PyPy passed handwritten import/semantics, both handwritten keyword-call stages,
generated constant-only import/semantics, and generated Fibonacci import. The isolated
`fibonacci-semantics` stage then terminated with signal 11 through the
`python-stub` HPy loader. This excludes module discovery, generic handwritten
`HPyFunc_KEYWORDS` dispatch for positional and named calls, `HPy_Length` on a
valid handwritten `kwnames`, generated module initialization, and constant
lowering; the first known failing rung is execution of the small generated
Fibonacci function.
The schema-v2 report then reran that exact stage under GDB 15.1 and captured
`SIGSEGV` with 65 frames. Its first four native frames are
`pypy_g_HPy_Length`, `pypy_g_ctx_HPy_Length__star_2`, the artifact's
`HPy_Length`, and `__pyx_hpy_def_0_fib_impl`. The same-run build artifact
`10073132279` (archive digest
`d38067dddca7ad2452dc3e39fc8b57c68706ce5d0ee6eb35e0101efc566cf118`)
retains the unchanged Fibonacci binary
`575cd832c38e6edd495f66ea69231a1f95b36f19d053b823fb47bad34c6656f8`.

## Filing guard

The expanded artifact now supplies the first failing rung, binary digest,
empty stderr, and signal classification. The PyPy workflow now provisions
`gdb` conditionally and asks the smoke driver to rerun only a signal-failing
stage under a 120-second, non-interactive debugger bound. The schema-v2 report
retains the debugger version, detected signal, frame count, bounded output and
failure status without replacing the primary stage failure. Run `34266960354`
now retains a hosted `native_backtrace.status == "captured"` result for the
small `fibonacci-semantics` crash, and its preceding positional and named
handwritten `HPyFunc_KEYWORDS` stages both pass. This proves that the generic
keyword signature and a valid `kwnames`/`HPy_Length` path are not sufficient to
reproduce the fault. Before filing, reduce the generated module to the smallest
wrapper/module-exec combination that still fails so the report is routed to
the correct aHPy, HPy, or PyPy tracker. Do not describe the passing handwritten
methods or the passing Fibonacci import as the reproducer.
