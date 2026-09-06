# PRD-5 portability and native-memory audit

Date: 2026-08-12
Product envelope: unpublished aHPy preview
Status: active; one external-reporting blocker remains

The preview support claim is deliberately narrow: CPython 3.11, HPy 0.9.0,
and the six platform/compiler lanes in `tests/ahpy/release-contract.toml`.
PyPy, GraalPy, Python 3.14, moving HPy revisions, and free-threaded Python are
early-warning or excluded targets, not advertised Universal support.

## Current same-HEAD evidence

Documentation-evidence commit `8460c99ca204e654c33524e2fcb880746e35b308`
revalidated the aHPy workflow in
[run 30428968553](https://github.com/mburakmmm/aHPy/actions/runs/30428968553).
Its stable jobs are green:

| Preview lane | Hosted job |
|---|---|
| Linux x64 GCC | [90501555291](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555291) |
| Linux x64 Clang | [90501555296](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555296) |
| Linux ARM64 GCC | [90501555306](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555306) |
| macOS Intel Clang | [90501555289](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555289) |
| macOS ARM64 Clang | [90501555331](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555331) |
| Windows x64 MSVC | [90501555388](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555388) |

Every stable job generates and builds with the pinned stable dependency,
audits source and binary boundaries, and executes the same module in normal,
HPy Trace, and HPy Debug modes. The unchanged portability artifact was built
successfully in
[job 90501555194](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555194);
its manifest contains SHA-256 and size metadata and is rehashed before each
stage. CPython 3.11 is the only supported interpreter, so the preview's
declared same-binary interpreter set is green without implying PyPy or GraalPy
support.

Pinned HPy development commit
`b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381` is green on CPython 3.11 in
[job 90501555258](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555258).
The current required aggregate is green in
[job 90503385982](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90503385982).

## Excluded alternate interpreters

The identical CPython-built handwritten-first artifact in
[run 34030366000](https://github.com/mburakmmm/aHPy/actions/runs/34030366000)
provides the current early-warning classification:

- PyPy 7.3.23 passes handwritten import/semantics, constant-only
  import/semantics, and Fibonacci import, then terminates with signal 11 at
  `fibonacci-semantics` in
  [job 101478712931](https://github.com/mburakmmm/aHPy/actions/runs/34030366000/job/101478712931).
- GraalPy 25.1.3 exposes neither `hpy.universal` nor a native `.hpy0` import
  suffix; the byte-identical native-only stage fails with
  `ModuleNotFoundError` in
  [job 101478712970](https://github.com/mburakmmm/aHPy/actions/runs/34030366000/job/101478712970).

Both are listed as unsupported in the frozen release contract and remain
allowed-failure CI signals. Their red results cannot broaden or weaken the
required CPython support claim.

The diagnostic revision keeps that handwritten oracle first, then adds
generated constant-only and single-function modules before the heap-type and
large function corpora. All ten stages pass locally on CPython 3.11.15/HPy
0.9.0. The hosted result now narrows PyPy to execution of the generated
Fibonacci function after its import succeeds. Prepared PyPy and GraalPy report
drafts live beside this audit; PyPy still needs a native backtrace and both
reports require owner authorization before external publication.
The cross-interpreter workflow now persists a schema-versioned JSON result with
the verified manifest/file hashes, target and loader provenance, ordered stage
stdout/stderr, and exact exit-or-signal classification under `if: always()`.
Missing evidence is itself a workflow artifact failure.
The current PyPy and GraalPy JSON payloads are retained byte-for-byte under
`evidence/portability-34030366000/`; their SHA-256 values are recorded in the
target-specific upstream report drafts.

## Python 3.14 minimal reproducer

The pinned HPy development lane still terminates with signal 11 on CPython
3.14.6 in
[job 94039919189](https://github.com/mburakmmm/aHPy/actions/runs/31573340325/job/94039919189).
`tests/ahpy/hpy_dev_type_reproducer.c` first proves the failure without the
aHPy emitter: one handwritten public-HPy heap type owns one `HPyField`, uses
`HPy_tp_new`, `HPy_New`, `HPy_tp_traverse`, and returns the stored object.
`tests/ahpy/hpy_dev_closure_reproducer.pyx` independently reduces the
generated failure to one captured object, one nested function, and one
immediate call. `Tools/ahpy/reproduce_hpy_dev_closure.py` audits both sources
and binaries, builds both through the pinned HPy toolchain, then executes the
unchanged modules.

Local macOS ARM64 evidence is exact:

- CPython 3.11.15 + HPy 0.9.0 passes both handwritten and generated modules in
  normal, Trace, and Debug;
- CPython 3.14.6 + HPy
  `0.9.1.dev100+gb57a33c1c` crashes in the first handwritten `HPy_New` call,
  before the generated module runs;
- the macOS report records `EXC_BAD_ACCESS` at address `0x10` through
  `_PyObject_GC_New`, HPy's `ctx_New`, `_HPy_New`, and the handwritten
  `reproducer_new_impl` function.

The development workflow now runs these minimal reproducers before the full
corpus, preserving the Python 3.14 job as an allowed failure while proving the
crash independently of generated aHPy C. HPy
[issue 488](https://github.com/hpyproject/hpy/issues/488) tracks general
Python 3.13/3.14 support but not this crash. The exact report is prepared in
`prd5-hpy-dev314-upstream-report.md`; filing it is still an external action.

## Native-memory policy

The current Linux GCC and macOS ARM64 Clang ASan/UBSan jobs are green in
[90501555207](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555207)
and
[90501555200](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555200).
MSVC has no equivalent GCC/Clang sanitizer contract in this preview and is
covered by its stable semantic lane plus the separate Windows heap diagnostic.

Linux Valgrind is a required schedule/manual gate with a real 64-byte definite-
leak positive control. Reviewed jobs 88878105102 and 88897432278 found zero
definite leaks and zero real-corpus errors without active suppressions.
Windows AppVerifier/full-page-heap is also a required schedule/manual gate.
Manual run
[30431371077](https://github.com/mburakmmm/aHPy/actions/runs/30431371077),
[job 90509136349](https://github.com/mburakmmm/aHPy/actions/runs/30431371077/job/90509136349),
proved full-heap configuration, detector injection in all five corpus
processes, a stop-code `0x13` native-overrun positive control, five clean
runtime XML logs, and successful cleanup. The reviewed artifact digest is
`sha256:de6b17f6500a6a74da862586d1bcb783bdc333860026f3d8ecf5280501985a36`;
the job no longer carries `continue-on-error`.

General `nogil`, free-threaded Python, and aHPy TSan support are outside the
preview contract. TSan is therefore not silently treated as passed or
required; promotion first requires a supported free-threading/re-entry model.

## Remaining exit work

Only one PRD-5 blocker remains: file the exact upstream crash report and record
its URL/disposition.

PRD-5 must remain active until that outcome is recorded. The current evidence
does not authorize PyPy, GraalPy, Python 3.14, free-threading, or a Universal
wheel claim.
