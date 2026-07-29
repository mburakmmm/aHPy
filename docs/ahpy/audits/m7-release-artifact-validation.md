# M7 clean release-artifact validation

Date: 2026-07-16
Status: local and hosted Linux sdist/install/uninstall/reinstall green

`Tools/ahpy/release_artifact_integration.py` built
`ahpy_compiler-3.3.0.1.dev0.tar.gz` from a clean frontend source tree. The
archive includes exact project metadata, the PEP 517 backend, external
build-system contract, compiler/runtime packages, maintained
tools/tests/docs/examples, and license. Its reviewed manifest emits no missing
source warnings. The safety audit records the current member count in JSON and
rejects traversal, links, native binaries, bytecode, caches, and VCS data.
The sdist carries a validated full-commit `.gitrev`; both its `PKG-INFO` and
the derived frontend wheel metadata link the exact aHPy source commit, exact
Cython base commit, and HPy 0.9 compatibility contract. A Git checkout always
resolves its live `HEAD`, so a stale local `.gitrev` cannot mislabel a new
artifact.

With index access disabled, the gate built the frontend wheel from that sdist,
created a new virtual environment, installed the exact frontend plus HPy 0.9.0
and setuptools 80.9.0, and built the maintained PEP 517 example. The example
passed normal and Debug LeakDetector execution. Both the frontend and example
then passed uninstall, clean-directory absence verification, reinstall, and a
final normal execution.

Dependency-wheel materialization deliberately retains PEP 517 build isolation:
HPy 0.9's source distribution otherwise derives the invalid version `0.0.0`
when its declared build requirements are absent. Index access is disabled
after the exact HPy 0.9.0 and setuptools 80.9.0 wheels have been materialized,
so all consumer builds and installs remain closed-wheelhouse operations.

The schema-versioned JSON record hashes the sdist, frontend wheel, example
wheel, HPy 0.9 wheel, and setuptools 80.9.0 wheel. Exact hashes are preserved
in the requested local JSON output and in the CI evidence artifact for hosted
runs, avoiding a self-referential hash inside the sdist itself.

Local macOS ARM64/CPython 3.11 evidence is complemented by the green clean
sdist/onboarding step in hosted
[compiler-and-quality job 88188395921](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395921).
Cross-interpreter package installation, standardized Universal
extension-wheel reproducibility, publication, and standardized Universal wheel
metadata remain open. The example wheel's CPython tag is not a portability
claim.

Current quality and coverage counts are recorded in
[`m8-focused-backend-coverage.md`](m8-focused-backend-coverage.md) and the
top-level validation matrix rather than duplicated here.
