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

The Universal emitter includes the header once and evaluates arguments in
source order. Dynamic arguments convert through public HPy APIs with checked
integer narrowing. A side-effect-free numeric literal takes a zero-handle path
only when its value is representable for the destination on every supported C
data model; the emitter supplies an explicit C type and portable spelling.
Non-finite floating values, signedness-ambiguous plain `char` values, and
out-of-portable-range integers retain the checked HPy path. The scalar result
always becomes an owned HPy handle. Any conversion or allocation failure
preserves the original Python exception and closes every already-created
handle. The generated translation unit still passes the
`Python.h`/legacy-symbol source and binary audits.

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

ADR 0010 enables one narrow `nogil` contract: a non-empty `with nogil` block
may contain discarded calls or simple-local assignments from validated
functions declared `noexcept nogil`. Portable literals become native constants;
other supported scalar
arguments are evaluated in source order, checked through public HPy conversion
APIs, and have their temporary handles closed before execution is left. The
native implementation must not call Python/HPy, access handles or Python-owned
state, invoke Python callbacks, throw across the C boundary, or escape with
`longjmp`. The emitter leaves and re-enters Python execution through public HPy
APIs around that handle-free interval. A supported scalar result may be kept in
a native temporary and assigned to a simple Python local only after re-entry.
Other result targets, native status-code/`errno`, pointer/buffer lifetime, and
callback contracts still need explicit designs. Unsupported forms fail at
their source position; the backend never changes ABI mode as a fallback.

## Executable reference

`examples/ahpy_setuptools` supplies the exact maintained `.pyx`, `.h`, and `.c`
files. `Tools/ahpy/setuptools_integration.py` builds and links them as a
Universal `.hpy0`, audits generated source and undefined binary symbols, runs
normal and HPy Debug semantics with leak detection, verifies narrowing failure,
builds the current host-tagged wheel, installs it into an empty target, and
runs it again. The example also executes ADR 0010 argumentless and
argument-bearing native counter probes in normal and Debug modes, proves a
failing `__index__` conversion never enters the native interval, returns a
retained scalar only after re-entry, and audits the HPy execution-state
spellings.
