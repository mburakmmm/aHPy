# M6 one-level closure validation record

Date: 2026-07-16
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
HPy: `0.9.0` Universal ABI
Host: Apple Silicon, CPython 3.11.15
Status: partial one-level nested-`def` slice green locally

## Ownership model

ADR 0005 defines one synthesized pure-HPy environment type per outer
function. Captured Python values occupy `HPyField`s and sibling nested
functions share the stable union of their captures. Each callable instance
owns an `HPyField` reference to that environment. Loads duplicate an owned
handle, stores update the shared field, traverse slots visit every field, and
no `HPyContext *` is persisted.

Capture-free nested functions still own an empty environment object. C-typed
captures are rejected before emission because this slice deliberately supports
only Python-value cells.

## Regression found during continuation audit

The initial implementation fixed an environment layout from the first nested
function encountered. A sibling that captured a different outer name therefore
failed generation with “no initialized local HPy value.” The registry now
merges every sibling's capture set in deterministic source order. Focused
emitter tests cover both the union and the capture-free layout.

## Runtime and failure evidence

`tests/ahpy/bootstrap_answer.pyx` exercises captured addition, outer mutation,
two siblings capturing different values, and a capture-free constant reader.
`Tools/ahpy/test_generated_hpy.py` generates one Universal binary, audits the
source and undefined imports, and executes those cases in normal, Trace, and
Debug modes. The post-fix local run passed with `CFLAGS='-O0 -g0'`.

The focused compiler suite passed 334 tests, the quality-tool suite passed 70
tests with one expected local Valgrind-availability skip, and all 150 isolated
allocation/API fault cases passed. Fixed-seed fuzz passed 48 cases;
coverage-guided fuzz retained 16 of 64 mutations across 16 families and reached
4,075 compiler lines. Focused Python coverage traced 404 tests at 73.83%
backend, 27.08% frontend seam, and 40.13% quality tools.

## Deliberate boundary

This record does not claim full Cython closure support. C-typed cells,
nested-nested closures, defaults, `*args`/`**kwargs`, generators/`yield`, and
decorated nested defs fail with actionable diagnostics. Generators, native
coroutines, async generators, code-object introspection, sanitizers on hosted
platforms, and the full existing Cython closure subset remain separate gates.
