# ADR 0015: Reproducible frontend package archives

- Status: accepted; frontend sdist and wheel gate implemented
- Date: 2026-07-16

## Context

`SOURCE_DATE_EPOCH` made the setuptools frontend wheel deterministic but did
not normalize directory and generated `PKG-INFO` timestamps in the gzip/tar
sdist. Two archives therefore contained identical files but different tar
metadata and compressed bytes. Logical-content comparison would hide this
release/provenance defect.

## Decision

1. Reproducibility builds run from two independently copied source roots with
   fixed `SOURCE_DATE_EPOCH`, `PYTHONHASHSEED=0`, no compiled Cython frontend,
   and exact installed build tooling.
2. The wheel remains the unmodified standards-based build output.
3. The sdist is rewritten without extraction: members are sorted, timestamps
   use the fixed epoch, numeric owner/group are zero, textual owner/group are
   empty, and gzip filename/time metadata is fixed. File payloads and modes are
   preserved.
4. Both archive file sets and complete bytes must match. A schema-versioned
   JSON report records names, sizes, SHA-256 hashes, epoch, interpreter,
   platform, `build`, and setuptools versions.
5. The clean release-artifact path applies the same epoch/hash seed and
   normalizer before auditing and building the wheel from the sdist.
6. This decision covers the `aHPy-compiler` frontend sdist and pure-Python
   wheel. A future standardized Universal extension wheel needs its own
   two-root gate including native compiler/linker provenance.

## Consequences

Archive metadata drift now fails CI even when extracted payloads match. The
normalizer is unit-tested against input order, timestamp, uid, and gid
variation. Changing the epoch or metadata policy requires an ADR/test update;
silently accepting logical equality is not permitted.
