# aHPy source compatibility scanner

`Tools/ahpy/scan_compatibility.py` compiles each requested `.py` or `.pyx`
source with the strict `hpy-universal` backend. It never retries with CPython or
Hybrid output. Successful files must also retain the generated `hpy.h`/no
`Python.h` boundary.

```console
python3 Tools/ahpy/scan_compatibility.py src/one.pyx src/two.pyx \
    --python .venv-hpy09/bin/python
python3 Tools/ahpy/scan_compatibility.py src/one.pyx --json \
    --python .venv-hpy09/bin/python
```

The default exit status is `0` only when every source is compatible, `1` when
at least one source receives an expected Universal compatibility rejection, and
`2` for an unclassified compiler error. `--allow-rejected` changes expected
rejections to exit `0`, but compiler errors still fail.

## JSON contract

The versioned report has this stable top-level shape:

```json
{
  "schema_version": 1,
  "backend": "hpy-universal",
  "sources": [],
  "summary": {
    "total": 0,
    "compatible": 0,
    "rejected": 0,
    "compiler-error": 0
  }
}
```

Each source status is `compatible`, `rejected`, or `compiler-error`. A
diagnostic records the source path, one-based line and column when available,
the compiler message, and a migration action with stable `id` and explanatory
`text` fields.

Current action IDs are:

- `cython-module-cimport`: replace a cross-module Cython C-API dependency with
  an ordinary Python-callable boundary, while routing genuinely independent C
  declarations through the separately reviewed external-C contract;
- `compiled-entry-point`: expose a module-level `cdef`/`cpdef` entry point as
  `def`, or keep a proven native-only helper outside the Universal translation
  unit;
- `cpp-runtime-boundary`: replace a `libcpp` runtime type with a semantically
  equivalent supported native scalar, or isolate C++ state behind a
  Python-independent C-compatible shim;
- `direct-cpython-cimport`: remove `cpython.*` declarations from the Universal
  boundary. The exact `from cpython.buffer cimport Py_buffer` declaration is a
  permitted frontend-only marker for the canonical validated buffer producer;
  its use remains compiler-validated and generated Universal output contains
  public `HPy_buffer`, not CPython buffer APIs;
- `numpy-c-api`: keep NumPy values behind an ordinary Python object boundary
  or replace the C-API dependency with a Python-independent scalar shim;
- `native-pointer-boundary`: keep native pointer/buffer ownership outside the
  Universal translation unit until a reviewed scalar shim or public HPy buffer
  contract is available;
- `python-header`: port `Python.h` dependencies to public HPy or an independent
  C shim;
- `direct-pyobject-pointer`: replace `PyObject *`/`cpy_PyObject *` storage with
  a correctly owned HPy handle or isolate it outside Universal code;
- `legacy-hpy-conversion`: remove `HPy_FromPyObject`/`HPy_AsPyObject` escape
  hatches and keep the value in the public HPy handle model;
- `set-construction`: use a verified representation until public HPy set APIs
  are selected;
- `generic-iteration`: isolate the loop or use the verified fixed literal
  subset until public iterator APIs exist;
- `exception-handlers`: keep handler state outside this backend slice;
- `control-flow-lifetime`: restructure continuing branch/loop ownership;
- `unsupported-source-node`: consult the support matrix for the gated feature;
- `unsupported-universal-construct`: preserve the diagnostic and do not fall
  back to CPython/Hybrid;
- `compiler-error` and `report-backend-boundary-bug`: preserve artifacts and
  report an aHPy compiler defect.

The scanner also performs source-level detection for `libcpp` runtime types,
relative cross-module Cython cimports, direct `cpython.*` and NumPy C-API cimports plus
`cdef extern from "Python.h"`, even if frontend analysis would fail before
backend emission. Native `void *` boundaries also receive a stable
source-located migration action. Ordinary Python-level
`import numpy` remains valid and is not confused with `cimport numpy`. The
scanner also rejects direct `PyObject *`/`cpy_PyObject *` declarations and
calls to the two legacy HPy/PyObject conversion APIs. Lexical comments and
string literals are masked without changing source offsets, so examples in
documentation do not become false findings. These findings are compatibility
rejections, never permission to change ABI mode.
