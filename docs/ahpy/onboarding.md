# Clean release-artifact onboarding

This is the maintained clean-environment path for the unpublished aHPy
frontend. It proves the local source artifact; it is not a PyPI publication or
Universal-wheel portability claim.

This flow belongs to the frozen
[preview support contract](release-contract.md). It requires CPython 3.11,
HPy 0.9.0, and setuptools 80.9.0; it does not promote PyPy, GraalPy, another
Python minor, or another HPy release.

## Prerequisites

- a clean checkout of this repository;
- CPython 3.11 and a working C compiler;
- network access only while the outer validation environment materializes its
  pinned dependency wheels.

From the repository root, run:

```console
python3.11 -m venv .venv-ahpy-onboarding
.venv-ahpy-onboarding/bin/python -m pip install \
    -r tests/ahpy/requirements-hpy09.txt \
    -r tests/ahpy/requirements-build-systems.txt
.venv-ahpy-onboarding/bin/python Tools/ahpy/release_artifact_integration.py \
    --python .venv-ahpy-onboarding/bin/python \
    --output /tmp/ahpy-release-artifacts.json \
    --bundle-dir /tmp/ahpy-release-bundle
```

On Windows, use `.venv-ahpy-onboarding\Scripts\python.exe` in the same three
commands. A successful run ends with `aHPy clean release-artifact onboarding
passed` and writes a schema-versioned JSON record containing artifact names,
SHA-256 digests, exact build provenance, runtime modes, and uninstall/reinstall
results.

## What the gate proves

The tool creates a clean frontend source copy, builds
`aHPy-compiler==3.3.0.1.dev0` as an sdist, and normalizes its tar/gzip metadata
under ADR 0015. The sdist's `.gitrev` and both package formats' Core Metadata
bind the artifact to the exact aHPy source commit, embedded Cython base, and
HPy 0.9 compatibility contract. It rejects path traversal, archive
links, native binaries, bytecode, caches, VCS data, missing compiler/runtime
sources, and incorrect distribution metadata. It then:

1. materializes exact HPy 0.9.0 and setuptools 80.9.0 wheels with their
   declared isolated build requirements;
2. disables package-index access and builds the frontend wheel from the sdist;
3. creates a second, new virtual environment and installs only from the local
   wheelhouse;
4. builds and installs `examples/ahpy_pep517` through real PEP 517 isolation;
5. runs the example in normal and HPy Debug modes;
6. removes and verifies absence of the frontend, reinstalls it, and repeats the
   same remove/absence/reinstall cycle for the example;
7. executes the example once more after reinstall.

The requested bundle directory is created only when empty and retains the
sdist, frontend wheel, example wheel, exact HPy/setuptools wheels,
`SHA256SUMS`, an SPDX 2.3 JSON SBOM, a machine-readable license inventory, and
`provenance.json`. Every copied artifact is rehashed against the validated
report before the bundle is accepted.

For release tags, the separate keyless Sigstore gate signs this bundle and its
SPDX statement; see [release signing and verification](release-signing.md).
Ordinary onboarding runs intentionally produce no signature.

The clean subprocess checks run from a temporary directory, so an uninstalled
package cannot be accidentally satisfied by the repository checkout.

## Current boundary

The produced example wheel has a CPython/host compatibility tag. ADR 0004
forbids treating that envelope as a cross-interpreter Universal wheel. Package
publication, standardized Universal wheel metadata, same-package
cross-interpreter installation, and byte-for-byte standardized Universal
extension-wheel reproducibility remain separate release gates. The frontend
sdist and pure-Python wheel already pass their two-root byte comparison.
See [known limitations](known-limitations.md) for the complete runtime and
distribution boundary.
