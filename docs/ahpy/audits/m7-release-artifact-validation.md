# M7 clean release-artifact validation

Date: 2026-07-16; Setuptools 83 local rerun: 2026-08-12
Status: current local sdist/install/uninstall/reinstall green; replacement
hosted evidence pending

`Tools/ahpy/release_artifact_integration.py` requires every declared release
input to be committed in an exact Git checkout both before and after its run,
then builds `ahpy_compiler-3.3.0.1.dev0.tar.gz` from a clean frontend source
tree. The
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

The source-member audit additionally enumerates the exact tracked release
inputs. Every archive file except generated root `PKG-INFO` and canonical
`.gitrev` must be tracked and byte-identical to the selected checkout. A dirty
input, an untracked member, a source revision race, or an unverifiable Git
identity therefore fails before evidence can be accepted.

With index access disabled, the gate built the frontend wheel from that sdist,
created a new virtual environment, installed the exact frontend plus HPy 0.9.0
and setuptools 83.0.0, and built the maintained PEP 517 example. The packaged
`ahpy_hpy_compat` module was present in both sdist and wheel, imported from the
clean environment, and removed with the frontend. The example
passed normal and Debug LeakDetector execution. Both the frontend and example
then passed uninstall, clean-directory absence verification, reinstall, and a
final normal execution.

Dependency-wheel materialization deliberately retains PEP 517 build isolation:
HPy 0.9's source distribution otherwise derives the invalid version `0.0.0`
when its declared build requirements are absent. Index access is disabled
after the exact HPy 0.9.0 and setuptools 83.0.0 wheels have been materialized,
so all consumer builds and installs remain closed-wheelhouse operations.

The schema-versioned JSON record hashes the sdist, frontend wheel, example
wheel, HPy 0.9 wheel, and setuptools 83.0.0 wheel. Exact hashes are preserved
in the requested local JSON output and in the CI evidence artifact for hosted
runs, avoiding a self-referential hash inside the sdist itself.

The release bundle retains those five exact artifacts together with a sorted
GNU-compatible `SHA256SUMS`, SPDX 2.3 JSON SBOM, schema-2 JSON license
inventory, and build provenance. The inventory covers six direct shipped or
build components: aHPy, the exact embedded Cython base, the packaging example,
HPy, setuptools, and PyPA build. SPDX `CONTAINS` relationships bind embedded
Cython to both aHPy artifacts and `BUILD_TOOL_OF` binds the pinned build
frontend. Provenance records the aHPy and Cython commits, HPy, setuptools and
build-frontend pins, selected Python implementation/version/path, platform,
compiler, and deterministic source epoch. Bundle creation rejects a non-empty
destination, unexpected/missing artifacts, unsafe filenames, duplicate names,
malformed digests, and copied bytes that do not match the validated report.
The no-upload publisher independently rehashes all five artifacts and requires
byte-exact regeneration of all four evidence documents; altered or missing
dependency wheels, checksums, licenses, provenance, or SBOM fail closed.

Local macOS ARM64/CPython 3.11 evidence is complemented by an earlier green
clean sdist/onboarding step in hosted
[compiler-and-quality job 88188395921](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395921).
That hosted job predates the Setuptools 83 loader update; it is historical
platform evidence, and the replacement current-HEAD run remains required.
Cross-interpreter package installation, standardized Universal
extension-wheel reproducibility, publication, and standardized Universal wheel
metadata remain open. The example wheel's CPython tag is not a portability
claim.

Current quality and coverage counts are recorded in
[`m8-focused-backend-coverage.md`](m8-focused-backend-coverage.md) and the
top-level validation matrix rather than duplicated here.
