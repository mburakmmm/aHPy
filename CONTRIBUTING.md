# Contributing to aHPy

aHPy is a downstream Cython compiler project. Contributions to its Universal
HPy backend are welcome, but supported behavior must be backed by semantics,
ownership, failure-path, Debug-mode, and ABI-boundary evidence.

Start with:

- [Project contract](docs/ahpy/README.md)
- [Ordered roadmap](TODO.md)
- [Agent handoff](AGENTTODO.md)
- [Support matrix](docs/ahpy/support-matrix.md)
- [Validation matrix](docs/ahpy/validation-matrix.md)
- [Production documentation contract](tests/ahpy/documentation-contract.toml)
- [Onboarding](docs/ahpy/onboarding.md)
- [Maintenance and backport policy](docs/ahpy/maintenance.md)
- [Debugging Universal failures](docs/ahpy/debugging.md)
- [Upstream dependency inventory](docs/ahpy/upstream-dependencies.md)

## Development workflow

1. Create an isolated environment using the exact requirements in
   `tests/ahpy/requirements-hpy09.txt`.
2. Add a supported example and a source-located rejection for unsupported
   forms before widening a compiler path.
3. Implement explicit HPy handle ownership and cleanup on every success and
   failure edge. Never add an implicit CPython or HPy Hybrid fallback.
4. Run the smallest focused tests while iterating, then the applicable commands
   in `AGENTTODO.md` section 9.
5. Update the support/validation matrices, audit record, and an entry under
   `docs/ahpy/changes/` in the same change.

Use focused commits. Do not mix generated files, local environments, build
outputs, or unrelated upstream Cython changes into an aHPy contribution.

Changes to Cython behavior that reproduce without `hpy-universal` should
normally be proposed to [upstream Cython](https://github.com/cython/cython).
Backend-neutral seams may be developed here first when they are independently
testable and suitable for a focused upstream contribution.

## Reporting defects and vulnerabilities

Use the repository's issue forms for bugs, features, and design questions.
Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
All participation is governed by the
[aHPy Code of Conduct](.github/code-of-conduct.md).

The preserved upstream Cython contribution guide remains available at
[docs/CONTRIBUTING.rst](docs/CONTRIBUTING.rst); it is not the aHPy project
handoff or support policy.
