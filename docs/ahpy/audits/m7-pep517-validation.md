# M7 isolated PEP 517 validation

Date: 2026-07-16
Status: maintained isolated frontend/wheel path locally and hosted green

The repository distribution is `aHPy-compiler==3.3.0.1.dev0`; this intentionally
differs from both upstream `Cython` and the unrelated existing PyPI `ahpy`
project. `ahpy_build_backend` rejects a missing or version-mismatched frontend,
checks the aHPy-only Universal backend marker, injects exactly one
`--hpy-abi=universal`, and rejects CPython/Hybrid ABI requests.

`Tools/ahpy/pep517_integration.py` copies a clean frontend source tree, builds
its pure-Python compiler wheel with self-compilation disabled, and verifies its
name, version, backend modules, and Cython package. It then gives that local
wheel to pip as the exact build dependency for `examples/ahpy_pep517`, while
leaving build isolation enabled. Exact HPy 0.9 and setuptools 80.9.0 wheels are
materialized into the same reviewed wheelhouse first, with HPy's declared PEP
517 build requirements available so its source distribution cannot degrade to
the invalid version `0.0.0`; the isolated resolver then uses `PIP_NO_INDEX=1`,
so no same-name index candidate can substitute for the local frontend. It
compiles the separate `.pyx` and produces exactly one `.hpy0` binary and loader
stub. The JSON report records every wheel's SHA-256.

The local macOS ARM64/CPython 3.11 run produced
`ahpy_pep517_example-0.0.0-cp311-cp311-macosx_26_0_arm64.whl`. Generated source
contains the required public HPy module/type operations, the binary has no
forbidden CPython imports, and the pip-installed example passes its function
and extension-field identity semantics in normal and HPy Debug LeakDetector
modes. Per ADR 0004, its CPython-specific envelope remains a packaging smoke
test and is not advertised as a cross-interpreter Universal wheel.

Current quality and coverage counts are recorded in
[`m8-focused-backend-coverage.md`](m8-focused-backend-coverage.md). The
compiler distribution name is not yet reserved or published, and this gate
does not claim standardized Universal wheel tags or cross-interpreter package
installation.

The same isolated PEP 517 integration is green on hosted Linux in
[compiler-and-quality job 88188395921](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395921).
This adds a clean hosted packaging execution, not a standardized Universal
wheel tag or cross-interpreter installation claim.
