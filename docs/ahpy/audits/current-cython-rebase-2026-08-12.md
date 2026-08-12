# Current Cython rebase audit — 2026-08-12

- Previous base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
- Accepted base: `86b94cef002aa23aea0b390335ea3d9e9b62c19e`
- Embedded Cython version: `3.3.0b1`
- Upstream range: 120 commits; the previous base is an ancestor of the accepted base.
- Integration strategy: non-fast-forward topic merge into `codex/ahpy-bootstrap`.

## Conflict decisions

All six textual conflicts are represented in `tests/ahpy/rebase-log.toml`.
The two workflow conflicts retain required aHPy aggregate contexts and internal
path filtering while accepting current action pins and the corrected benchmark
label trigger. `CmdLine.py` retains the runtime option inside upstream's
non-shared parser boundary. `ExprNodes.py` and `Nodes.py` accept upstream's
generation refactors while keeping Python-runtime operations behind
`RuntimeAPI`; the post-merge bypass scanners found and drove repairs for the
new starred-exception list, tuple and exception-state calls. The shared-utility
test remains serialized because that is part of the validated Windows and
capacity reliability contract.

## Post-merge regression repairs

The first full local C/C++ run exposed two defects in the accepted upstream
snapshot. `encode_pyunicode_string()` compared the one-character iteration
value with an integer instead of comparing its `ord()` result, causing astral
Unicode constants to fail during code generation. C++ template deduction also
preserved a C function type for a non-reference value parameter instead of
applying standard function-to-pointer decay; Apple Clang 21/libc++ then
rejected the explicit function-type specializations used by permutation,
merge and set algorithms. Both defects are repaired in the compiler frontend,
with the existing Unicode C/C++ oracles and a new independent templated C
function argument test. The matching algorithm corpus passes in ordinary and
`cpp_locals` modes after the repair.

The raw developer profile also selected `cpp_stl_cmath_cpp17` and
`cpp_condition_variables_cpp20`, which Apple libc++ does not provide for this
test configuration. Both are pre-existing entries in upstream's
`tests/macos_cpp_bugs.txt`; the authoritative rerun therefore uses the same
`CI=1` macOS exclusion contract as upstream CI rather than treating unavailable
standard-library facilities as aHPy regressions.

## Validation record

- Conflict-marker scan: clean.
- Patch whitespace validation: clean.
- Focused compiler/runtime/HPy writer suite on CPython 3.11: 441/441 passed.
- CI policy tests: 8/8 passed.
- Quality-gate tests: 34/34 passed.
- Complete quality-tool suite: 530/530 passed with two expected platform/tool
  availability skips.
- CPython 3.11 focused coverage: backend 9609/9609, frontend seam
  18403/34755 (52.95%), quality tools 9430/9430.
- CPython 3.14.2 focused coverage: backend 9495/9495, frontend seam
  18504/34860 (53.08%), quality tools 9439/9439.
- Generated Universal HPy normal, Trace and Debug execution: passed under the
  required `CFLAGS=-O0` semantic profile.
- Direct Universal HPy build/import: passed under the required semantic
  profile.
- Upstream `except *` and serialized shared-utility end-to-end selection:
  61/61 passed.
- Astral-Unicode regression selection: 35/35 C/C++ tests passed.
- C++ template-decay and previously failing libc++ algorithm selection: 57/57
  tests passed, including ordinary and `cpp_locals` variants.
- Authoritative upstream macOS C/C++ profile (`CI=1`, four workers): 22,025
  tests selected across the four partitions; 21,847 passed and 178 were
  skipped under the upstream platform/dependency contract. The partitions
  reported 6,482/4 skipped, 6,585/25 skipped, 4,511/25 skipped and 4,447/124
  skipped, and the aggregate command exited successfully after 1,724 seconds.
- Documentation contract: all 28 required aHPy documents and 72 local links
  passed. A diagnostic full-tree Sphinx `-W` run remains non-authoritative and
  fails on the repository's existing missing `entry` directive, offline
  intersphinx inventories and upstream keyword-reference warnings; it reported
  no rebase-audit or release-contract link failure.
- Hosted required contexts and exact post-merge release provenance are recorded
  after the merge commit is pushed, because both must bind to that immutable
  source commit rather than its pre-merge parent.

## Immutable merge and artifact evidence

- Merge commit: `a1dc62c0084cc426090b38137eefb3c9ef82dcab`.
- Parents: aHPy `6b5f0878ecfa809156f377cc8ddd2362194adc9c` and Cython
  `86b94cef002aa23aea0b390335ea3d9e9b62c19e`.
- Clean sdist: `ahpy_compiler-3.3.0.1.dev0.tar.gz`, 739 members, SHA-256
  `0c88f324e492ed805e524d8388dd4b86ac4a5baf7643279a2d98a06aecaefa2c`.
- Frontend wheel SHA-256:
  `23565b1146aeac20d69fc13c9072ce2f3bad4f8f3129acc5a63cbdec741ea444`.
- Built example wheel SHA-256:
  `0067fbd04c03bf74bd7a0718fb4a5c25b59d4e7e69b486b4828a8b2afc0d4534`.
- The offline install, compiler uninstall/reinstall and example
  uninstall/reinstall checks all passed with CPython 3.11.15, HPy 0.9.0,
  setuptools 83.0.0 and build 1.5.0.
- GitHub runs created for the immutable merge commit are Universal
  `31590065924`, Benchmarks `31590065944`, Coverage `31590065930`, Sanitizers
  `31590066370`, CI `31590066388`, and Security `31590065928`. They are
  pending/queued under the repository's current Actions quota and must not be
  described as green until their required aggregate jobs complete.

Historical milestone audit documents retain the base on which their evidence
was originally collected. Current product metadata, the support contract and
the append-only rebase log identify only the accepted base above.
