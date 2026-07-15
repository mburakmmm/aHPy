# ADR 0002: Universal ABI boundary and fallback policy

- Status: accepted
- Date: 2026-07-14

## Decision

The `hpy-universal` backend guarantees that generated extension code does not
depend on `Python.h`, `PyObject *`, CPython-only symbols, legacy HPy conversions,
or legacy method/type definitions.

If source code or a dependency requires one of those constructs, compilation
fails with a source-located diagnostic that identifies the construct and the
available migration choices. The compiler never changes to CPython, HPy
CPython, or HPy Hybrid ABI automatically.

External C libraries are permitted when the interface visible to the generated
module is independent of the Python C API. A C library whose public boundary
contains Python C-API objects is not Universal-compatible until that boundary
is ported.

## Rationale

A silent fallback could produce a working binary that is falsely labeled or
understood as Universal. That failure is more dangerous than an explicit build
error because it escapes local tests and appears only on another interpreter or
Python version.
