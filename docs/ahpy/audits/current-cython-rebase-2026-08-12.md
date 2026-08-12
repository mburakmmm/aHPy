# Current Cython rebase audit — 2026-08-12

- Previous base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
- Accepted base: `86b94cef002aa23aea0b390335ea3d9e9b62c19e`
- Embedded Cython version: `3.3.0b1`
- Upstream range: 120 commits; the previous base is an ancestor of the accepted base.
- Integration strategy: non-fast-forward topic merge into `codex/ahpy-bootstrap`.

## Conflict decisions

All six textual conflicts are represented in `tests/ahpy/rebase-log.toml`.
The two workflow conflicts retain required aHPy aggregate contexts and internal
path filtering while accepting current action pins and the corrected benchmark
label trigger. `CmdLine.py` retains the runtime option inside upstream's
non-shared parser boundary. `ExprNodes.py` and `Nodes.py` accept upstream's
generation refactors while keeping Python-runtime operations behind
`RuntimeAPI`; the post-merge bypass scanners found and drove repairs for the
new starred-exception list, tuple and exception-state calls. The shared-utility
test remains serialized because that is part of the validated Windows and
capacity reliability contract.

## Validation record

- Conflict-marker scan: clean.
- Patch whitespace validation: clean.
- Focused compiler/runtime/HPy writer suite on CPython 3.11: 441/441 passed.
- CI policy tests: 8/8 passed.
- Quality-gate tests: 34/34 passed.
- Complete quality-tool suite: 530/530 passed with two expected platform/tool
  availability skips.
- CPython 3.11 focused coverage: backend 9609/9609, frontend seam
  18403/34755 (52.95%), quality tools 9430/9430.
- CPython 3.14.2 focused coverage: backend 9495/9495, frontend seam
  18504/34860 (53.08%), quality tools 9439/9439.
- Generated Universal HPy normal, Trace and Debug execution: passed under the
  required `CFLAGS=-O0` semantic profile.
- Direct Universal HPy build/import: passed under the required semantic
  profile.
- Upstream `except *` and serialized shared-utility end-to-end selection:
  61/61 passed.
- Documentation contract: all 28 required aHPy documents and 72 local links
  passed. A diagnostic full-tree Sphinx `-W` run remains non-authoritative and
  fails on the repository's existing missing `entry` directive, offline
  intersphinx inventories and upstream keyword-reference warnings; it reported
  no rebase-audit or release-contract link failure.
- Hosted required contexts and exact post-merge release provenance are recorded
  after the merge commit is pushed, because both must bind to that immutable
  source commit rather than its pre-merge parent.

Historical milestone audit documents retain the base on which their evidence
was originally collected. Current product metadata, the support contract and
the append-only rebase log identify only the accepted base above.
