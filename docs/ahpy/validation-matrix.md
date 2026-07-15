# Validation matrix and release gates

The dedicated `.github/workflows/ahpy-universal.yml` workflow separates
release claims from early warnings. Merely declaring a job does not make a
platform supported: a release matrix entry becomes supported only after its
first green hosted run is recorded and remains required for release branches.

## Required stable lane

The stable lane installs `hpy==0.9.0` and `setuptools==80.9.0` on Python 3.11.
Every platform job generates C directly through `hpy-universal`, compiles a
`.hpy0` module, audits generated source and undefined binary imports, then runs
the semantic corpus in HPy release, Trace, and Debug modes. Debug Mode uses
`LeakDetector` for backend handle leaks.

| Runner | Architecture | Compiler | Initial state |
|---|---:|---|---|
| `ubuntu-24.04` | x86-64 | GCC | declared; hosted run pending |
| `ubuntu-24.04` | x86-64 | Clang | declared; hosted run pending |
| `ubuntu-24.04-arm` | ARM64 | GCC | declared; hosted run pending |
| `macos-15-intel` | x86-64 | Apple Clang | declared; hosted run pending |
| `macos-15` | ARM64 | Apple Clang | declared; hosted run pending |
| `windows-2025` | x86-64 | MSVC | declared; hosted run pending |

The runner labels follow GitHub's current hosted-runner reference:
<https://docs.github.com/actions/reference/runners/github-hosted-runners>.
Explicit labels prevent a moving `*-latest` alias from silently changing a
release platform.

## HPy development early warning

`tests/ahpy/hpy-versions.toml` is authoritative. The development requirement
uses a 40-character commit rather than `master`. Python 3.11 is the validated
development lane. Python 3.14 is allowed to fail as an experimental signal
because the pinned revision currently crashes the generated corpus on the
locally tested macOS arm64 configuration. A future green result must not alter
stable support until the pin, compatibility audit, and support matrix are
updated together.

## Same-binary interpreter gate

The builder job uses CPython 3.11 and HPy 0.9 exactly once. It generates and
builds the module-function and pure-extension-type corpora, audits both
binaries, copies each `.hpy0` file and Python loader unchanged, and records
SHA-256 plus size metadata. PyPy 7.3.23 (Python 3.11.15 compatible) and GraalPy
25.1.3 (Python 3.12 compatible) download that one artifact rather than
rebuilding it. Their exact setup identifiers live in
`tests/ahpy/interpreters.toml`. Both jobs are early warnings until their first
green hosted executions are recorded; only then may `continue-on-error` be
removed and the support matrix reconsidered.

Two independent local portability-artifact builds use a fixed
`SOURCE_DATE_EPOCH`, `ZERO_AR_DATE`, and compiler file/debug-prefix maps. The
resulting module binaries, loader stubs, smoke program, and manifest are
byte-identical. `verify_reproducible_artifact.py` repeats this comparison in CI.
This does not yet claim reproducible sdist or wheel archives.

## Sanitizers and deterministic output

The Linux GCC and macOS ARM64 Apple Clang jobs instrument the generated
extension and bundled HPy runtime with ASan and UBSan. The runner discovers and
preloads the compiler-matching `libasan` or Apple dynamic ASan runtime before
Python imports the extension, then stops at the first diagnostic.
LeakSanitizer is intentionally disabled because the host CPython process is
not built with matching instrumentation; unsuppressed interpreter allocations
would not be an actionable backend signal. HPy Debug Mode remains the mandatory
leak detector. A separately reviewed LSan/Valgrind lane with versioned
suppressions is still required.

`Tools/ahpy/test_quality_gates.py` compiles the same source twice in independent
directories and compares the emitted bytes. This gate found and fixed an
unordered method-cleanup epilogue; deterministic ordering is now enforced by
the emitter rather than normalized after generation.

The deterministic fault-injection gate wraps APIs only in a test copy of
generated source. It independently fails all three `HPyLong_FromLongLong`
conversions, every nested list/tuple builder build, three dictionary inserts,
four direct call layouts, expanded tuple/dict calls, three attribute and item
reads, and attribute/item set/delete. Every selected failure must remain an
exact `MemoryError`; every one-past selector must succeed; all independently
owned intermediates, builder consumption/cancellation, the undefined-symbol
ABI audit, and Debug `LeakDetector` must remain clean. The import lane counts
and fails all three `HPyType_FromSpec` calls and every generated
`HPy_SetAttr_s` publication position, requiring exact `MemoryError`, removal
from `sys.modules`, collection, and successful one-past imports. The resulting
matrix passes 116 isolated normal/Debug processes.

This expansion exposed partial module initialization losing its active error
after rollback. The emitter now records successful module publications,
matches `MemoryError` before cleanup, rolls publications back in reverse order,
and re-establishes only that positively matched error because HPy 0.9 exposes
no public fetch/restore API. Non-memory errors are not speculatively replaced.

