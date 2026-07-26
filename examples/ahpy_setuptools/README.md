# aHPy setuptools example

This example proves the supported programmatic build seam: Cython's
`cythonize()` selects `runtime_backend="hpy-universal"`, and HPy setuptools
integration receives the resulting extension through `hpy_ext_modules`.
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
the generated source and undefined symbols, and runs normal/Debug semantics.

The enabled external-C seam accepts a concrete, injection-safe header and
ordinary C boolean/integer/floating scalar parameters and results. HPy argument
conversion is source ordered and narrowing is checked. `Python.h`, inline
verbatim C, external typedefs, pointers, aggregates, variables, variadics,
optional parameters, and Python exception clauses are intentionally rejected.
See `docs/ahpy/external-c.md` for the full contract.

The example's `external_nogil_probe()` and argument-bearing
`external_nogil_advance()` and `external_nogil_ordered()` are the ADR 0010
transition oracles. Their discarded native calls are declared `noexcept
nogil`; generated code converts and checks each scalar argument before its
call's leave/re-enter interval using public HPy 0.9 APIs. The ordered probe
also proves a later Python conversion remains after the preceding native call.
This does not enable used native results, callbacks, `prange`, or general
`nogil`.

This is the maintained setuptools/cythonize example, not yet the clean isolated
PEP 517 distribution path. The latter remains gated until the aHPy build
frontend itself has an installable package identity; declaring ordinary PyPI
Cython as the isolated build requirement would silently select the wrong
backend implementation.
