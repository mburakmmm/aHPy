# aHPy preview support contract

This document freezes the first public aHPy product envelope. The
machine-readable source is
[`tests/ahpy/release-contract.toml`](../../tests/ahpy/release-contract.toml).
The product level is **preview**, not beta, release candidate, or stable.
The `aHPy-compiler` distribution is not published yet.

Validate the complete machine contract and its repository bindings with:

```console
python3 Tools/ahpy/release_contract.py
python3 Tools/ahpy/release_contract.py --json
```

The validator requires exact distribution/Cython/HPy/Python pins, positive
hosted run identities, the six declared platform lanes, seven frontend scopes,
matching Universal workflow entries, and the identity/evidence values in this
document. Unknown or missing fields fail closed. The Universal workflow invokes
the same CLI explicitly; a green parser alone does not publish the preview.

## Exact compiler and dependency baseline

- Distribution: `aHPy-compiler==3.3.0.1.dev0`.
- Embedded Cython version: `3.3.0a2.dev0`.
- Exact Cython base:
  `b99cb0e3b5425e11414cadd24168a6cc850e8000`.
- Supported HPy release: exactly `0.9.0`.
- Required HPy 0.9 build companion: exactly `setuptools==80.9.0`.
- Every built sdist and frontend wheel carries Core Metadata `Project-URL`
  records for its exact aHPy source commit, this exact Cython base, and the
  HPy 0.9 compatibility contract; the sdist also carries a validated
  full-commit `.gitrev`.
- Supported interpreter: CPython 3.11 only; local evidence records 3.11.15
  and hosted jobs resolve the current 3.11 patch for their runner.
- Pinned HPy development commit
  `b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381`, Python 3.14,
  PyPy, GraalPy, and moving nightly dependencies are early-warning inputs,
  not supported environments.

An aHPy version does not imply compatibility with another Cython commit,
another HPy release, another Python minor, or arbitrary Cython source.

## Status meanings for users

- **supported** means the named feature or environment is inside this exact
  preview envelope and its required semantic, ownership/failure, Debug/Trace
  where applicable, generated-source/binary, and hosted platform gates pass.
  A defect inside the documented subset is an aHPy bug.
- **partial** means only the explicitly written subset is usable. Anything
  outside that subset must fail with a source-located diagnostic or remains
  outside the packaging/platform promise; partial never means silent fallback.
- **blocked** means the required public HPy/interpreter API or an external
  dependency does not currently permit a correct Universal implementation.
  aHPy does not emulate the feature with CPython or private HPy APIs.
- **rejected** means the feature is intentionally outside Universal mode.
  Users must redesign that boundary, use a separately selected non-Universal
  build, or wait for a future explicitly scoped backend.
- **planned** and **in progress** are development states and are not user
  support promises.

The feature-by-feature status is normative in
[`support-matrix.md`](support-matrix.md); the principal hard gaps are collected
in [`known-limitations.md`](known-limitations.md).

## Supported platform/compiler lanes

All supported lanes use CPython 3.11 and HPy 0.9.0:

| Runner contract | Architecture | Compiler | Status |
|---|---|---|---|
| Ubuntu 24.04 | x86-64 | GCC | supported |
| Ubuntu 24.04 | x86-64 | Clang | supported |
| Ubuntu 24.04 ARM | ARM64 | GCC | supported |
| macOS 15 Intel | x86-64 | Clang | supported |
| macOS 15 | ARM64 | Clang | supported |
| Windows Server 2025 | x86-64 | MSVC | supported |

These are exact validated preview lanes, not promises for every Linux
distribution, macOS/Windows release, architecture, or compiler version.
Release provenance records the concrete compiler and Python patch selected by
each runner.

## Build frontend contract

| Frontend | Status | Preview scope |
|---|---|---|
| aHPy compiler CLI | supported | Generate C for the documented Universal subset |
| Direct non-setuptools build | partial | Build/audit/load through HPy's public loader on all six lanes; packaging/import stubs remain separate |
| setuptools/cythonize | partial | Maintained linked example; not yet a six-platform packaging promise |
| Isolated PEP 517 | partial | Closed-wheelhouse Linux-hosted and macOS-local evidence; unpublished |
| CMake | partial | Linux x86-64 hosted and macOS ARM64 local; Windows/cross-build pending |
| Meson | partial | Linux x86-64 hosted and macOS ARM64 local; Windows/cross-build pending |
| scikit-build-core | partial | Linux x86-64 hosted and macOS ARM64 local; portable tags pending |

Host-specific CPython wheel tags are not Universal-wheel portability evidence.
No package index publication or same-wheel cross-interpreter installation is
part of this preview contract.

The portable `.hpy0` used by the same-binary validation matrix is retained as
release evidence, not published as an installable Universal wheel. aHPy will
not invent a private wheel tag or call a CPython-tagged wheel Universal while
the HPy/PyPA distribution contract remains unsettled.

## Evidence and change control

Implementation commit
`8ed77677ee6bd69fdc93a81bdfe3e704ea7d924b` has all five required contexts
green: aHPy run `30361153504`, benchmark run `30361153497`, full Cython run
`30361153866`, coverage run `30361153526`, and sanitizer run `30361153809`.
Detailed jobs and allowed failures are in
[`validation-matrix.md`](validation-matrix.md).

This contract may expand only through a manifest change that updates the
support and validation matrices, tests the new claim, and passes the required
branch checks on the same commit. A green nightly alone cannot expand support.
