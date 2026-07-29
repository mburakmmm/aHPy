# M7 external build-system validation

Date: 2026-07-16
Status: CMake, Meson, and isolated scikit-build-core locally and hosted green

The complete local macOS ARM64/CPython 3.11/HPy 0.9 path was rerun on
2026-07-29: direct build, setuptools/cythonize, CMake, Meson, and the
closed-wheelhouse scikit-build-core build all passed.

The installed `ahpy_build_config` module and CLI wrapper emit schema-version 1
contracts for the selected Python/HPy toolchain. Focused tests cover POSIX and
Windows suffix/export state, static and source runtime selection, forbid-header
ordering, both renderers, invalid module names, and maintained example
boundaries.

On macOS ARM64 with CPython 3.11 and HPy 0.9, CMake 4.3.3 built
`ahpy_cmake_example.hpy0.so`; Meson 1.11.2 with Ninja 1.13.0 built
`ahpy_meson_example.hpy0.so`. Both artifacts pass public-HPy generated-source
checks, undefined CPython-symbol audits, function/type semantics, and normal
plus Debug LeakDetector execution.

The scikit-build-core 1.0.3 gate built a fresh `aHPy-compiler` frontend wheel,
then materialized a hashed wheelhouse containing exact HPy 0.9, CMake 4.3.4,
Ninja 1.13.0, exact setuptools 80.9.0, and the scikit-build transitive
dependencies. Dependency materialization honors declared PEP 517 build
requirements; this prevents HPy 0.9's sdist from being misidentified as
`0.0.0` when no compatible cached wheel exists. With `PIP_NO_INDEX=1`, a real
isolated build produced
`ahpy_scikit_build_example-0.0.0-cp311-cp311-macosx_26_0_arm64.whl` containing
one audited `.hpy0` and public-loader stub. Pip installation and ordinary
module import pass in normal and Debug modes.

Current quality and coverage counts are recorded in
[`m8-focused-backend-coverage.md`](m8-focused-backend-coverage.md); packaging
modules remain part of the quality-tools denominator.

All three Linux CI integrations are green in hosted
[compiler-and-quality job 88188395921](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395921).
Windows/MSVC execution of these external build systems, cross-compilation, and
standardized Universal wheel metadata remain open.
Clean sdist and uninstall/reinstall evidence is recorded separately in
`m7-release-artifact-validation.md`. The CPython-specific wheel tag is
packaging smoke evidence only.
