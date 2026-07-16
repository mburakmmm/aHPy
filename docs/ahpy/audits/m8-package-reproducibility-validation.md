# M8 frontend package reproducibility validation

Date: 2026-07-16
Status: local frontend sdist and wheel byte-reproducible

The first two-root run proved the frontend wheel byte-identical but failed the
sdist. Tar inspection found 40 differing metadata entries—generated directory
and `PKG-INFO` timestamps—with zero file-content differences. ADR 0015's
streaming normalizer now sorts members and fixes tar ownership/time plus gzip
name/time metadata without extracting the archive.

The final CPython 3.11.15/macOS ARM64 run built both formats from two
independent clean source roots with `SOURCE_DATE_EPOCH=1767225600`,
`PYTHONHASHSEED=0`, build 1.5.0, and setuptools 80.9.0. The complete sdist and
wheel bytes match across roots. Names, sizes, SHA-256 hashes, and provenance
are retained in the requested JSON output locally and the CI artifact on
hosted runs.

This closes frontend archive reproducibility only. The existing `.hpy0`
portability artifact has a separate native gate. A future standardized
Universal extension wheel still requires two-root native compiler/linker and
archive reproducibility evidence.
