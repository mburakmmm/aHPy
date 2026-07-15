# aHPy development tools

`build_inventory.py` scans the current Cython compiler and utility sources for
Python C-API calls and object types. It emits deterministic JSON to standard
output. Its initial classification is intentionally conservative: every symbol
is unreviewed, and an unknown symbol is considered unsupported until a public
HPy mapping and ownership contract are validated.

Run the unit test from this directory:

```console
python3 -m unittest -v test_build_inventory.py
```

Regenerate the baseline inventory from the repository root and review its diff
before updating `docs/ahpy/audits/capi-inventory.json`.

`test_minimal_hpy.py` builds the handwritten Universal ABI reference module.
`test_generated_hpy.py` applies the same normal/debug execution and leak gates
to C emitted directly from `tests/ahpy/bootstrap_answer.pyx` by the strict
bootstrap `hpy-universal` backend. Its executable corpus includes implemented
scalar literals plus empty, fixed-size, and nested list/tuple returns. Its
dictionary corpus exercises allocation and insertion cleanup. The `HPyFunc_O`
cases verify borrowed positional arguments, owned duplication, and keyword
rejection. Item/attribute reads exercise both successful owned returns and
runtime exception cleanup. Zero/one-argument calls and bound methods cover
successful returns plus callable-raised exception cleanup. Both tools use the
pinned environment declared in
`tests/ahpy/requirements-hpy09.txt`.

The generated test now executes the same semantic corpus in HPy release,
Trace, and Debug modes. Its binary audit uses `nm`/`llvm-nm` on Unix and
`dumpbin`, `llvm-nm`, or `objdump` on Windows, and fails closed if no symbol
reader exists. Always pass `--python` in CI so the selected HPy environment is
unambiguous.

`test_quality_gates.py` checks exact HPy pins, binary-import parsing, the
declared platform/compiler matrix, sanitizer setup, and byte-for-byte
deterministic Universal source generation. `run_sanitized_hpy.py` builds and
runs the real generated corpus with GCC ASan/UBSan on Linux and Apple Clang on
macOS, provided the selected Python executable permits dynamic sanitizer
preloading. LeakSanitizer is disabled in that mixed
instrumented-extension/uninstrumented-interpreter process; HPy Debug Mode
remains the mandatory handle-leak gate until a validated LSan suppression
policy exists.

`doctor.py` is the repository's `ahpy doctor` equivalent. It probes the exact
interpreter path without resolving a virtual-environment symlink, validates the
machine-readable stable/development HPy pins, checks the public `hpy.h` header,
and discovers C compilers plus supported binary symbol readers. Text and JSON
reports share the same versioned checks; `--strict` rejects early-warning pins.

`report_nightly_environment.py` produces schema-versioned provenance for the
two moving early-warning jobs. It rejects a requested/actual interpreter minor
mismatch and requires HPy branch-tip installs to resolve from the exact
official repository/ref to a full 40-character commit recorded by pip's
`direct_url.json`. The schedule/manual-only jobs upload this report alongside
pip's install report and remain allowed-failure; neither can expand the pinned
support matrix.

`scan_compatibility.py` compile-scans one or more sources with no ABI fallback,
checks successful generated header boundaries, and emits text or schema-versioned
JSON. Direct `cpython.*`/`Python.h` dependencies and backend diagnostics receive
stable migration action IDs; expected rejections and unclassified compiler
errors have distinct exit codes. See `docs/ahpy/migration-scanner.md`.

`build_diagnostic_catalog.py` inventories every strict Universal
`unsupported(...)` call site across module, statement, expression, and emitter
layers. The committed schema-versioned JSON records source ownership, message
templates, and scanner migration actions; the tool's `--check` mode and the
unit suite prevent it from becoming stale.

`report_coverage.py` uses Python's line-event tracer and code-object line
tables, so the focused coverage gate needs no third-party package. It reports
the Universal backend, touched Cython frontend seam, and aHPy quality tools
separately, while also running ownership-model, Runtime API, emitter,
compiler-seam, and quality-tool test families independently. The CI command
enforces conservative floors of 71%, 25%, and 35% respectively. Generated C,
native execution, and child-process coverage deliberately remain the
responsibility of the real HPy, fault-injection, sanitizer, and C/C++ oracle
gates rather than being misreported as Python line coverage.

