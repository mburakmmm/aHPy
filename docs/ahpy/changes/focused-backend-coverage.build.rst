The focused dual-interpreter coverage gate now requires 100% executable
Python-line coverage for the Universal backend, reports exact missing
lines/ranges in schema 2 artifacts, and traces measured modules from source to
avoid stale-extension blind spots.
Nested coverage self-tests now restore the outer trace function instead of
silently undercounting alphabetically later quality-tool tests.
The corrected dual-interpreter baseline raises the quality-tool CI floor from
41% to 50%.
Reproducibility and direct-build integration control flow now has focused
unit coverage above 97% without replacing their real hosted integration gates.
The build-system contract CLI's JSON, CMake, Meson, stdout, and file-output
branches are also covered while real CMake/Meson builds remain separate gates.
The portability artifact builder's reproducible flags, generated-source and
binary audits, copied loaders, hashes, sizes, manifest, and CLI resolution now
have focused control-flow coverage above 95%.
CMake/Meson tool discovery, contract preparation, build commands, artifact
selection, normal/Debug loading, reports, and CLI selection now have focused
control-flow coverage above 98%.
The isolated scikit-build-core wheel path now has focused coverage for pinned
dependency materialization, wheel/tag inspection, Universal source/binary
audits, install, normal/Debug execution, evidence output, and CLI reporting.
The setuptools/cythonize integration now has focused coverage for Universal
generation, external-C boundaries, normal/Trace/Debug execution, wheel
contents/tags, target installation, and interpreter CLI resolution.
The HPy-development closure reproducer now has focused coverage for
handwritten/generated source and binary audits, loader stubs, all six
normal/Trace/Debug runtime checks, crash classification, and CLI selection.
The Linux LSan/Valgrind gate now has focused control-flow coverage above 98%
for platform/tool rejection, reviewed suppressions and environment evidence,
the mandatory leaking positive control, generated-corpus runtime prefixes,
and exact per-process log cardinality.
The per-process Windows AppVerifier wrapper now has focused control-flow
coverage above 98% for tokenized marker environments, runtime timeouts,
stdout/stderr and JSON evidence, XML export, child failures, and fail-closed
export validation.
The isolated PEP 517 frontend build now has focused control-flow coverage above
96% for exact frontend and dependency wheels, offline isolation, Universal
wheel/source/binary audits, normal/Debug installation checks, provenance
metadata, hashes, report output, and CLI selection.
The unchanged-artifact portability smoke now has focused control-flow coverage
above 98% for manifest safety, size/hash integrity, native-binary staging,
source-path isolation, all four semantic stages, signal/exit diagnostics, and
both Python-stub and native loader selection.
The clean release-artifact integration now has focused control-flow coverage
above 96% for the reproducible sdist, exact offline wheelhouse, isolated
frontend install/uninstall/reinstall, example rebuild and runtime modes,
dependency provenance, immutable bundle assembly, hashes, reports, and CLI.
The Windows AppVerifier orchestration now has focused control-flow coverage
above 95% for SDK tool discovery, full-page-heap configuration, injection
probes, positive-control compilation and XML validation, five-process runtime
cardinality, dirty-log detection, raw evidence, cleanup, and failure paths.
The deterministic supported-surface fuzz driver now has focused control-flow
coverage above 99% for all generated templates, rejected diagnostic/crash
contracts, Universal source/binary audits, normal/Debug semantic oracles,
interpreter selection, and CLI validation.
The compiler-coverage-guided fuzz driver now has focused control-flow coverage
above 99% for all mutation families, measured-line filtering, incremental
greedy selection, traced compilation failures, Universal source/binary audits,
normal/Debug semantic oracles, interpreter selection, and CLI validation.
The release benchmark's focused control-flow coverage is now above 95%,
including budget/environment validation, every semantic mismatch, debug leak
checks, native compiler profiles and timeouts, extension discovery, subprocess
failure diagnostics, peak RSS, all internal/public CLI dispatch paths, and
the complete Universal/HPy-CPython/classic multi-ABI report assembly.
The compatibility scanner now has focused control-flow coverage above 99% for
lexical masking, static CPython/PyObject rules, compiler diagnostics,
Universal generated-header validation, status aggregation, text/JSON reports,
interpreter/source validation, allow-rejected policy, and CLI exit codes.
The dual-interpreter quality-tool suite now contains 504 tests and covers
8687/8687 executable lines on CPython 3.11 and 8694/8694 on CPython 3.14
(100% on both), while the Universal backend remains at 100% and the frontend
seam remains above its 45% floor.
Nightly environment provenance, diagnostic catalogs, publish preparation,
doctor reports, coverage reporting, bounded stress orchestration,
reproducibility checks, sanitizer launchers, and external build contracts now
include their fail-closed schema, subprocess, platform, and CLI branches.
The quality-tool CI floor is raised from 50% to 100% so the expanded control-flow
coverage cannot silently regress while retaining interpreter-specific headroom.
Release, PEP 517, scikit-build-core, setuptools, provenance, portability,
AppVerifier, process cleanup, and Windows peak-RSS artifact/cardinality failure
paths now have deterministic focused tests instead of relying on hosted
failures to exercise their validation contracts.
Coverage excludes only ellipsis interface stubs and behavior-free top-level
repository-path/``__main__`` dispatch wiring; real imported behavior and every
CLI ``main()`` body remain measured, with subprocess entrypoint tests retained.
