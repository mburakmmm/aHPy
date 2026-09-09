# Guarded upstream report: PyPy generated Universal HPy call crash

Status: hosted failure reduced to the generated Fibonacci semantics rung while
the handwritten no-argument, positional `HPyFunc_KEYWORDS`, named
`HPyFunc_KEYWORDS`, and constant-only oracles pass. A bounded hosted native
backtrace reaches PyPy's `pypy_g_HPy_Length`. The generic keyword-call bridge
boundary is now excluded, and a one-function generated keyword reducer also
passes both call forms on hosted PyPy. An isolated public-HPy `range`/`HPy_Length`
oracle and owner filing authorization remain required before choosing the
upstream tracker.

Target issue tracker: `https://github.com/pypy/pypy/issues`

## Proposed title

`PyPy 7.3.23 exits with SIGSEGV in HPy_Length while calling an aHPy-generated HPyFunc_KEYWORDS function`

## Environment

- Builder: CPython 3.11.16, HPy 0.9.0, setuptools 83.0.0, Ubuntu 24.04 x86-64.
- Target: `pypy3.11-v7.3.23` from `actions/setup-python`.
- Artifact: unchanged `.hpy0.so` plus HPy's generated `hpy.universal` loader
  stub; no rebuild occurs under PyPy.
- Current evidence: GitHub Actions run `34331675408`, job `102401673045`,
  exact source head `50b91bcf8406cd6b57c67288017a217a7ba51fc1`.

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

Run `34331675408`, job `102401673045`, uploaded report artifact
`10096048079`. Its GitHub archive digest is
`93b27aac0ec0322167a93a42bca3908fc39415980be0a145708689bc40f4c3a7`
and the retained JSON SHA-256 is
`fbf6322f64109316c83f3f65daaf1cbf01651eaeac126779fd74e8f42c27fef1`.
The byte-identical JSON is retained at
[`evidence/portability-34331675408/portability-result-PyPy-7.3.23.json`](evidence/portability-34331675408/portability-result-PyPy-7.3.23.json).
The artifact's handwritten `ahpy_minimal.hpy0.so` has SHA-256
`50f645206e8e728b99a022e195154018b9fd3537075d7a99598e68033ace1bdc`.
PyPy passed handwritten import/semantics, both handwritten keyword-call stages,
generated constant-only import/semantics, the generated keyword-identity import
and both call forms, and generated Fibonacci import. The isolated
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
`10096025574` (archive digest
`73d5da1b22cf4a2a5c3c5f008d81478c2ea549029b14e290cc31014d18d812a0`)
retains the unchanged Fibonacci binary
`575cd832c38e6edd495f66ea69231a1f95b36f19d053b823fb47bad34c6656f8`.
The minimal generated keyword binary is
`7ff8240627eeaddbf2cf30cef9fecbebab685b6766bab84a15109ea51fca6fd2`.

## Filing guard

The expanded artifact now supplies the first failing rung, binary digest,
empty stderr, and signal classification. The PyPy workflow now provisions
`gdb` conditionally and asks the smoke driver to rerun only a signal-failing
stage under a 120-second, non-interactive debugger bound. The schema-v2 report
retains the debugger version, detected signal, frame count, bounded output and
failure status without replacing the primary stage failure. Run `34331675408`
now retains a hosted `native_backtrace.status == "captured"` result for the
small `fibonacci-semantics` crash, and its preceding positional and named
handwritten `HPyFunc_KEYWORDS` stages both pass. This proves that the generic
keyword signature and a valid `kwnames`/`HPy_Length` path are not sufficient to
reproduce the fault. The artifact's `keyword_identity.pyx` only returns its
single argument; its import, positional-call, and named-call stages all pass on
hosted PyPy. Generated Fibonacci contains another `HPy_Length` for the object
returned by `range(n)`, so the next frontend-independent oracle must call
`range` and measure that result before the report is routed to the correct
aHPy, HPy, or PyPy tracker. Do not describe the passing handwritten
methods or the passing Fibonacci import as the reproducer.
