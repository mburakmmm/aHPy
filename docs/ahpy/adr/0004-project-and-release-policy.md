# ADR 0004: Project, version, branch, and release policy

- Status: accepted; preview contract frozen 2026-07-29
- Date: 2026-07-14

## Licensing

aHPy changes use the repository's Apache License 2.0 so that backend-neutral
and HPy changes can be contributed to Cython without relicensing. Existing
Cython, HPy, Oracle, and other third-party copyright and license notices must be
preserved. Imported code is accepted only after its license and provenance are
recorded.

## Versioning

The product/command name is `aHPy`. ADR 0012 amends the original distribution
identity to `aHPy-compiler` because normalized `ahpy` is an unrelated existing
PyPI project. The new distribution identity remains publication-pending until
it is reserved by the project owner. Stable versions contain the corresponding
Cython base version followed by an aHPy release counter:

```text
<cython-major>.<cython-minor>.<cython-patch>.<ahpy-release>
```

For example, `3.2.5.1` means the first aHPy release based on Cython 3.2.5. The
base commit is additionally recorded in package metadata and release notes.
Development builds use a PEP 440 development suffix and must record the full
Cython and aHPy commits.

An aHPy version never implies compatibility with an untested Cython patch even
when source changes rebase cleanly.

## Branches

- `main` is the integration branch and tracks current Cython development.
- `ahpy/<cython-major>.<cython-minor>` is created for a supported release line.
- Work is developed in short-lived topic branches and merged only with its
  tests and documentation.
- Historical experiments live under non-release refs and are never merged as a
  whole.

The current `codex/ahpy-bootstrap` branch is a bootstrap topic branch, not a
release branch.

## Upstream and backports

- Upstream Cython changes are integrated continuously into `main`.
- Backend-neutral refactors are proposed upstream before long-lived downstream
  divergence develops.
- Release branches receive correctness, security, packaging, and compatibility
  fixes. New feature families normally remain on `main`.
- A backport must include the original regression test and must not expand the
  documented support tier implicitly.
- Direct pushes to release branches and history rewrites of published branches
  are prohibited.

## Releases

A release candidate is cut only when all gates for its declared support tiers
are green. Release notes state the exact Cython base, HPy versions, interpreter
matrix, supported feature tiers, known blockers, performance results, and
artifact provenance.

The first frozen product level is **preview**, not beta, release candidate, or
stable. Its exact unpublished distribution, Cython/HPy/Python baseline,
platform/compiler lanes, frontend scopes, status meanings, and evidence are
normative in [`release-contract.md`](../release-contract.md) and
`tests/ahpy/release-contract.toml`. Preview status does not relax Universal
fail-closed behavior; it limits the size of the support promise.
