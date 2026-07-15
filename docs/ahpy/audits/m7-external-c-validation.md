# M7 Python-independent external-C validation

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: constrained scalar interface enabled; pointer/aggregate/error-protocol
surface remains gated

## Accepted invariant

An admitted `cdef extern` block has a concrete injection-safe header, contains
only direct C function declarations, and exposes only independently sized
boolean/integer/floating scalar parameters and results. Each compiler entry is
marked only after the complete declaration contract is checked. Calls without
that mark cannot reach native emission.

The function emitter evaluates each Python argument in source order, retains
its owned HPy handle while converting, checks conversion and narrowing failures,
then performs exactly one native call. The result is converted through
`HPyLong_FromLongLong`, `HPyLong_FromUnsignedLongLong`, `HPyFloat_FromDouble`,
or a duplicated boolean context constant. Any failure closes all live argument
handles and preserves the active exception.

## Negative boundary

Focused compiler tests reject:

- `cdef extern from *`, verbatim injected code, unsafe header text, and
  `Python.h`;
- typedefs, variables, pointer results, Python-owned `Py_ssize_t`, variadic
  signatures, and any non-scalar parameter/result;
- Cython/Python exception contracts and non-identifier function names.

External typedef width, aggregate layout, pointer ownership, callback context,
native status/`errno`, C++, and `nogil` execution are not inferred. A rejection
produces a source-positioned aHPy diagnostic and no C file; there is no ABI
fallback.

## Executable gate

`examples/ahpy_setuptools` links `ahpy_external.c` against the strict generated
translation unit. `Tools/ahpy/setuptools_integration.py` proves:

- signed and unsigned 64-bit, boolean, and floating results;
- two-argument signed integer and floating calls;
- left-to-right `__index__` side effects;
- exact lower-bound `signed char` behavior;
- overflow before native entry, checked with a private C call counter;
- normal and HPy Debug execution with `LeakDetector`;
- generated-source and undefined-binary-symbol Universal audits;
- `.hpy0` build, current host-tagged wheel content, empty-target pip install,
  and post-install execution.

The compatibility scanner also classifies the exact example source as
`compatible`. CI includes it in the strict self-scan and reruns the full
setuptools gate.

## Portability scope

The emitted module is independent of a Python implementation ABI. Its linked C
library is still a native platform artifact and must be compiled for each
operating-system/architecture target. This gate makes no claim that arbitrary
third-party native binaries are cross-platform or that headers which secretly
include Python APIs are safe; generated-source plus undefined-symbol audits
remain mandatory backstops.
