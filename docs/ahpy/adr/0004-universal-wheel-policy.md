# ADR 0004: Do not label CPython-tagged wheels as Universal HPy wheels

- Status: accepted
- Date: 2026-07-15

## Context

HPy 0.9's setuptools integration correctly builds an HPy Universal extension
when `--hpy-abi=universal` is selected. The official HPy quickstart documents
the resulting `.hpy0` binary and loader stub, and the HPy project describes the
binary itself as portable across supporting interpreters:

- <https://docs.hpyproject.org/en/0.9.0/quickstart.html>
- <https://hpyproject.org/>

The same HPy project page explicitly lists packaging Universal extensions and
PyPI integration among its open questions. There is no selected standard wheel
compatibility tag in the current aHPy/HPy 0.9 support contract.

The executable aHPy setuptools gate confirms the distinction. On the validated
CPython 3.11/macOS arm64 builder, `bdist_wheel` places the `.hpy0` binary and
loader stub inside a wheel tagged
`cp311-cp311-macosx_26_0_arm64`. That wheel installs and runs on its CPython
host, but the wheel envelope advertises CPython 3.11 compatibility rather than
the cross-interpreter compatibility of the contained HPy binary.

## Decision

1. aHPy may claim portability only for an audited `.hpy0` artifact copied
   unchanged between interpreter lanes.
2. A CPython-tagged wheel containing `.hpy0` is a host packaging smoke test,
   not a Universal HPy distribution artifact.
3. aHPy will not invent a private wheel tag, rename a wheel after build, or
   publish misleading metadata.
4. The correct Universal wheel/tag task remains blocked until an HPy/PyPA
   packaging contract is selected and implemented by the relevant tooling.
5. PEP 517 isolation selects the exact `aHPy-compiler` build frontend under ADR
   0012. It must not resolve ordinary upstream Cython or unrelated `ahpy` and
   silently lose this backend.

## Consequences

The maintained setuptools/cythonize example and CI gate build, audit, install,
and execute the current host-tagged wheel. Cross-interpreter validation
continues to use the separately hashed portability artifact, not that wheel.
Clean aHPy sdist reproduction, standardized Universal wheel metadata,
distribution-name reservation, and PyPI publication remain release blockers.
The maintained PEP 517 wheel isolation gate is locally green under ADR 0012,
but does not alter the wheel portability policy.
