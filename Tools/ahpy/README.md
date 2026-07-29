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
macOS. Linux preloads the compiler-selected `libasan`; macOS pins the native
architecture and runs through a temporary `Py_BytesMain` launcher linked to
the compiler-selected Apple ASan runtime, avoiding signed-launcher dyld
filtering and `universal2` cross-architecture links. Both compile the generated
corpus at `-O0` with frame pointers. `ASAN_OPTIONS` sets `detect_leaks=0`
because the host CPython process is not built with matching instrumentation;
that ASan lane is therefore not an LSan leak gate. LeakSanitizer remains
disabled in that mixed
instrumented-extension/uninstrumented-interpreter process. The independent
schedule/manual Linux `run_lsan_hpy.py` lane runs a mandatory C leak positive
control and then all five generated-corpus normal/Trace/Debug runtime processes
under Valgrind, failing on definite leaks through the versioned suppression
file. Manual run `29906185775`, job `88878105102`, proved the positive control,
five clean generated-runtime logs, and zero active suppressions; the
schedule/manual job is now required. HPy Debug Mode remains the mandatory
handle-leak gate as well.

`run_appverifier_hpy.py` is the independent Windows heap-corruption diagnostic.
On schedule/manual runs it discovers the 64-bit SDK tools fail closed, applies
Application Verifier Basics and GFlags full page heap to unique target images,
and requires an out-of-bounds native positive control to produce an XML error.
It then runs all five generated-corpus processes through a uniquely copied
Python executable; a startup probe must find `verifier.dll` in every process,
and every exported runtime XML log must contain no error severity. Preflight,
queries, stdout/stderr, XML, raw AppVerifier logs, process counts, and cleanup
results are uploaded. This is not a native leak gate; HPy Debug and Linux
Valgrind retain their separate leak responsibilities. The Windows job remains
allowed-failure until its first hosted artifact is reviewed.

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

`report_coverage.py` uses Python's line-event tracer, code-object line tables,
and a source-first import finder, so the focused coverage gate needs no
third-party package and cannot accidentally trace a stale compiled extension.
It reports the Universal backend, touched Cython frontend seam, and aHPy
quality tools separately, while also running ownership-model, Runtime API,
emitter, compiler-seam, and quality-tool test families independently. Schema 2
JSON and Markdown output include exact missing lines and compact missing
ranges. The CI command enforces floors of 100%, 45%, and 41% respectively.
Generated C, native execution, and child-process coverage deliberately remain
the responsibility of the real HPy, fault-injection, sanitizer, and C/C++
oracle gates rather than being misreported as Python line coverage.

`setuptools_integration.py` copies the maintained
`examples/ahpy_setuptools` sources to a temporary build, calls
`cythonize(..., runtime_backend="hpy-universal")`, passes those extensions to
HPy's `hpy_ext_modules`, audits the emitted C and `.hpy0` binary, and runs the
module-function plus pure-type semantics in normal and Debug modes. It also
inspects and pip-installs the current wheel. ADR 0004 explains why its
CPython-specific compatibility tag is not a Universal distribution claim.

`direct_build.py` is the versioned non-setuptools build API/CLI. It probes the
selected interpreter, creates an auditable Universal compile/link plan, uses
HPy's helper static library or source fallback, refuses unsafe output reuse,
activates the installed MSVC toolchain through `vswhere`/`vcvarsall` when
needed, and verifies the generated source and linked binary. `direct_build_integration.py`
generates the maintained module and loads the direct artifact through public
`hpy.universal.load` in normal and Debug modes. See
`docs/ahpy/direct-build.md`; this path intentionally does not create a wheel or
loader stub.

`pep517_integration.py` first builds the exact `aHPy-compiler` frontend wheel
from a clean source copy, then lets pip create a genuine isolated build
environment for `examples/ahpy_pep517`. The aHPy PEP 517 backend rejects
upstream-Cython/unrelated-`ahpy` substitution and non-Universal ABI requests.
The gate audits the emitted source and `.hpy0`, installs the host-tagged wheel,
and runs normal/Debug semantics. See `docs/ahpy/pep517.md` and ADR 0012.

