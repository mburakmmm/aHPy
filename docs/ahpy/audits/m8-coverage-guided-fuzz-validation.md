# M8 coverage-guided fuzz validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: deterministic guided frontend/runtime gate passes

The tool uses seed `0xC0A4F9` to generate 64 valid Python/Cython candidates
across 16 feature families. After a compiler warmup, each candidate is compiled
under the standard-library line tracer. A greedy frontier retains a candidate
when it executes a previously unseen line in `HPyModuleWriter`, `HandleModel`,
`RuntimeAPI`, `Nodes`, or `ExprNodes`, or represents a previously unseen family.

The current Python 3.11 run selects 16/64 candidates, retains all 16 families,
and records 4,075 compiler/backend lines. The selection is source ordered and
depends only on the explicit seed and observed line sets; it does not modify
Python's global random state.

The selected sources are combined into one Universal module. The gate rejects
forbidden source and undefined binary imports, then compares every selected
function against `exec` of the identical source in normal and HPy Debug modes.
Debug execution is wrapped in `LeakDetector`. The corpus includes arithmetic,
nested containers, expanded and keyword calls, module-global mutation,
current-error handlers, `while` and fixed-sequence `for` control, slices,
comparisons, imports/attributes, item mutation, starred containers, in-place
operators, and conditional expressions.

```console
.venv-hpy09/bin/python Tools/ahpy/coverage_guided_fuzz.py \
    --python .venv-hpy09/bin/python \
    --seed 0xC0A4F9 --candidates 64
```

This gate complements rather than replaces the fixed 48-function grammar
corpus and deterministic rejected-input diagnostics.
