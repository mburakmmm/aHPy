# ADR 0012: PEP 517 frontend identity and Universal enforcement

- Status: accepted; maintained isolated path implemented
- Date: 2026-07-16

## Context

An extension project's isolated build must install the aHPy compiler, not an
upstream Cython release that lacks this repository's Universal backend. The
brand name is also not a safe distribution identifier: PyPI normalizes names
case-insensitively, and `ahpy` is already the unrelated Analytic Hierarchy
Process project. Reusing that identity would enable accidental substitution
and dependency-confusion failures.

HPy 0.9 adds `--hpy-abi` as a setuptools global option only after its
`hpy_ext_modules` setup-keyword hook runs. A project can therefore select the
wrong ABI unless the PEP 517 frontend applies and validates the option at every
hook boundary.

## Decision

1. The product/command brand remains **aHPy**, but its Python distribution
   identity is `aHPy-compiler`. `ahpy` must never appear as a build dependency.
   The distribution name remains publication-pending until the project owner
   reserves it on the intended package indexes.
2. aHPy's release version is independent of the embedded Cython compiler
   version. `ahpy_version.py` is the single source for distribution name,
   aHPy version, Cython base version, and base commit.
3. Isolated projects pin `aHPy-compiler` exactly and select
   `ahpy_build_backend`. The backend verifies the installed distribution's
   exact version and imports the aHPy-only Universal backend marker. An
   installed upstream `Cython` or unrelated `ahpy` package cannot satisfy this
   check.
4. Every PEP 517 wheel, sdist, metadata, and editable hook receives exactly one
   `--hpy-abi=universal`. A CPython or Hybrid request fails instead of
   overriding the policy.
5. The maintained integration first builds a frontend wheel from the checked
   out source and materializes exact HPy 0.9.0 plus setuptools 83.0.0 wheels
   (building HPy from its sdist when the platform has no published wheel).
   The genuine isolated example build runs with `PIP_NO_INDEX=1` against only
   that wheelhouse, preventing same-name index substitution. It audits the
   resulting source and binary and runs the installed module in normal and HPy
   Debug modes.
6. HPy 0.9's host-specific wheel tag remains governed by ADR 0004. PEP 517
   isolation proves frontend provenance and build behavior; it does not make
   that wheel a portable Universal distribution.

## Consequences

The repository now has an executable clean-build path without relying on the
checkout's import path. Publication, clean aHPy sdist reproduction,
uninstall/reinstall, standardized Universal wheel metadata, and name
reservation remain separate release gates. If the chosen distribution name
cannot be reserved, change the single identity constant, example pin, ADR, and
integration expectation together before publishing anything.
