# Pinned third-party pilot matrix

PRD-8 uses four real upstream projects to measure library-porting behavior
without implying general Cython compatibility. The machine-readable source of
truth is `tests/ahpy/pilots.toml`; a moving branch or release name is never
sufficient evidence. Every selection records a full commit SHA, SPDX license,
license path, exact sources, expected initial status and required migration
actions.

## Selected sources

| Category | Project and pinned commit | License | Selected boundary | Initial contract |
| --- | --- | --- | --- | --- |
| Pure Cython | [cython-package-example 0.1.7 `7dfb3905259c5c7a82770806e5e558999eef79ce`](https://github.com/FedericoStra/cython-package-example/commit/7dfb3905259c5c7a82770806e5e558999eef79ce) | MIT | `answer.pyx`, `fibonacci.pyx`, and `utils.pyx`, with no direct Python C API | rejected until typed `cpdef`/`cdef` entry points and cross-module Cython cimports move to supported Python boundaries |
| Python-independent C wrapper | [murmurhash `58831632dab79389a5cee7715fb688ef2297ff78`](https://github.com/explosion/murmurhash/commit/58831632dab79389a5cee7715fb688ef2297ff78) | MIT | Cython wrapper plus MurmurHash2/3 C/C++ sources | rejected while byte-buffer pointers cross the Universal boundary |
| Extension type, GC, inheritance | [frozenlist `351ad4bb62b30d943b0aa7463a0f85f7339b6ada`](https://github.com/aio-libs/frozenlist/commit/351ad4bb62b30d943b0aa7463a0f85f7339b6ada) | Apache-2.0 | `FrozenList`, its object field and a planned same-module derived-type probe | rejected initially because of direct CPython bool construction, C++ atomic storage and iterator-only methods |
| Deliberately blocked CPython/NumPy API | [bezier `cf18953a491e8568e4a4344327ed441d3e8956da`](https://github.com/dhermes/bezier/commit/cf18953a491e8568e4a4344327ed441d3e8956da) | Apache-2.0 | ndarray/dtype/memoryview declarations in `_speedup.pyx` | rejected by exact `numpy-c-api` diagnostics at `37:1` and `38:1`; no CPython or Hybrid fallback |

These rows are selection and initial-rejection contracts, not successful port
claims. A project becomes compatible only after the exact pinned checkout and
recorded source changes pass generation, native build, source and binary ABI
audits, tests, normal execution, HPy Trace, HPy Debug leak detection and the
applicable performance comparison.

The initial scanner contract is also actionable rather than project-specific:
module-level native entry points map to `compiled-entry-point`, relative
Cython module C-API imports map to `cython-module-cimport`, `libcpp` runtime
state maps to `cpp-runtime-boundary`, and the pointer, CPython and NumPy
boundaries retain their dedicated action IDs. The pinned cypack and frozenlist
rescans require these precise rules, so a broad unsupported-node diagnostic
cannot silently replace their recorded migration path.

## First local port result

The maintained cypack port fixture in `tests/ahpy/pilot_ports/cypack` applies
the three recorded transformations to the pinned 0.1.7 sources and preserves
the upstream license plus Git blob IDs. On CPython 3.11.15, HPy 0.9.0 and
Apple Clang, the following declared setuptools production path is locally
green:

```console
.venv-hpy09/bin/python Tools/ahpy/cypack_pilot_integration.py \
  --python .venv-hpy09/bin/python \
  --output /tmp/ahpy-cypack-pilot.json
```

The run generates and links three `.hpy0.so` modules, audits all three
generated sources and binaries, and executes the selected upstream semantics
in normal, HPy Trace and HPy Debug `LeakDetector` modes. It also builds exactly
one wheel, checks its three `.hpy0` binaries, three loader stubs, packaged data
and compatibility metadata, installs it with `pip --no-deps --target`, and
repeats normal/Trace/Debug execution from the installed tree. The recorded
wheel is CPython/host tagged and is not presented as a portable Universal
wheel.

The performance lane checks equivalent `axpy` and iterative Fibonacci
semantics, records seven-sample median call costs against same-process Python
implementations, and binds the result to Python, HPy, platform and machine
provenance. It is a comparable measurement, not an enforced release budget;
the local sample currently records compiled-to-Python ratios without turning
them into support promises. The integration is in `ahpy-universal.yml` and its
JSON is retained with packaging evidence. This remains local proof until a
green hosted artifact exists, so the compatibility dashboard keeps the project
at `not-run`.

The deliberately blocked bezier source was checked at the pinned commit: its
`_speedup.pyx` SHA-256 is
`f99e5053f1c942bbc443fa3399c1c67243c46cf078c664a00cc9433ae2993a05`, and
the two NumPy cimports produce `numpy-c-api` findings at exact upstream
positions `37:1` and `38:1`. These locations are part of the manifest contract;
`run_pilots.py` fails the expectation if either diagnostic disappears or
moves. This is an intentional `blocked` result, not a compiler failure or a
fallback to CPython/Hybrid.

## Second local port result

The maintained murmurhash adapter in
`tests/ahpy/pilot_ports/murmurhash` first verifies a pristine checkout at
`58831632dab79389a5cee7715fb688ef2297ff78`, then links the exact upstream
`MurmurHash3.cpp` and `murmurhash/include/murmurhash/MurmurHash3.h`. The
physical include paths in the manifest were verified against the pinned Git
tree rather than inferred from the include spelling used by the C++ source.

```console
.venv-hpy09/bin/python Tools/ahpy/murmurhash_pilot_integration.py \
  --python .venv-hpy09/bin/python \
  --checkout /tmp/ahpy-murmurhash-pilot \
  --output /tmp/ahpy-murmurhash-pilot.json
```

The adapter serializes a Python-converted unsigned 64-bit value into a stable
eight-byte little-endian message inside a C++ shim. Every pointer, byte-buffer
lifetime and `MurmurHash3_x86_32` call stays outside the generated Universal C
translation unit. Held and `with nogil` calls are compared against an
independent Python MurmurHash3 oracle in normal, Trace and Debug modes, while
underflow/overflow probes prove conversion fails before the native call. The
generated source and `.hpy0` binary audits pass locally.

This result is deliberately `partial-scalar-adapter`: it does not implement or
claim compatibility with upstream `hash(str | bytes)`, because public HPy 0.9
does not supply the selected buffer-acquisition contract. The hosted workflow
checks out the complete pinned matrix once and retains its checkout/scan JSON
beside the separate execution JSON; it remains unverified until that workflow
runs green.

## Third local port result

The frozenlist fixture in `tests/ahpy/pilot_ports/frozenlist` is derived from
the pristine pinned `_frozenlist.pyx` whose SHA-256 is
`26f27a30206848ce5c532dffa53224df73c5334cbe159def849f36f355703961`.
It replaces C++ atomic storage with a supported native boolean, replaces the
CPython boolean constructor with ordinary `bool()`, stores the list through an
object-valued HPy field, lowers internal `cdef` helpers to ordinary methods,
and adds a same-module derived-type probe.

```console
.venv-hpy09/bin/python Tools/ahpy/frozenlist_pilot_integration.py \
  --python .venv-hpy09/bin/python \
  --checkout /tmp/ahpy-frozenlist-pilot \
  --output /tmp/ahpy-frozenlist-pilot.json
```

The local result passes generated-source and binary audits, mutation/freeze
and hash semantics, constructor failure cleanup, inherited field/method use,
and an actual `FrozenList -> list -> FrozenList` GC cycle with a weakly observed
payload in normal, Trace and Debug `LeakDetector` modes. It is explicitly a
`supported-subset`: C++ atomic/free-threading semantics, iterator protocol,
rich comparison, copy/deepcopy and MutableSequence registration remain out of
scope.

This pilot exposed a backend correctness bug in `__hash__`: fitting large
integers were being hashed a second time. The emitter now converts values that
fit `HPy_hash_t` directly, maps `-1` to `-2`, and invokes `HPy_Hash` only after
an overflow, matching CPython slot behavior. The full generated runtime oracle
now covers the fitting, overflow, `-1`, and non-integer cases. Hosted matrix
checkout and execution artifacts are wired but remain unverified until CI can
run.

## Reproduce the selection and initial scan

Validate the manifest without network access:

```console
python3 Tools/ahpy/pilot_matrix.py
python3 Tools/ahpy/pilot_matrix.py --json
```

Create or reuse pristine detached checkouts and scan the selected Cython
sources with the stable HPy environment:

```console
.venv-hpy09/bin/python Tools/ahpy/run_pilots.py \
  --manifest tests/ahpy/pilots.toml \
  --checkout-root /tmp/ahpy-pilots \
  --checkout --scan \
  --output /tmp/ahpy-pilot-initial-scan.json
```

Use repeatable `--pilot <exact-id>` filters when only one pinned checkout is
needed; unknown IDs fail before any checkout and duplicate selections collapse
to one manifest-ordered run.

An existing checkout is accepted only when `origin`, `HEAD`, cleanliness,
license and every selected path match the manifest. The runner fetches the
full SHA directly, checks out detached `FETCH_HEAD`, deletes partial checkout
state after infrastructure failure, and fails when an expected diagnostic is
missing. It does not apply port patches or silently compile through another
ABI.

Render a dashboard from one or more retained JSON artifacts. Checkout/scan
matrix evidence and per-pilot integration evidence are merged independently
for every gate; the newest timezone-qualified value wins per gate, an
equal-timestamp conflict fails closed, and missing phases remain `not-run`:

```console
python3 Tools/ahpy/build_pilot_dashboard.py \
  --evidence /tmp/ahpy-pilot-initial-scan.json \
  --evidence /tmp/ahpy-cypack-pilot.json \
  --evidence /tmp/ahpy-murmurhash-pilot.json \
  --evidence /tmp/ahpy-frozenlist-pilot.json \
  --output docs/ahpy/compatibility-dashboard.md
```

The complete pinned checkout/scan plus all three integration reports pass this
merge locally: cypack reaches `pass`, murmurhash remains the declared
`partial-scalar-adapter`, frozenlist remains the declared `supported-subset`,
and bezier remains intentionally `blocked`. The committed dashboard stays
manifest-only until an immutable hosted artifact proves those same results.

## Evidence still required

For each port, retain the following under one aHPy commit and one upstream
commit:

1. applied patch checksum and complete source diff;
2. compiler command, generated C and strict `hpy.h`/no-`Python.h` audit;
3. native compiler/linker command and undefined-symbol audit;
4. upstream tests plus a minimal semantic oracle;
5. normal, Trace and Debug Mode results, including leak/fault details;
6. build/runtime/size measurements only for comparable supported behavior;
7. OS, architecture, compiler, Python, HPy and aHPy provenance;
8. immutable CI run, job and artifact identifiers.

Until those records exist, the dashboard must show `not-run` or `blocked`,
never infer `pass` from manifest validation or a compatibility scan.
