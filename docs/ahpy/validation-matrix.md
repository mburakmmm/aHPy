# Validation matrix and release gates

The dedicated `.github/workflows/ahpy-universal.yml` workflow separates
release claims from early warnings. Merely declaring a job does not make a
platform supported: a release matrix entry becomes supported only after its
first green hosted run is recorded and remains required for release branches.

The frozen product level is **preview**. Its exact CPython 3.11, HPy 0.9.0,
Cython base, platform/compiler, and frontend status contract is defined in
[`release-contract.md`](release-contract.md) and machine-readable
`tests/ahpy/release-contract.toml`; PyPy, GraalPy, Python 3.14, and moving
dependency lanes remain outside that contract.

## Required branch protection

Repository ruleset
[`19886870`](https://github.com/mburakmmm/aHPy/rules/19886870) actively targets
`main` and `ahpy/**` with no bypass actor. It blocks deletion and
non-fast-forward pushes, requires pull requests with resolved review threads,
and requires the following up-to-date GitHub Actions contexts:

- `aHPy required checks`;
- `benchmark required checks`;
- `ci-success`;
- `coverage required checks`; and
- `sanitizers-success`.

All five contexts are bound to GitHub Actions integration ID `15368`.
Benchmark and coverage publish stable aggregate contexts even when lightweight
selectors skip their expensive bodies, preventing an irrelevant change from
leaving branch protection permanently pending. The live branch-rules API
returns all four rule types for both `main` and the future-pattern probe
`ahpy/3.2`.

### PRD-0 hosted aggregate evidence

CI-policy implementation commit
`e791c8983bcb1a3c38aa932617a91ea976cb5c55` has the following hosted
evidence:

| Required context | Hosted result |
|---|---|
| `aHPy required checks` | [green job 90238576086](https://github.com/mburakmmm/aHPy/actions/runs/30347252766/job/90238576086) |
| `benchmark required checks` | [green job 90250254151](https://github.com/mburakmmm/aHPy/actions/runs/30347253289/job/90250254151) |
| `coverage required checks` | [green job 90245943934](https://github.com/mburakmmm/aHPy/actions/runs/30347253159/job/90245943934) |
| `sanitizers-success` | [green job 90246538721](https://github.com/mburakmmm/aHPy/actions/runs/30347253367/job/90246538721) |
| `ci-success` | replacement required after PyPy fixture repair |

The benchmark run passed all five parallel interpreter jobs in 32m23s to
1h03m28s, including CSV generation, summary rendering, and artifact upload.
The full Cython graph found one PyPy 3.9-only test-fixture incompatibility:
`SimpleNamespace(self=...)` raised `TypeError` before backend execution.
Commit `1b3805e30` preserves the same synthetic AST field through post-
construction assignment and passes all 248 `TestHPyModuleWriter` tests under
both local CPython and PyPy. PRD-0 therefore remained open until all five
contexts became green on one exact replacement HEAD.

Repair HEAD `8ed77677ee6bd69fdc93a81bdfe3e704ea7d924b` currently records:

| Required context | Current-head result |
|---|---|
| `aHPy required checks` | [green job 90283757405](https://github.com/mburakmmm/aHPy/actions/runs/30361153504/job/90283757405) |
| `benchmark required checks` | [green job 90296401321](https://github.com/mburakmmm/aHPy/actions/runs/30361153497/job/90296401321) |
| `coverage required checks` | [green job 90291908521](https://github.com/mburakmmm/aHPy/actions/runs/30361153526/job/90291908521) |
| `sanitizers-success` | [green job 90296760091](https://github.com/mburakmmm/aHPy/actions/runs/30361153809/job/90296760091) |
| `ci-success` | [green job 90328870116](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90328870116) |

The aHPy aggregate remains green while the same three explicitly allowed
HPy-development 3.14 and same-binary PyPy/GraalPy lanes fail, so the policy
continues to isolate early warnings from the required support signal.

The full Cython run did not expose a backend or test assertion failure. Its
Ubuntu shared-utility C++ lane continued compiling and passing tests until the
80-minute job ceiling cancelled it; the final log reports 109 ccache hits
versus 442 misses and multiple active `g++`/`cc1plus` workers. The replacement
keeps the full corpus, bounds this heavy mode to four outer workers, and grants
only shared-utility jobs a 120-minute fail-closed ceiling. The replacement
hosted run below supplied the required green `ci-success`.

On the repair HEAD, the previously cancelled
[shared-utility C++ job 90281110328](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90281110328)
passed in 14m39s and
[PyPy 3.9 job 90288783333](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90288783333)
passed the fixture regression. The complete graph published 103 successful
jobs including `ci-success`, so all five required contexts are green on the
same repair HEAD.

## Required stable lane

The stable lane installs `hpy==0.9.0` and `setuptools==80.9.0` on Python 3.11.
Every platform job generates C directly through `hpy-universal`, compiles a
`.hpy0` module, audits generated source and undefined binary imports, then runs
the semantic corpus in HPy release, Trace, and Debug modes. Debug Mode uses
`LeakDetector` for backend handle leaks. These correctness builds use `-O0` on
GCC/Clang and `/Od` on MSVC so optimizer cost cannot mask semantic liveness.
The direct non-setuptools integration and the separately budgeted performance
gate retain their own explicit optimization profiles.

| Runner | Architecture | Compiler | Hosted evidence |
|---|---:|---|---|
| `ubuntu-24.04` | x86-64 | GCC | [green, job 88188395901](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395901) |
| `ubuntu-24.04` | x86-64 | Clang | [green, job 88188395939](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395939) |
| `ubuntu-24.04-arm` | ARM64 | GCC | [green, job 88188395936](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395936) |
| `macos-15-intel` | x86-64 | Apple Clang | [green, job 88188395931](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395931) |
| `macos-15` | ARM64 | Apple Clang | [green, job 88188395966](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395966) |
| `windows-2025` | x86-64 | MSVC | [green, job 88188395905](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395905) |

Push run [29685285138](https://github.com/mburakmmm/aHPy/actions/runs/29685285138)
validated commit `02d9f8cdd8386eaf277e89dc876fcee9f75e4054` from a clean checkout.
The exact runner images were Ubuntu x64 `20260714.240.1`, Ubuntu ARM64
`20260714.61.1`, macOS Intel `20260715.0340.1`, macOS ARM64
`20260715.0234.1`, and Windows `20260714.173.1`. Their versioned image
manifests identify GCC 13.3.0, Ubuntu Clang 18.1.3, Apple Clang/LLVM 17.0.0,
and the MSVC 14.44 x86/x64 toolset in Visual Studio Enterprise
18.7.11925.98. These six non-allowed-failure jobs are the initial supported
hosted platform/compiler baseline.

PR run [29900694746](https://github.com/mburakmmm/aHPy/actions/runs/29900694746)
revalidated all six stable jobs, both dedicated sanitizer jobs, portability,
HPy development on Python 3.11, and compiler/quality at implementation commit
`20e401ca71a0440ed91e9b6f9d083f3d6a24ef25`. Its Python 3.14 HPy-development
and same-binary PyPy/GraalPy jobs remain explicit allowed-failure early
warnings and do not weaken the stable result.

The runner labels follow GitHub's current hosted-runner reference:
<https://docs.github.com/actions/reference/runners/github-hosted-runners>.
Explicit labels prevent a moving `*-latest` alias from silently changing a
release platform.

## HPy development early warning

`tests/ahpy/hpy-versions.toml` is authoritative. The development requirement
uses a 40-character commit rather than `master`. Python 3.11 is the validated
development lane. Python 3.14 is allowed to fail as an experimental signal
because the pinned revision currently crashes the generated corpus on the
locally tested macOS arm64 configuration and with exit status -11 in hosted
Ubuntu job
[88188395904](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395904).
A handwritten public-HPy GC heap type and a five-line captured-object closure
now reproduce the same failure before the full corpus: stable CPython 3.11
passes both in normal/Trace/Debug, while CPython 3.14.6 and the pinned HPy
development revision fault during the handwritten `HPy_New` through
`_PyObject_GC_New`/`ctx_New`. The reproducer and ready-to-file upstream report
are linked from the
[PRD-5 audit](audits/prd5-portability-native-memory.md).
A future green result must not alter stable support until the pin,
compatibility audit, and support matrix are updated together.

Two moving nightly lanes are deliberately separate from that pinned
development lane. A schedule/manual-only CPython `3.15-dev` job installs stable
HPy, while a second job keeps CPython 3.11 and installs HPy from `master`.
Both are allowed-failure early warnings. Their report step rejects an
unexpected interpreter minor, non-VCS HPy install, wrong repository/ref, or a
resolved commit that is not exactly 40 hexadecimal characters. Local workflow
contract tests prove that neither moving dependency is present in a stable
support job. Manual run 29906185775 resolved `3.15-dev` to CPython
`3.15.0-beta.4`; stable HPy 0.9 then failed to build before aHPy ran because
its `-Werror` rejected `_POSIX_C_SOURCE` redefinition between Python 3.15's
`pyconfig.h` and glibc. The HPy-master lane resolved to the already pinned
`b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381` commit and recorded upstream VCS
provenance on CPython 3.11, but unlike the green pinned lane it omitted
`CFLAGS=-O0`; its optimized generated-corpus build ran unbounded for more than
90 minutes. Both runtime steps now use the validated `-O0` semantic profile
and a 30-minute timeout. The bounded rerun in manual run 29912162645, job
88897432348, subsequently completed the HPy-master runtime in 19 seconds with
exact full-commit provenance. CPython 3.15 with HPy 0.9 remains red before aHPy
executes.
Neither result is support evidence; both jobs remain allowed-failure early
warnings with unconditional evidence upload.

## Same-binary interpreter gate

The builder job uses CPython 3.11 and HPy 0.9 exactly once. It generates and
builds the module-function and pure-extension-type corpora, audits both
binaries, copies each `.hpy0` file and Python loader unchanged, and records
SHA-256 plus size metadata. PyPy 7.3.23 (Python 3.11.15 compatible) and GraalPy
25.1.3 (Python 3.12 compatible) download that one artifact rather than
rebuilding it. The smoke driver verifies every manifest digest before running
four isolated stages (module import and semantics for functions and pure HPy
types). A signal or nonzero exit therefore identifies the exact failing stage.
Interpreters exposing `hpy.universal` use the unchanged Python stubs; native
HPy interpreters receive a temporary directory containing only byte-identical
`.hpy0` binaries so a CPython loader stub cannot shadow their native importer.
Their exact setup identifiers and evidence job IDs live in
`tests/ahpy/interpreters.toml`. Run 29685285138 reached the first isolated
module-import stage on both targets: PyPy terminated through its bundled HPy
bridge, while GraalPy exposed neither that bridge nor a native `.hpy0` import
hook. Both therefore remain allowed-failure early warnings. Only a future
green hosted execution may remove `continue-on-error` or alter support.

The artifact builder [job 88188395887](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395887)
recorded CPython 3.11.15 and byte-for-byte verified these principal binaries:
`bootstrap_answer.hpy0.so` =
`2630e3aef4f00d277742b0b331a01b7916a2f04759f3a77c4cd5f967a75dcaac`
(3,101,256 bytes) and `bootstrap_types.hpy0.so` =
`cd0a86cd37c89f83d237300123cfb46faf3841eba69711fbc0cd1776d8ba0655`
(2,432,936 bytes).

Two independent local portability-artifact builds use a fixed
`SOURCE_DATE_EPOCH`, `ZERO_AR_DATE`, and compiler file/debug-prefix maps. The
resulting module binaries, loader stubs, smoke program, and manifest are
byte-identical. `verify_reproducible_artifact.py` repeats this comparison in CI.
This does not yet claim reproducible sdist or wheel archives.

## Sanitizers and deterministic output

The Linux GCC and macOS ARM64 Apple Clang jobs instrument the generated
extension and bundled HPy runtime with ASan and UBSan at `-O0`. Linux discovers
and preloads the compiler-matching `libasan`. macOS forces the runner's native
architecture through `ARCHFLAGS`, builds a tiny `Py_BytesMain` launcher linked
to the compiler-matching Apple ASan runtime, and proves that runtime is already
loaded before the generated extension is imported. This avoids signed Python
launchers discarding `DYLD_INSERT_LIBRARIES` and prevents a `universal2` link
from combining native ARM64 objects with a missing x86-64 slice. Both lanes
stop at the first diagnostic.
`run_sanitized_hpy.py` sets `ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:...`
because the host CPython process is not built with matching instrumentation.
LeakSanitizer is intentionally disabled in that mixed ASan lane; unsuppressed
interpreter allocations would not be an actionable backend signal. HPy Debug
Mode remains the mandatory leak detector.

An independent schedule/manual Linux Valgrind job is a required native-memory
gate whenever that workflow mode executes. Its versioned suppression file is
applied first
to a deliberately leaking C positive control; failure to report that definite
leak rejects the lane, preventing an over-broad suppression set. It then runs
all five generated-corpus normal/Trace/Debug runtime subprocesses under
`--errors-for-leak-kinds=definite` and requires zero exits from each. The job
uploads the exact suppression hash, toolchain/interpreter versions, positive
control log, and per-process Valgrind logs. Manual run 29906185775, job
88878105102, is green on CPython 3.11.15/GCC 13.3.0/Valgrind 3.22.0: the
positive control reports 64 definitely lost bytes, all five real logs report
zero definitely lost bytes and zero errors, and the reviewed suppression file
contains no active entries. Artifact digest is
`sha256:296535447ec22e70dcdf0cf3046c92ebffc191bcd673e002203aeb90f729a4a2`.
The job is therefore no longer `continue-on-error`; Windows native-memory
hosted evidence remains open. Required job 88897432278 in successful manual
run 29912162645 revalidated the promoted gate at commit `d0026d83b`.

The Windows counterpart is a required schedule/manual gate on `windows-2025`.
It enables Application Verifier Basics and GFlags full page heap for a unique
native overrun control and a uniquely copied Python executable. The control
must fail with an AppVerifier XML error; each of the five real
generated-corpus processes must prove `verifier.dll` injection and produce an
XML log with no error severity. Preflight discovery, settings queries,
per-process output, XML, raw logs, counts, and cleanup results are uploaded
unconditionally. Manual run
[30431371077](https://github.com/mburakmmm/aHPy/actions/runs/30431371077),
[job 90509136349](https://github.com/mburakmmm/aHPy/actions/runs/30431371077/job/90509136349),
proved full-page-heap configuration, a native-overrun AppVerifier error, five
injected and clean real-corpus processes, and successful settings cleanup.
Artifact digest is
`sha256:de6b17f6500a6a74da862586d1bcb783bdc333860026f3d8ecf5280501985a36`.
The job is therefore no longer `continue-on-error`. It diagnoses native heap
corruption, not leaks; HPy Debug and the Linux Valgrind job keep their separate
leak contracts.

`Tools/ahpy/test_quality_gates.py` compiles the same source twice in independent
directories and compares the emitted bytes. This gate found and fixed an
unordered method-cleanup epilogue; deterministic ordering is now enforced by
the emitter rather than normalized after generation.

The deterministic fault-injection gate wraps APIs only in a test copy of
generated source. It independently fails all three `HPyLong_FromLongLong`
conversions, every nested list/tuple builder build, three dictionary inserts,
four direct call layouts, expanded tuple/dict calls, three attribute and item
reads, attribute/item set/delete, and `HPy_CallMethod` direct method calls. Every selected failure must remain an
exact `MemoryError`; every one-past selector must succeed; all independently
owned intermediates, builder consumption/cancellation, the undefined-symbol
ABI audit, and Debug `LeakDetector` must remain clean. The import lane counts
and fails all three `HPyType_FromSpec` calls and every generated
`HPy_SetAttr_s` publication position, requiring exact `MemoryError`, removal
from `sys.modules`, collection, and successful one-past imports. The resulting
matrix passes 128 isolated normal/Debug processes.

This expansion exposed partial module initialization losing its active error
after rollback. The emitter now records successful module publications,
matches `MemoryError` before cleanup, rolls publications back in reverse order,
and re-establishes only that positively matched error because HPy 0.9 exposes
no public fetch/restore API. Non-memory errors are not speculatively replaced.

`Tools/ahpy/fuzz_supported_surface.py` deterministically generates 48 functions
from seed `0xA4F9`. The grammar combines nested containers, continuing
conditionals, mutating `while` loops, fixed-sequence `for` loops, in-place
operators, slice replacement, function `dir()`/`globals()`, direct method calls,
and Python `type()`/sequence surfaces. One Universal module is generated, audited,
built, and compared function-by-function with `exec` of the identical source as
the pure-Python oracle in normal and HPy Debug modes. The first run exposed a
backend crash on transformed nested statement lists; recursive source-ordered
flattening and a focused regression now guard it. The same gate also compiles a
deterministic rejected-input corpus covering set
construction, generic iteration, `except as`, nonterminal handlers, generators,
`@cython.freelist`, multiple inheritance, metaclass customization,
variable-size layout, and `__dealloc__`; every case must fail with its
actionable Universal diagnostic and no Python traceback or compiler
`InternalError`. Return/raise from loops and
mixed terminating/continuing branches are executable supported surface rather
than rejected fuzz cases.

`Tools/ahpy/coverage_guided_fuzz.py` warms the compiler, compiles 64 mutations
under Python line tracing, and greedily retains a candidate when it adds a new
line in `HPyModuleWriter`, `HandleModel`, `RuntimeAPI`, `Nodes`, or `ExprNodes`,
or introduces a new feature family. Seed `0xC0A4F9` selects 16 candidates,
preserves all 16 families, and reaches a 4,141-line compiler frontier. The
combined corpus covers arithmetic, containers, direct/expanded/keyword calls,
globals, terminal handlers, loops, slices, comparisons, imports, mutation,
starred values, in-place operators, and conditional expressions. It is
source/binary audited and compared with execution of the identical Python
source in normal and Debug modes.

## One-level closure slice

ADR 0005's one-level nested-`def` slice is exercised in emitted-source tests
and in the generated Universal corpus. The runtime oracle covers a captured
argument, mutation through a shared environment, sibling nested functions that
capture different outer values, and a capture-free nested callable. Each outer
function owns one synthesized environment; sibling capture layouts are the
stable union of all nested functions' captures, and callable objects reference
that environment through an `HPyField`. The same generated binary passes
normal, Trace, and Debug modes and the usual source/undefined-import audits.

Focused reject tests keep C-typed captures, nested-nested closures, defaults,
star arguments, generators/`yield`, and decorators outside this partial support
claim. This is not evidence for generators, native coroutines, code-object
introspection, or unrestricted closure semantics.

## Slotless pure-type protocol methods

HPy 0.9 has no dedicated type slots for `__format__`, `__bytes__`,
`__complex__`, or `__round__`, so the Universal type definition array publishes
them as ordinary `HPyDef_METH` entries with the exact checked no/one/optional-
argument layout. The generated pure-type corpus proves builtin dispatch,
inherited lookup, invalid bytes/complex result rejection by the runtime, and
body-error propagation in normal, HPy Trace, and HPy Debug modes. Focused
negative inputs reject invalid source arities with a source-located diagnostic
and no C output; generated source contains no invented `HPy_tp_*` spelling.

## Synchronous pure-type context managers

Pure Universal types publish `__enter__(self)` and
`__exit__(self, exc_type, exc_value, traceback)` as ordinary `HPyDef_METH`
entries because Python discovers the synchronous context-manager protocol by
special-method lookup rather than an HPy type slot. The real generated corpus
proves successful entry/exit, exception suppression and propagation, inherited
lookup, and an exception raised by the `__exit__` body in normal, HPy Trace,
and HPy Debug modes. Focused negative inputs require exact source arities,
produce an actionable diagnostic, and emit no C; asynchronous context methods
remain separately gated.

## Generator diagnose-only gate

ADR 0006 records the resume-state and suspended-handle ownership contract, but
the selected HPy 0.9 headers expose no public iterator-next type slots or
generic iterator API. The strict Universal frontend therefore rejects
top-level generator functions using `yield` or `yield from` before emission.
A returned real generator expression receives the same versioned API-gap
diagnostic; generator expressions consumed by the explicitly inlined
sequence-safe `list`/`dict`/`any`/`all` paths remain supported because they do
not publish or resume a generator object. Focused tests require empty output,
one compiler diagnostic, and no internal traceback for each rejected form.

## Coroutine and async-generator diagnose-only gate

ADR 0007 keeps async state independent from synchronous generators. HPy 0.9
lacks the public async protocol slots and complete exception-state surface
needed for await delivery, cancellation, async iteration, and finalization.
Focused tests compile a native coroutine containing `await` and an async
generator containing `yield`; both fail at their function source with the
versioned HPy gap and an explicit prohibition on CPython coroutine utilities.
No Universal C output is produced.

## Buffer consumer early-rejection gate

ADR 0008 separates the producer slots that HPy 0.9 does expose from the public
consumer acquisition/release API that it does not. A typed-memoryview argument
is rejected immediately after declaration analysis, and the HPy pipeline aborts
on that error before `View.MemoryView` or `Py_buffer` utilities are introduced.
The regression requires one source-located diagnostic, no unrelated GIL
errors, no traceback, and no generated C. Default/explicit CPython pipelines do
not receive this early abort stage.

## Fused specialization fail-closed gate

ADR 0009 defines the pure-HPy specialization dispatcher and metadata model.
Focused inputs cover both fused `def` and `cpdef` over `int`/`double`; each
produces exactly one source-located diagnostic naming the missing typed
conversion, pure-HPy dispatch, and interpreter-owned signature requirements.
No C output is emitted and the diagnostic explicitly prohibits CPython
`__Pyx_FusedFunction`/PyCFunction dispatch. The existing C/C++ CPython semantic
oracle remains green, so this Universal gate does not disable ordinary Cython
specialization.

## Narrow `nogil` external-C gate

ADR 0010 defines the no-handle execution-state interval. A focused positive
input emits a local `HPyThreadState`, leaves through
`HPy_LeavePythonExecution`, calls validated external C symbols with zero or
more scalar arguments, and re-enters through `HPy_ReenterPythonExecution`
before the next HPy operation. Non-literal arguments are source-ordered,
checked, and closed before the leave; conversion failures therefore never
enter the native interval. Each statement receives its own interval so a
later argument's Python conversion cannot move ahead of an earlier native
call. A used scalar result remains native until re-entry, is then boxed through
public HPy, and may be moved into a Python local/global, attribute, item, or
slice target. Attribute/item argument expressions are evaluated before leave and
the corresponding result targets only after re-entry. Focused negative inputs
reject expanded arguments, compound/destructuring result targets, and empty
blocks with no generated C. An explicit non-empty `with gil` island may run the
already-supported held-execution HPy body between native intervals; implicit,
conditional, and empty islands fail closed.

The setuptools integration example links argumentless/scalar-argument
`noexcept nogil` probes plus exact signed `except -1` errno probes, checks their
counter across repeated calls, and
proves a raising `__index__` conversion leaves the counter unchanged. The exact
oracle also observes that an earlier native statement completes before a later
argument's `__index__` conversion and returns retained scalar results through
global/attribute/item/slice targets. The
`.hpy0` passes normal, HPy Trace, and HPy Debug execution plus generated-source and
undefined-import audits. Held, released, and discarded errno calls prove
success, `EDOM`→`OSError`, unchanged native state on failure, snapshot-before-
re-entry ordering, and missing-errno `RuntimeError`. A linked Python callback
inside the GIL island proves native/Python/native ordering and its raising path
proves the following native call is skipped in normal/Trace/Debug. This gate does not cover
compound/destructuring result targets, other native failure protocols, Python
exception reacquisition, callbacks crossing from native C, long-lived nested
transitions, `prange`/OpenMP, or free-threading.

## Parallel/OpenMP fail-closed gate

ADR 0011 records why the originating-thread HPy transition pair is not a
worker-attachment contract and defines the neutral scheduling/reduction plan
required before implementation. Focused inputs exercise both
`prange(..., nogil=True)` and `with nogil, cython.parallel.parallel()`; each
produces one source-located diagnostic naming the missing public HPy worker
attach/error transport, forbids CPython thread-state/exception triples, and
writes no Universal C. This is not OpenMP or free-threading support evidence.

The setuptools integration gate also builds a wheel, verifies that it contains
exactly one `.hpy0` binary plus loader stub, reads its `WHEEL` tags, installs it
with pip into an empty target directory, and executes it. The exact example
also compiles and links a Python-independent C header/source pair, exercises
signed, unsigned, boolean, and floating results plus checked scalar arguments,
and proves that an out-of-range `signed char` argument raises before entering
the C function in normal and HPy Debug modes. On the validated local builder
the observed envelope is
`ahpy_setuptools_example-0.0.0-cp311-cp311-macosx_26_0_arm64.whl`, tagged
`cp311-cp311-macosx_26_0_arm64`. ADR 0004 therefore treats it only as a host
packaging smoke test; the unchanged `.hpy0` portability artifact remains the
cross-interpreter gate until HPy/PyPA select Universal wheel metadata.

## Direct non-setuptools build gate

`Tools/ahpy/direct_build_integration.py` generates `bootstrap_answer.c`, asks
the selected interpreter for its HPy development contract, compiles and links
the artifact without setuptools, verifies source and undefined symbols, and
loads it with public `hpy.universal.load` in normal and Debug LeakDetector
modes. Unit tests cover POSIX/static and MSVC/export plans plus fail-closed
inputs. On Windows the executor locates Visual Studio with `vswhere.exe` and
loads `vcvarsall.bat` only when `cl.exe` is not already on `PATH`; compile and
link execution remains direct. The stable platform/compiler matrix executes the same integration;
all six jobs are green in reviewed run 29685285138.

## Isolated PEP 517 frontend gate

`Tools/ahpy/pep517_integration.py` builds a clean
`aHPy-compiler==3.3.0.1.dev0` frontend wheel and validates its distribution
metadata and backend modules. A separate example then uses that exact wheel in
a real pip-created isolated build environment. `ahpy_build_backend` verifies
the installed frontend and forces Universal ABI for every hook, preventing
upstream `Cython` or the unrelated PyPI `ahpy` distribution from satisfying the
build requirement. The example's generated source and `.hpy0` binary are
audited, pip-installed into an empty target, and run in normal and HPy Debug
modes. The compiler-and-quality CI job executes the gate; hosted evidence is
green in job 88188395921. ADR 0012 defines identity/provenance and ADR 0004
still governs the host-specific wheel tag.

## CMake, Meson, and scikit-build-core gates

`ahpy_build_config` emits one selected-interpreter Universal contract used by
both native examples. `build_system_integration.py` generates their C through
aHPy, builds CMake `MODULE` and Meson `shared_module` targets, verifies exact
`.hpy0` output plus source/binary boundaries, and executes function/type
semantics in normal and Debug modes. The local macOS ARM64 CMake and Meson
paths and hosted Linux compiler-and-quality job 88188395921 are green.

`scikit_build_integration.py` separately builds the frontend wheel and a hashed
build-dependency wheelhouse, disables index access, and asks scikit-build-core
to generate/compile/package the maintained CMake project inside real PEP 517
isolation. The installed wheel passes ordinary import in normal and Debug
modes. Its CPython tag remains a host packaging smoke test under ADR 0004.

## Clean release-artifact and onboarding gate

`Tools/ahpy/release_artifact_integration.py` creates the frontend sdist from a
clean source copy and audits every member before using it. Absolute/traversal
paths, links, native binaries, bytecode, caches, VCS state, wrong metadata, and
missing compiler/build/runtime/license files fail closed. Exact HPy 0.9.0 and
setuptools 80.9.0 wheels are materialized first; index access is then disabled
for the wheel-from-sdist build and all clean-environment installations.

The gate creates a new virtual environment, installs the frontend only from the
local wheelhouse, builds and installs the maintained PEP 517 example, and runs
normal plus Debug LeakDetector semantics. It uninstalls both distributions
separately, verifies their absence from a temporary working directory, then
reinstalls and executes again. The compiler-and-quality workflow records
SHA-256 evidence for the sdist, frontend/example wheels, and exact build
dependencies. Local macOS ARM64/CPython 3.11 and hosted Linux job 88188395921
are green. Publication, cross-interpreter
packaging, standardized Universal wheel tags, and standardized Universal
extension-wheel reproducibility remain open.

## Frontend package reproducibility gate

`Tools/ahpy/verify_reproducible_packages.py` builds the real frontend sdist and
pure-Python wheel in two independent clean roots with a fixed epoch and hash
seed. Complete archive bytes must match. The initial sdist comparison exposed
40 generated directory/`PKG-INFO` timestamp differences despite identical file
payloads; the ADR 0015 streaming tar/gzip normalizer now fixes member order,
timestamps, ownership, and gzip header metadata. JSON evidence retains archive
hashes/sizes and exact Python/platform/build/setuptools provenance. This gate
does not claim reproducibility for a future standardized Universal extension
wheel.

## Local commands

```console
python3 -m unittest discover -s Tools/ahpy -p 'test_*.py'
python3 Tools/ahpy/doctor.py --python .venv-hpy09/bin/python --strict
python3 Tools/ahpy/scan_compatibility.py tests/ahpy/bootstrap_answer.pyx \
    --python .venv-hpy09/bin/python --json
python3 Tools/ahpy/setuptools_integration.py \
    --python .venv-hpy09/bin/python
python3 Tools/ahpy/direct_build_integration.py \
    --python .venv-hpy09/bin/python
python3 Tools/ahpy/pep517_integration.py \
    --python .venv-hpy09/bin/python --output /tmp/ahpy-pep517.json
python3 Tools/ahpy/build_system_integration.py \
    --python .venv-hpy09/bin/python --system all \
    --output /tmp/ahpy-build-systems.json
python3 Tools/ahpy/scikit_build_integration.py \
    --python .venv-hpy09/bin/python --output /tmp/ahpy-scikit-build.json
python3 Tools/ahpy/release_artifact_integration.py \
    --python .venv-hpy09/bin/python \
    --output /tmp/ahpy-release-artifacts.json
python3 Tools/ahpy/verify_reproducible_packages.py \
    --python .venv-hpy09/bin/python \
    --output /tmp/ahpy-package-reproducibility.json
.venv-hpy09/bin/python Tools/ahpy/test_generated_hpy.py \
    --python /absolute/path/to/.venv-hpy09/bin/python
.venv-hpy09/bin/python Tools/ahpy/test_fault_injection.py \
    --python /absolute/path/to/.venv-hpy09/bin/python
.venv-hpy09/bin/python Tools/ahpy/fuzz_supported_surface.py \
    --python /absolute/path/to/.venv-hpy09/bin/python \
    --seed 0xA4F9 --cases 48
python3 Tools/ahpy/run_sanitized_hpy.py --python python3 --cc gcc
python3 Tools/ahpy/build_portability_artifact.py \
    --python python3 --output /empty/artifact/directory
python3 Tools/ahpy/benchmark_hpy.py --python .venv-hpy09/bin/python \
    --output /tmp/ahpy-benchmark.json
```

The sanitizer command supports Linux GCC and Apple Clang. The ASan-linked
launcher makes the local signed Homebrew Python 3.11 lane executable without
mutating that interpreter; local macOS ARM64 normal/Trace/Debug plus ASan/UBSan
is green. The explicit `macos-15` hosted job is green in run 29685285138 and
remains the authoritative ARM64 platform gate. Full Cython CPython regression
coverage remains in the repository's existing `ci.yml`; the aHPy workflow adds
the focused C/C++ semantic oracle so backend changes receive a fast, explicit
parity signal.

The allocation/API fault-injection gate passes all 128 isolated normal/Debug
processes. An early ad-hoc stress run once produced an import `SystemError`
without an exception, while a later orchestration cancellation demonstrably
left two compiler process trees alive. The replacement bounded runner gives all
four gates independent temporary roots and process groups, retains hashed
stdout/stderr, recursively terminates descendants, and records timeout,
exit/signal, command, and duration evidence. Five full local rounds completed
without the `SystemError`: 640 fault selectors plus the generated corpus,
setuptools integration, and 48-case fuzz all passed. CI repeats one bounded
round. The stress-only O0 profile matches the hosted semantic matrix while
remaining separate from explicitly optimized direct-build and performance
validation; it changes optimization cost, not the HPy semantics and failure
paths under concurrency.

## Focused Python coverage

`Tools/ahpy/report_coverage.py` runs 653 focused tests under Python's built-in
line-event tracer, derives executable lines from nested code-object line
tables, and forces measured modules through a source-first finder so stale
compiled extensions cannot hide Python lines. It reports the Universal
backend, touched Cython frontend seam, and quality tools independently, plus
ownership, Runtime API, emitter, compiler-seam, and quality-tool feature
families. The current Python 3.11 validation records 100.00%, 45.80%, and
58.66%; Python 3.14.6 records 100.00%, 45.94%, and 58.70%. CI keeps
cross-version floors of 100%, 45%, and 50%. Schema 2 JSON and Markdown reports
include exact missing lines and compact missing ranges for actionable
follow-up.

Every external `uses:` entry in the aHPy workflow is pinned to a full
40-character commit SHA. A quality regression parses the complete workflow and
rejects tags, branches, and shortened hashes. The first hosted push exposed
seven 39-character `actions/upload-artifact` pins before checkout; the full-SHA
fix is locally YAML-valid and covered by the quality suite. The replacement
hosted run reached project code and exposed that the direct-build CLI depended
on the checkout root being present in `PYTHONPATH`. It now derives that root
from `Tools/ahpy/direct_build.py` itself, and a subprocess regression removes
`PYTHONPATH` and runs from an unrelated temporary working directory.

This is intentionally Python-source coverage. Generated C, native HPy runtime
behavior, child processes, allocation failures, and binary boundaries remain
covered by their dedicated semantic, Debug, fault-injection, sanitizer, fuzz,
and C/C++ oracle gates; they are not folded into an inflated Python percentage.

## Performance regression history

`Tools/ahpy/benchmark_hpy.py` compiles the same ten operations as generated
Universal HPy and as a handwritten public-HPy reference, validates semantics
and Debug handle cleanup, then alternates both modules across seven repeats.
The versioned budget file rejects relative runtime regressions in identity,
arithmetic, container, attribute, nested-call, and exception paths, plus large
extension-type construction/method calls, a shared Python-independent
external-C function, and generated-C or binary growth. Relative same-process comparisons are mandatory;
absolute nanoseconds are recorded for diagnosis but never compared across
unrelated CI hosts.

Three initial Apple Silicon/CPython 3.11/HPy 0.9 validation runs passed. Before
the positional-only contract correction, their
observed generated/reference ranges were 4.73–5.14× for identity, 4.11–4.37×
for arithmetic, 3.31–4.10× for containers, 2.24–2.78× for attributes,
1.59–1.85× for nested calls, and 0.99–1.07× for exceptions. Generated binary
size was approximately 1.013× the handwritten reference in the first recorded
run. These costs are visible baseline facts, not optimization claims. Each CI
run uploads its timestamped JSON, raw samples, build identity, sizes, ratios,
budget source, and violations as a uniquely named history artifact.

The corrected generated and handwritten fixtures now reject the same keyword
calls. With direct-name borrowing enabled only for API-borrowed attribute
receivers and zero-argument callables, the follow-up Universal ratios were
0.82× identity, 0.87× attribute, and 1.02× call. Trace reports exactly one API
call and zero Dup/Close churn on both generated and reference attribute/call
paths; the corresponding ceilings are now 1.5×.

The next follow-up emits `HPyFunc_VARARGS` for two-or-more required
positional-only arguments, binding the call-scoped borrowed `args[]` handles
without the keyword parser/tracker. Direct Name operands are also borrowed for
binary APIs and fixed sequence-builder items under an evaluation-order proof.
Arithmetic now matches the reference at 1 API call and container construction
at 4, both with zero Dup/Close churn. Their tightened-budget Universal ratios
were 0.97× and 1.07×, so both runtime ceilings are 1.5×. Normal/Trace/Debug,
186 emitter tests, side-effectful-right evaluation regressions, closure and
extension-method signature checks, and all 128 fault selectors pass.

The extension-type follow-up borrows incoming field owners and direct Name
field-store values, loads type/module owners only for actual constant/default/
global/builtin/closure access, and binds positional-only initializer slot
arrays without a tracker. Type-method Trace is now 2.003 calls versus 2.002 for
the reference with zero generated Dup/Close; type construction is 3 versus 2,
where the sole extra call is the generated `__cinit__` `AsStruct`. Tightened-
budget Universal ratios were 1.02× type creation and 0.96× type method, so both
ceilings are 1.5×. The branch snapshot regression and isolated large-type native
compile prevent lazy owner C names from escaping their declaration scope.

The external-C literal follow-up bypasses the HPy object round trip only for
side-effect-free numeric constants proven portable for the declared scalar C
type. Dynamic, non-finite, ambiguous plain-`char`, and out-of-range values stay
on the checked conversion path. External-C Trace is now exactly 1 generated
and 1 reference API call per iteration with zero Dup/Close churn; the measured
Universal ratio is 0.99× and its ceiling is now 1.5×. Normal/Trace/Debug,
188 emitter tests, the checked-fallback regressions, and all 128 fault selectors
pass.

The expanded local run measured 4.57× for extension-type construction, 5.89×
for a field-returning extension method, and 5.70× for the external-C wrapper
before its literal-lowering optimization.
The generated and reference extensions compile the same external C source.
Supported sequence-index iteration now has equivalent generated/handwritten
semantics and an initial 2.50× ceiling around the observed 1.86–2.00× local range;
hosted same-HEAD calibration remains mandatory. True iterator-protocol and
typed-memoryview numbers remain deliberately absent while those HPy 0.9
surfaces are blocked.

Peak RSS is measured in two separate clean children, each running 10,000
iterations per operation, so one module cannot inherit the other's process
high-water mark. The first expanded local result was 35,127,296 bytes for the
generated module and 35,258,368 bytes for the handwritten reference (0.996×).
The record also retained 0.356 seconds frontend time, 0.936 seconds combined
native build time, and exact C/binary sizes. These local absolute values are
diagnostic evidence rather than cross-host limits.

Each benchmark record also contains a separate `HPY=trace` measurement over
1,000 invocations per operation. It stores exact API deltas, total calls per
iteration, and `ctx_Dup`/`ctx_Close` churn for both generated and handwritten
modules. The initial local baseline is documented in
`audits/m9-trace-baseline.md`; the counts guide ownership work but are not
release thresholds until hosted history and failure-path proofs exist.

The same benchmark JSON contains an `abi_matrix` with three deliberately
separate profiles. Classic Cython records standalone nanoseconds, source and
binary size, build times, and peak RSS. HPy CPython ABI and HPy Universal each
record generated-versus-handwritten timings within their own ABI. No cross-ABI
ratio is treated as a release threshold. The initial evidence and exact
measurement contract are in `audits/m9-abi-performance-baseline.md`.

Each new benchmark history record also contains exact source-commit and GitHub
Actions run provenance. `Tools/ahpy/calibrate_performance_budgets.py` requires
at least five unique successful records from the same commit, repository,
workflow, Python/HPy/platform/compiler/build-configuration identity, resource
settings, and measurement contract. It rejects
local reports, duplicate attempts, mixed cohorts, existing violations, failed
Debug evidence, resource-schema gaps, and footprint/large-source byte drift.
Its output includes runtime, frontend/native build-time, peak-RSS, footprint,
and large-type frontend/O0 distributions, is explicitly proposal-only, and
cannot rewrite the versioned budget. The collection and
maintainer review procedure is documented in
`performance-release-gate.md`; hosted same-HEAD history is still required
before the current conservative ceilings become release budgets.

The sequence-index iteration follow-up borrows its loop source only when the
source is an incoming call-scoped argument. Rebindable owned locals retain
materialization, and a body that rebinds the original argument name passes
normal/Trace/Debug plus all 128 fault selectors. Generated Trace falls from 38
to 36 calls per iteration (9 Dup/17 Close versus the reference's 1/8); the
temporary runtime ceiling remains unchanged pending hosted calibration.
The manual-only `ahpy-performance-calibration.yml` workflow provides the
bounded collection path: five isolated Ubuntu/Python 3.11/HPy 0.9 matrix
samples for one exact selected commit, distinct sample provenance and
artifacts, then one dependent proposal job. It has read-only permissions and
cannot aggregate a partial matrix.

The two-root package reproducibility gate retains only the first root's
immutable sdist and wheel before starting the second build. This preserves the
byte-for-byte comparison contract while preventing two complete copied
source/build trees from becoming the gate's peak disk requirement.

The record additionally regenerates the large extension-type corpus and runs
one isolated native compile at `-O0` and `-O3`, with a 60-second ceiling. O0 is
the required C-validity/liveness gate and O3 is a bounded diagnostic
per optimization. The current Apple Clang 21 result is 1.59 and 5.29 seconds
(3.32×) for 4,978,328 bytes/87,259 lines. Accidentally running two full-corpus
`bootstrap_answer.c -O3` builds concurrently later reproduced multi-minute
optimizer pressure, confirming concurrency as a trigger without changing the
isolated large-type timing authority. The stress gate remains `-O0` for bounded
parallel semantics testing.
