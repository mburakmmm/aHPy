# ADR 0014: Clean release-artifact and onboarding contract

- Status: accepted; local sdist/install/reinstall gate implemented
- Date: 2026-07-16

## Context

A wheel built directly from a developer checkout does not prove that the
published source archive contains the compiler, build backends, HPy runtime
contract, or license. Imports executed from the checkout can also survive an
uninstall and create a false success. HPy 0.9's current Python loader imports
`pkg_resources`, which was removed in setuptools 82. aHPy therefore has to
carry and package a narrow, fail-closed loader-template compatibility hook.

## Decision

1. The release gate builds an aHPy sdist from a clean source copy and verifies
   safe member paths, regular-file provenance, required compiler/build modules,
   exact `aHPy-compiler` metadata, and absence of native/cache/VCS artifacts.
2. The frontend wheel is built from that sdist with index access disabled. HPy
   0.9.0 and setuptools 83.0.0 are exact wheelhouse inputs. Before HPy emits a
   Universal loader, the packaged compatibility hook replaces only HPy 0.9's
   recognized `pkg_resources` lookup with an adjacent `pathlib` lookup;
   unrecognized partial templates are rejected.
3. Installation happens in a newly created virtual environment. Presence and
   absence probes run from a clean temporary directory rather than the
   repository root.
4. The compiler frontend and maintained PEP 517 example must each survive a
   complete install, uninstall, absence check, reinstall cycle. The extension
   executes in normal and Debug modes before removal and normally after
   reinstall.
5. The JSON evidence hashes the sdist, frontend wheel, example wheel, and exact
   build-dependency wheels and records exact source/toolchain provenance.
6. An optional non-empty-destination-refusing bundle retains those artifacts,
   `SHA256SUMS`, SPDX 2.3 JSON SBOM, machine-readable license inventory, and
   provenance; every copied artifact is rehashed before acceptance.
7. This gate proves local artifacts only. Publication, standardized Universal
   wheel tags, cross-interpreter package installation, and reproducible archive
   bytes remain independent gates.

## Consequences

Removing a required file from `MANIFEST.in`, relaxing a build dependency,
omitting the loader compatibility module, or leaving an importable compiler
behind after uninstall fails CI. Updating HPy or setuptools requires an
explicit pin change and a complete rerun. A host-tagged green wheel still
cannot be advertised as a portable Universal distribution.
