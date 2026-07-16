# M7 external build-system validation

Date: 2026-07-16
Status: CMake, Meson, and isolated scikit-build-core locally green

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
dependencies. With `PIP_NO_INDEX=1`, a real isolated build produced
`ahpy_scikit_build_example-0.0.0-cp311-cp311-macosx_26_0_arm64.whl` containing
one audited `.hpy0` and public-loader stub. Pip installation and ordinary
module import pass in normal and Debug modes.

The complete quality-tool suite passes 111 tests with one expected macOS
Valgrind availability skip. The 455-test focused trace reports 73.69% backend,
28.75% frontend seam, and 35.49% quality tools, above the unchanged
71%/25%/35% floors. Packaging modules are included in the quality-tools
denominator. Python 3.14.6 independently reports 72.85%, 28.62%, and 35.60%,
so both current local interpreter snapshots remain above the same floors.

Linux CI executions are declared but hosted evidence is pending. Windows/MSVC,
cross-compilation, and standardized Universal wheel metadata remain open.
Clean sdist and uninstall/reinstall evidence is recorded separately in
`m7-release-artifact-validation.md`. The CPython-specific wheel tag is
packaging smoke evidence only.
