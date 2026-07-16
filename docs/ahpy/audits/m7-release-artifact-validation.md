# M7 clean release-artifact validation

Date: 2026-07-16
Status: local sdist, offline install, and uninstall/reinstall green

`Tools/ahpy/release_artifact_integration.py` built
`ahpy_compiler-3.3.0.1.dev0.tar.gz` from a clean frontend source tree. The
archive includes exact project metadata, the PEP 517 backend, external
build-system contract, compiler/runtime packages, maintained
tools/tests/docs/examples, and license. Its reviewed manifest emits no missing
source warnings. The safety audit records the current member count in JSON and
rejects traversal, links, native binaries, bytecode, caches, and VCS data.

With index access disabled, the gate built the frontend wheel from that sdist,
created a new virtual environment, installed the exact frontend plus HPy 0.9.0
and setuptools 80.9.0, and built the maintained PEP 517 example. The example
passed normal and Debug LeakDetector execution. Both the frontend and example
then passed uninstall, clean-directory absence verification, reinstall, and a
final normal execution.

The schema-versioned JSON record hashes the sdist, frontend wheel, example
wheel, HPy 0.9 wheel, and setuptools 80.9.0 wheel. Exact hashes are preserved
in the requested local JSON output and in the CI evidence artifact for hosted
runs, avoiding a self-referential hash inside the sdist itself.

This is local macOS ARM64/CPython 3.11 evidence. Hosted Linux execution,
cross-interpreter package installation, standardized Universal extension-wheel
reproducibility, publication, and standardized Universal wheel metadata remain
open. The example wheel's CPython tag is not a portability claim.

The current quality-tool suite passes 111 tests with one expected local
Valgrind availability skip. The 455-test focused trace remains above the
unchanged floors: Python 3.11 records 73.69% backend, 28.75% frontend seam, and
35.49% quality tools; Python 3.14.6 records 72.85%, 28.62%, and 35.60%.