`setuptools_integration.py` copies the maintained
`examples/ahpy_setuptools` sources to a temporary build, calls
`cythonize(..., runtime_backend="hpy-universal")`, passes those extensions to
HPy's `hpy_ext_modules`, audits the emitted C and `.hpy0` binary, and runs the
module-function plus pure-type semantics in normal and Debug modes. It also
inspects and pip-installs the current wheel. ADR 0004 explains why its
CPython-specific compatibility tag is not a Universal distribution claim.

`test_fault_injection.py` generates one dedicated Universal module and
interposes test-only wrappers after the public HPy header. Its 116 isolated
normal/Debug processes cover scalar allocation; nested list/tuple builder
builds; dictionary insertion; direct/expanded calls; attribute/item
read/write/delete; every generated type creation; and every module/type
publication position. Each injected boundary must raise exact `MemoryError`,
every one-past selector must succeed, partial builders and independently owned
intermediates must clean up, and the binary must remain CPython-symbol-free.
The interposition never enters shipped generated source.

`stress_parallel_hpy.py` launches the fault, generated-corpus, setuptools, and
fixed-fuzz gates together in independently rooted process groups. Every child
has its own `TMPDIR`/`TEMP`/`TMP`, stdout/stderr logs, deadline, exit/signal
record, and recursive timeout cleanup; a killed orchestration cannot leave
native compiler descendants behind. Its documented stress-only `-O0 -g0`
profile preserves the same HPy semantic/failure paths while excluding the
pathological Apple Clang time spent optimizing the large type corpus at `-O3`.
Normal runtime and release gates retain their ordinary build flags. The local
acceptance run completed five full 48-case rounds and all 580 fault selectors;
CI repeats one bounded round and uploads the JSON plus hashed logs.

`coverage_guided_fuzz.py` deterministically generates 64 candidates across 16
supported feature families. It warms the compiler, traces five frontend/backend
files while compiling every candidate, and greedily retains candidates that
add line coverage or a previously unseen family. The selected corpus is then
compiled once, source/binary audited, and compared to execution of the same
Python source in normal and HPy Debug modes. Seed `0xC0A4F9` currently selects
16 mutations and a 3,864-line compiler frontier; three unit tests guard source
determinism, greedy selection, and isolation from global random state.

`benchmark_hpy.py` builds six equivalent operations twice: once from aHPy
generated Universal C and once from a handwritten public-HPy reference. It
alternates both modules across seven repeats, records per-call medians and raw
samples for identity/call overhead, arithmetic, containers, attributes, nested
calls, and exceptions, and rejects ratios or source/binary sizes outside
`tests/ahpy/performance-budgets.toml`. The exact HPy and interpreter family are
part of the budget contract. Both binaries receive source/import audits and a
separate Debug `LeakDetector` semantic pass. CI uploads the timestamped JSON
result under a run-specific artifact name, forming append-only benchmark
history without comparing noisy absolute timings across different hosts.

`build_portability_artifact.py` builds `bootstrap_answer` and
`bootstrap_types` once with the CPython 3.11/HPy 0.9 builder, rejects forbidden
binary imports, copies the `.hpy0` files and loader stubs without rebuilding,
and writes sizes plus SHA-256 digests to `artifact-manifest.json`.
`portability_smoke.py` is then executed against those exact files by the pinned
PyPy and GraalPy hosted jobs. Until both first runs are green, these jobs remain
allowed-failure early warnings rather than support claims.

`verify_reproducible_artifact.py` performs two independent builds with a fixed
`SOURCE_DATE_EPOCH`, deterministic archive mode, and compiler
file/debug-prefix maps. It requires identical file sets and byte content,
including both `.hpy0` binaries and their SHA-256 manifest. This is the
Universal portability-artifact gate; future sdist/wheel archive reproducibility
remains a separate packaging task.