`build_system_config.py` renders the installed `ahpy_build_config` Universal
toolchain contract for CMake or Meson. `build_system_integration.py` uses the
maintained native examples and verifies both build systems through binary
audits and normal/Debug loading. `scikit_build_integration.py` adds a closed,
no-index PEP 517 wheelhouse around the maintained scikit-build-core/CMake
package and proves ordinary pip install/import. See `docs/ahpy/build-systems.md`.

`release_artifact_integration.py` builds the frontend sdist from a clean source
copy, rejects unsafe or incomplete archive contents, and constructs the
frontend wheel with index access disabled and exact HPy/setuptools inputs. It
then creates a fresh virtual environment, executes the maintained PEP 517
example in normal/Debug modes, and proves clean uninstall/reinstall cycles for
both distributions. The JSON report hashes all artifacts and build-dependency
wheels. See `docs/ahpy/onboarding.md` and ADR 0014.

`prepare_publish_dist.py` is a deliberately network-free package-index
rehearsal. It requires a green schema-2 release bundle for the exact checkout,
rehashes every selected file, rejects a non-empty output directory, and copies
only the `aHPy-compiler` sdist and `py3-none-any` frontend wheel. Dependency
and example wheels plus evidence metadata remain excluded. See
`docs/ahpy/publishing.md`.

`verify_reproducible_packages.py` builds the `aHPy-compiler` sdist and
pure-Python wheel from two independent clean roots. A fixed epoch/hash seed and
streaming tar/gzip metadata normalization make complete archive bytes the
comparison unit; the JSON result retains hashes, sizes, and exact
interpreter/build-tool provenance. ADR 0015 records why logical payload equality
is insufficient. Standardized Universal extension-wheel reproducibility stays
open.

`test_fault_injection.py` generates one dedicated Universal module and
interposes test-only wrappers after the public HPy header. Its 128 isolated
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
Hosted semantic jobs likewise use `-O0` (or MSVC `/Od`); direct-build and
performance gates retain their own explicit optimization flags. The local
acceptance run completed five full 48-case rounds and all 640 fault selectors;
CI repeats one bounded round and uploads the JSON plus hashed logs.

`coverage_guided_fuzz.py` deterministically generates 64 candidates across 16
supported feature families. It warms the compiler, traces five frontend/backend
files while compiling every candidate, and greedily retains candidates that
add line coverage or a previously unseen family. The selected corpus is then
compiled once, source/binary audited, and compared to execution of the same
Python source in normal and HPy Debug modes. Seed `0xC0A4F9` currently selects
16 mutations and a 4,141-line compiler frontier; three unit tests guard source
determinism, greedy selection, and isolation from global random state.

`benchmark_hpy.py` builds ten equivalent operations twice: once from aHPy
generated Universal C and once from a handwritten public-HPy reference. It
alternates both modules across seven repeats, records per-call medians and raw
samples for identity/call overhead, arithmetic, containers, attributes, nested
calls, exceptions, extension-type construction/method calls, and a shared
Python-independent external-C function, and rejects ratios or source/binary sizes outside
`tests/ahpy/performance-budgets.toml`. The exact HPy and interpreter family are
part of the budget contract. Both binaries receive source/import audits and a
separate Debug `LeakDetector` semantic pass. Sequence-index iteration is
measured; true iterator-protocol loops and typed memoryviews remain explicitly
blocked/non-comparable on HPy 0.9. Each implementation also runs all ten
operations in its own clean child to record peak RSS without cross-module
high-water contamination. CI uploads the timestamped JSON
result under a run-specific artifact name, forming append-only benchmark
history without comparing noisy absolute timings across different hosts.
New reports also carry the exact source commit and, on GitHub Actions, the
repository, workflow, job, run ID, run attempt, and GitHub SHA. Release-budget
promotion uses `calibrate_performance_budgets.py`, which accepts at least five
unique successful reports for one exact commit and cohort, rejects local or
mixed evidence, and emits a proposal without editing the versioned budget.
The manual `ahpy-performance-calibration.yml` workflow collects five isolated
runner samples for the selected commit and invokes that proposal gate only
after every matrix entry succeeds.
The collection and review contract is in
`docs/ahpy/performance-release-gate.md`.

