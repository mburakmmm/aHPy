# Known limitations of the aHPy preview

These are correctness boundaries, not silent compatibility fallbacks. Every
source-level gap must remain fail-closed with the diagnostic recorded in the
[Universal diagnostic catalog](diagnostics.md). The
[support matrix](support-matrix.md) is authoritative for finer-grained
implemented subsets.
The [advanced-surface closure](audits/prd4-advanced-surface.md) assigns every
larger Cython family an exact preview status and migration path.

## HPy 0.9 public-API gaps

- True iterator-protocol loops, generator objects, `yield`, and `yield from`
  are blocked because HPy 0.9 lacks the required public iterator-next and
  complete exception-state APIs.
- `async def`, `await`, asynchronous iterators, and async generators are
  blocked by missing public async protocol slots and suspension/error state.
- Full exception semantics including `except as`, bare reraise, traceback,
  chaining, `else`, `finally`, and nested handlers are blocked by the missing
  public exception-triple/state surface.
- Set literals and comprehensions are blocked because HPy 0.9 lacks the
  required public set construction/add APIs and `SetType`.
- Python function/code-object introspection is blocked because HPy 0.9 has no
  public code-object constructor and module methods are not Python functions.
- Portable instance `__dict__`, weakrefs, and `__dealloc__`/native-resource
  destruction are blocked by missing layout/offset or context-bearing destroy
  APIs.
- Typed memoryviews and buffer consumers are blocked because HPy 0.9 does not
  expose public buffer acquire/release consumer operations; a pure-type buffer
  producer remains planned behind its own ownership gate.
- Arbitrary `prange`/`parallel()` workers are blocked because HPy 0.9 has no
  public worker attach and error-transport contract.
- Immediate retry after a failed module initialization requires an explicit
  GC boundary in the current oracle; GC-free retry is not supported.

## Compiler and source-surface limits

- General Cython compatibility is not claimed. Only the exact subsets marked
  supported or partial in the support matrix are accepted.
- Multiple/cross-module/builtin inheritance, metaclasses, remaining type
  slots, broad decorators, nested-nested closures, and several callable
  signature families are not complete.
- Fused types are planned but currently fail closed before CPython fused
  dispatch machinery can enter Universal generation.
- Broad C++ output, C++ exceptions, and RAII cleanup are planned and are not
  part of the preview.
- `cpython.*` cimports, `PyObject *`, HPy legacy conversions, Hybrid fallback,
  and CPython-only third-party C APIs are rejected or blocked.
- NumPy's CPython C API is not a supported Universal boundary.

## Runtime and distribution limits

- CPython 3.11 is the only supported interpreter minor. Python 3.14 with the
  pinned HPy development revision, PyPy, GraalPy, and branch-tip nightlies are
  allowed-failure early warnings.
- HPy 0.9.0 is the only supported HPy release and currently requires
  `setuptools==80.9.0` for its generated loader.
- The maintained frontend and example wheels currently carry host-specific
  CPython tags. They are not standardized Universal wheels and are not
  evidence of same-wheel cross-interpreter installation.
- The distribution is unpublished; package-index reservation, execution and
  verification of the prepared tag-only signing workflow, an approved real
  TestPyPI upload, and stable release approval remain later production gates;
  the no-upload publication rehearsal is green.
- Direct build, CMake, Meson, scikit-build-core, setuptools/cythonize, and
  isolated PEP 517 have the partial platform/packaging scopes frozen in the
  [preview contract](release-contract.md).
