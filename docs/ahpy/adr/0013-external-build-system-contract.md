# ADR 0013: External build-system contract

- Status: accepted; CMake, Meson, and scikit-build-core paths implemented
- Date: 2026-07-16

## Context

HPy's Universal build inputs are selected-interpreter data: public/forbid
include order, ABI definitions, `.hpy0` suffix, helper static library or source
fallback, and the Windows initializer export. Copying these rules independently
into setuptools, direct argv plans, CMake, Meson, and packaging backends would
let the paths drift and could silently produce a non-Universal artifact.

## Decision

1. Installed `ahpy_build_config` is the public, schema-versioned source of
   external build-system configuration. It probes the explicitly selected
   Python/HPy installation and returns only a validated Universal contract.
2. The contract fixes `HPY`/`HPY_ABI_UNIVERSAL`, puts the HPy forbid-Python
   include first, chooses exactly one helper static library when available or
   the public runtime sources otherwise, preserves the `.hpy0` suffix, and
   names the exact `HPyInit_<module>` export.
3. CMake and Meson receive generated native-language contract files. Examples
   reject a non-Universal ABI or mismatched module name before compiling.
4. CMake uses a `MODULE` target; Meson uses `shared_module`. Neither path
   invokes setuptools or guesses Python library linkage.
5. Windows exports use CMake linker options or Meson's module-definition file.
   Actual Windows support remains pending a green hosted MSVC run.
6. The scikit-build-core example invokes the installed aHPy frontend inside a
   real PEP 517 isolated environment, generates the contract there, builds the
   CMake target, and installs a small loader that calls public
   `hpy.universal.load`.
7. Every executable path receives generated-source, undefined-import,
   normal-runtime, and Debug LeakDetector gates. Current host-tagged wheels are
   still governed by ADR 0004 and are not portable wheel claims.

## Consequences

New build systems should consume `ahpy_build_config` instead of reimplementing
HPy discovery. A contract must never be reused across Python/HPy installations.
Cross-compilation needs a future explicit host/build toolchain schema; the
current native contract fails closed rather than pretending a probed build
interpreter describes another target.

References:

- <https://mesonbuild.com/Reference-manual_functions_shared_module.html>
- <https://cmake.org/cmake/help/latest/command/add_library.html>
