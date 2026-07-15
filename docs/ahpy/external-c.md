# Python-independent external C contract

aHPy's first external-library seam deliberately covers only C interfaces that
do not expose the Python or HPy ABI. A supported declaration names a concrete
header and contains direct C functions whose parameters and result are standard
boolean, signed/unsigned integer, or floating scalar types:

```cython
cdef extern from "ahpy_external.h":
    long long ahpy_external_add(long long left, long long right)
    double ahpy_external_scale(double value, double factor)

def add(left, right):
    return ahpy_external_add(left, right)
```

The Universal emitter includes the header once, evaluates Python arguments in
source order, converts each through public HPy APIs, checks integer narrowing,
calls the C function, and converts its scalar result back to an owned HPy
handle. A conversion or allocation failure preserves the original Python
exception and closes every already-created handle. The generated translation
unit still passes the `Python.h`/legacy-symbol source and binary audits.

## Accepted boundary

- A literal safe header path such as `"library.h"` or `"<math.h>"`.
- Direct `bint`, `char`, signed/unsigned byte, short, int, long, long long,
  `float`, `double`, and `long double` parameters/results.
- Zero or more positional scalar parameters; conversions occur left to right.
- A plain C identifier for each linked function.
- Normal C calls while the Python execution lock remains held.

The build system remains responsible for include directories, additional C
sources/libraries, platform compiler flags, and linking. Universal HPy removes
the interpreter ABI dependency; it does not make an arbitrary native library
binary portable across operating systems or CPU architectures.

## Rejected boundary

- `Python.h`, `cpython.*`, `PyObject *`, or any Python C-API contract.
- `cdef extern from *` and verbatim inline C, because the emitted ABI cannot be
  independently audited from a concrete header.
- External typedefs, enums, structs/unions, variables, pointers, arrays,
  callbacks, variadic functions, and optional C arguments.
- `Py_ssize_t`, because it is a Python-header-owned type rather than an
  independent C-library ABI type.
- Cython/Python exception clauses on the native function.
- C++ names, overloads, methods, templates, or exception translation.

Native status-code, `errno`, pointer/buffer lifetime, callback, and `nogil`
contracts need explicit designs before they can be enabled. Until then, a
supported function must return its value without invoking Python APIs and must
not require a Python exception indicator. Unsupported declarations fail at
their source position; the backend never changes ABI mode as a fallback.

## Executable reference

`examples/ahpy_setuptools` supplies the exact maintained `.pyx`, `.h`, and `.c`
files. `Tools/ahpy/setuptools_integration.py` builds and links them as a
Universal `.hpy0`, audits generated source and undefined binary symbols, runs
normal and HPy Debug semantics with leak detection, verifies narrowing failure,
builds the current host-tagged wheel, installs it into an empty target, and
runs it again.
