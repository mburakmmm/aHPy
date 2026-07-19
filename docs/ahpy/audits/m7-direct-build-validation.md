# M7 direct Universal build validation

Date: 2026-07-16
Status: version-1 contract implemented; all hosted stable targets green

`Tools/ahpy/direct_build.py` probes the selected interpreter for HPy paths,
suffix, runtime inputs, and compiler configuration. Its public Python seam is
`probe_toolchain` → `create_build_plan` → `execute_build_plan`; the CLI exposes
the same schema-versioned plan and execution contract.

Unit tests prove POSIX static-runtime ordering/defines/suffix, MSVC
`HPyInit_*` export and `.hpy0.pyd` naming, invalid-module rejection, and strict
static-library cardinality. They also launch the CLI from an unrelated
temporary working directory with `PYTHONPATH` removed, proving that repository
module discovery depends on the script location rather than caller state. The
real integration generates
`bootstrap_answer.c`, compiles and links it without setuptools, applies source
and undefined-symbol audits, and loads the exact artifact through public
`hpy.universal.load` in normal and Debug LeakDetector modes. Local macOS ARM64
uses HPy 0.9's `libhpy-extra-universal.a` and produces
`bootstrap_answer.hpy0.so` successfully.

The stable CI matrix now invokes the same integration with Linux GCC/Clang,
Linux ARM64 GCC, macOS Intel/ARM64 Clang, and Windows x64 MSVC. All six jobs
are green in push run
[29685285138](https://github.com/mburakmmm/aHPy/actions/runs/29685285138).
This audit does not claim PEP 517, sdist, wheel/import-stub, or package-install
support.

Hosted run `29490936993` supplied the clean-checkout evidence for this guard:
the prior implementation raised `ModuleNotFoundError: ahpy_build_config` before
the direct build began. The repaired CLI and the complete normal/Debug
integration are green locally and in every hosted stable job.

After adding the direct tool to the automatically discovered quality coverage
area, the local gates pass 345 focused compiler tests and 73 quality-tool tests
(one expected macOS Valgrind availability skip). The combined 418-test trace
reports 73.69% backend, 28.75% frontend seam, and 39.61% quality tools, above
the unchanged 71%/25%/35% floors.