The benchmark also launches a separate HPy Trace child for 1,000 calls per
operation and records exact API deltas, calls per iteration, plus
`ctx_Dup`/`ctx_Close` churn for generated and handwritten modules. The initial
baseline exposed tracker/dup overhead in arithmetic, containers, attributes,
and extension types plus the external-C wrapper. Positional-only functions with
two or more required arguments now use `HPyFunc_VARARGS`, avoiding the keyword
parser/tracker. Direct live names are also borrowed for binary operands and
fixed list/tuple builder items when evaluation order proves that safe.
Arithmetic and container paths therefore match the references at one and four
API calls respectively with zero Dup/Close churn, as attribute and zero-argument
call paths already do. The exception path also matches the reference API count.
Extension-field owners and values now remain borrowed where their call-scoped
lifetime proves that safe, while type/module owners are loaded only when a
method actually needs constants, defaults, globals, builtins, or closures.
Positional-only initializers also bind their raw slot argument array without a
tracker. Type methods therefore match the handwritten two-call Trace contract;
type creation adds only the separate generated `__cinit__` `AsStruct` call.
Representable numeric literal arguments to validated external-C scalar
functions are emitted as explicitly typed, portable C literals instead of
being boxed and unboxed through HPy. Dynamic, non-finite, ambiguous plain-char,
and out-of-portable-range values retain checked HPy conversion. The external-C
path therefore matches the handwritten one-call Trace contract with zero
Dup/Close churn.
These are optimization candidates, not permission to remove proven cleanup.

The same invocation records a three-profile ABI matrix without blending their
costs: classic Cython has standalone timings, HPy CPython ABI has its own
generated/handwritten ratios, and HPy Universal retains its independent
generated/handwritten ratios and release regression gate. Each profile records
its applicable build, footprint, and clean-process peak-memory evidence.

The performance invocation also regenerates the large `bootstrap_types.pyx`
corpus and compiles its Universal C once at `-O0` and once at `-O3`, each under
a 60-second ceiling. `-O0` is the required C-validity/liveness gate; `-O3` is
a bounded diagnostic. This keeps native optimizer time distinct from
runtime ratios. The isolated Apple Clang 21 baseline was 1.59/5.29 seconds for
the 4.98 MB, 87,259-line C file. Ubuntu GCC 13 exceeded both 60- and 180-second
O3 trials while O0 completed near 5 seconds, so O3 duration is recorded without
misclassifying optimizer cost as a backend correctness regression.

`build_portability_artifact.py` builds `bootstrap_answer` and
`bootstrap_types` once with the CPython 3.11/HPy 0.9 builder, rejects forbidden
binary imports, copies the `.hpy0` files and loader stubs without rebuilding,
and writes sizes plus SHA-256 digests to `artifact-manifest.json`. Its hosted
correctness build uses `-O0`; cross-interpreter portability does not depend on
optimizer throughput.
`portability_smoke.py` revalidates every digest and runs imports/semantics in
four isolated subprocess stages. Python `hpy.universal` runtimes use the
unchanged stubs; native HPy runtimes use a temporary directory containing only
the unchanged binaries so CPython stubs cannot shadow native loading. The
pinned PyPy and GraalPy jobs remain allowed-failure early warnings until both
first runs are green.

`verify_reproducible_artifact.py` performs two independent builds with a fixed
`SOURCE_DATE_EPOCH`, deterministic archive mode, and compiler
file/debug-prefix maps. It requires identical file sets and byte content,
including both `.hpy0` binaries and their SHA-256 manifest. This is the
Universal portability-artifact gate; future sdist/wheel archive reproducibility
was split into the now-green frontend archive gate and the still-open future
standardized Universal extension-wheel gate.