`Tools/ahpy/fuzz_supported_surface.py` deterministically generates 48 functions
from seed `0xA4F9`. The grammar combines nested containers, continuing
conditionals, mutating `while` loops, fixed-sequence `for` loops, in-place
operators, and slice replacement. One Universal module is generated, audited,
built, and compared function-by-function with `exec` of the identical source as
the pure-Python oracle in normal and HPy Debug modes. The first run exposed a
backend crash on transformed nested statement lists; recursive source-ordered
flattening and a focused regression now guard it. The same gate also compiles a
deterministic rejected-input corpus covering set
construction, generic iteration, `except as`, nonterminal handlers, and
generators; every case must fail with its actionable Universal diagnostic and
no Python traceback or compiler `InternalError`. Return/raise from loops and
mixed terminating/continuing branches are executable supported surface rather
than rejected fuzz cases.

`Tools/ahpy/coverage_guided_fuzz.py` warms the compiler, compiles 64 mutations
under Python line tracing, and greedily retains a candidate when it adds a new
line in `HPyModuleWriter`, `HandleModel`, `RuntimeAPI`, `Nodes`, or `ExprNodes`,
or introduces a new feature family. Seed `0xC0A4F9` selects 16 candidates,
preserves all 16 families, and reaches a 3,864-line compiler frontier. The
combined corpus covers arithmetic, containers, direct/expanded/keyword calls,
globals, terminal handlers, loops, slices, comparisons, imports, mutation,
starred values, in-place operators, and conditional expressions. It is
source/binary audited and compared with execution of the identical Python
source in normal and Debug modes.

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

## Local commands

```console
python3 -m unittest discover -s Tools/ahpy -p 'test_*.py'
python3 Tools/ahpy/doctor.py --python .venv-hpy09/bin/python --strict
python3 Tools/ahpy/scan_compatibility.py tests/ahpy/bootstrap_answer.pyx \
    --python .venv-hpy09/bin/python --json
python3 Tools/ahpy/setuptools_integration.py \
    --python .venv-hpy09/bin/python
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

The sanitizer command supports Linux GCC and Apple Clang. The local signed
Homebrew Python 3.11 executable on macOS 26 strips
`DYLD_INSERT_LIBRARIES`, so that local Apple run is not recorded as green; the
explicit `macos-15` hosted job remains the authoritative pending gate. Full
Cython CPython regression coverage remains in the repository's existing
`ci.yml`; the aHPy workflow adds the focused C/C++ semantic oracle so backend
changes receive a fast, explicit parity signal.

The allocation/API fault-injection gate passes all 116 isolated normal/Debug
processes. An early ad-hoc stress run once produced an import `SystemError`
without an exception, while a later orchestration cancellation demonstrably
left two compiler process trees alive. The replacement bounded runner gives all
four gates independent temporary roots and process groups, retains hashed
stdout/stderr, recursively terminates descendants, and records timeout,
exit/signal, command, and duration evidence. Five full local rounds completed
without the `SystemError`: 580 fault selectors plus the generated corpus,
setuptools integration, and 48-case fuzz all passed. CI repeats one bounded
round. The stress-only O0 profile is deliberately separate from normal O3
release validation; it changes optimization cost, not the HPy semantics and
failure paths under concurrency.

## Focused Python coverage

`Tools/ahpy/report_coverage.py` runs 352 focused tests under Python's built-in
line-event tracer and derives executable lines from nested code-object line
tables. It reports the Universal backend, touched Cython frontend seam, and
quality tools independently, plus ownership, Runtime API, emitter,
compiler-seam, and quality-tool feature families. The Python 3.11 validation
records 72.61%, 25.20%, and 40.57%; Python 3.14 records 71.65%, 25.07%, and
40.62%. CI therefore fails below conservative cross-version floors of 71%,
25%, and 35%.

This is intentionally Python-source coverage. Generated C, native HPy runtime
behavior, child processes, allocation failures, and binary boundaries remain
covered by their dedicated semantic, Debug, fault-injection, sanitizer, fuzz,
and C/C++ oracle gates; they are not folded into an inflated Python percentage.

## Performance regression history

`Tools/ahpy/benchmark_hpy.py` compiles the same six operations as generated
Universal HPy and as a handwritten public-HPy reference, validates semantics
and Debug handle cleanup, then alternates both modules across seven repeats.
The versioned budget file rejects relative runtime regressions in identity,
arithmetic, container, attribute, nested-call, and exception paths, plus large
generated-C or binary growth. Relative same-process comparisons are mandatory;
absolute nanoseconds are recorded for diagnosis but never compared across
unrelated CI hosts.

Three initial Apple Silicon/CPython 3.11/HPy 0.9 validation runs passed. Their
observed generated/reference ranges were 4.73–5.14× for identity, 4.11–4.37×
for arithmetic, 3.31–4.10× for containers, 2.24–2.78× for attributes,
1.59–1.85× for nested calls, and 0.99–1.07× for exceptions. Generated binary
size was approximately 1.013× the handwritten reference in the first recorded
run. These costs are visible baseline facts, not optimization claims. Each CI
run uploads its timestamped JSON, raw samples, build identity, sizes, ratios,
budget source, and violations as a uniquely named history artifact.
