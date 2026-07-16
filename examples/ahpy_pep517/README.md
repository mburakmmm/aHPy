# aHPy isolated PEP 517 example

This project pins the `aHPy-compiler` distribution—not upstream `Cython` and
not the unrelated PyPI `ahpy` project—as its build frontend and selects
`ahpy_build_backend`. The wrapper verifies the installed aHPy version and
forces HPy's Universal ABI option for every setuptools PEP 517 hook. A
missing/substituted frontend or Hybrid/CPython ABI request fails.

The current HPy 0.9 tooling produces a host-tagged wheel containing one
`.hpy0` binary and loader stub. Per ADR 0004, that wheel is a packaging smoke
test and must not be advertised as a cross-interpreter Universal wheel.
