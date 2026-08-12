# Cython upstream baseline and rebase log

The machine-readable log is `tests/ahpy/rebase-log.toml`. It is append-only:
every accepted Cython baseline transition records the previous and new full
commits, date, strategy, conflict decisions and validation documents. Validate
the chain against `ahpy_version.py` and the release contract with:

```console
python3 Tools/ahpy/rebase_log.py
python3 Tools/ahpy/rebase_log.py --json
```

## Current baseline

- Upstream: `https://github.com/cython/cython.git`
- Exact commit: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
- Commit date: 2026-07-13
- Subject: `Merge branch '3.2.x'`
- Relationship: this commit is the merge base of the current aHPy topic branch.

The first log event is a baseline selection, not a claimed rebase; its old and
new commits are deliberately equal and its conflict list is empty. Future
`rebase` events must continue from the preceding accepted base and change the
commit. The final event must always equal the base embedded in package and
release metadata.

## Conflict classifications

Every conflicted path is recorded exactly once per event:

- `upstream-taken`: upstream behavior replaces the downstream copy;
- `backend-neutral`: retain/refine the seam and prepare a focused Cython PR;
- `ahpy-specific`: preserve the Universal backend behavior downstream;
- `obsolete`: remove code made unnecessary by upstream.

A decision states what was kept and why; “resolved” alone is insufficient.
Before accepting a new base, follow `maintenance.md`: inspect the whole commit
range, use a topic branch, run full Cython plus applicable aHPy/native gates,
and update version, support, audit, changelog and provenance records together.

No newer upstream HEAD is implied by this log. Monthly review may conclude
“no transition”; only an actually validated accepted base creates a new event.
