# aHPy setuptools example

This example proves the supported programmatic build seam: Cython's
`cythonize()` selects `runtime_backend="hpy-universal"`, and HPy setuptools
integration receives the resulting extension through `hpy_ext_modules`.
The `hpy-universal` cythonize seam automatically applies aHPy's fail-closed
HPy 0.9 loader compatibility hook, so the generated stub resolves its adjacent
`.hpy0` binary without the removed `pkg_resources` module under the pinned
Setuptools 83 toolchain.
It also links `ahpy_external.c` and exposes its Python-independent scalar C API
from `ahpy_external.h`; this is the maintained external-C example rather than
an inline or CPython C-API wrapper.

From the repository root, after creating the pinned environment documented in
`tests/ahpy/requirements-hpy09.txt`:

```console
cd examples/ahpy_setuptools
PYTHONPATH=../.. ../../.venv-hpy09/bin/python setup.py \
    --hpy-abi=universal build_ext --inplace
PYTHONPATH=. ../../.venv-hpy09/bin/python -c \
    "import ahpy_setuptools_example as m; assert m.answer() == 42; assert m.external_add(20, 22) == 42; assert m.external_nogil_probe() >= 1"
HPY=debug PYTHONPATH=. ../../.venv-hpy09/bin/python -c \
    "import ahpy_setuptools_example as m; assert m.Box(42).identity() == 42"
```

The build must create an `.hpy0` binary and an HPy loader stub. It must not
silently produce a CPython extension. `Tools/ahpy/setuptools_integration.py`
copies and builds these exact files in an isolated temporary directory, audits
the generated source and undefined symbols, and runs normal/Trace/Debug
semantics.

The enabled external-C seam accepts a concrete, injection-safe header and
ordinary C boolean/integer/floating scalar parameters and results. HPy argument
conversion is source ordered and narrowing is checked. `Python.h`, inline
verbatim C, external typedefs, pointers, aggregates, variables, variadics,
optional parameters, and Python-inspecting exception clauses are intentionally
rejected. The sole exception clause is the exact signed-integer `except -1`
errno contract;
`except?`, `except *`, unsigned/non-`-1` sentinels, and C++ exception clauses
remain rejected.
See `docs/ahpy/external-c.md` for the full contract.

The example's `external_nogil_probe()` and argument-bearing
`external_nogil_advance()`, `external_nogil_ordered()`, and
`external_nogil_result()` plus `external_nogil_targets()` are the ADR 0010
transition oracles. Their native
calls are declared `noexcept nogil`; generated code converts and checks each
scalar argument before its call's leave/re-enter interval using public HPy 0.9
APIs. The ordered probe proves a later Python conversion remains after the
preceding native call, while the result probe boxes its retained scalar only
after re-entry. The target probe evaluates attribute/item arguments before
leave and writes retained results to global/attribute/item/slice targets only after
re-entry, including a custom slice target. `external_nogil_with_gil()` places
an explicit Python callback island between two native intervals and proves both
ordered success and that callback failure skips the second native call in
normal/Trace/Debug. This does not enable
compound/destructuring result targets, native
failure protocols, callbacks invoked from native C, `prange`, or general `nogil`.

`external_errno_held()`, `external_errno_released()`,
`external_errno_discarded()`, and `external_missing_errno()` are the native
error oracles. The first three prove exact signed `except -1` success and
`EDOM`→`OSError` behavior while held or after re-entry, including discarded
results and unchanged native state on failure; the last proves a sentinel
without errno becomes the documented `RuntimeError`.

This is the maintained setuptools/cythonize example, not yet the clean isolated
PEP 517 distribution path. The latter remains gated until the aHPy build
frontend itself has an installable package identity; declaring ordinary PyPI
Cython as the isolated build requirement would silently select the wrong
backend implementation.
