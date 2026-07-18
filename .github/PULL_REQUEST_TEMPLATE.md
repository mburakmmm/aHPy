## Summary

Describe what changed and why.

## Universal HPy contract

- Supported/rejected source forms:
- Handle ownership and cleanup:
- Failure-path behavior:
- CPython/Hybrid fallback risk:
- Interpreter/module-state impact:

## Validation

List exact commands and results. Include normal, HPy Debug/Trace,
fault-injection, binary-boundary, and CPython regression evidence where
applicable.

## Documentation

- [ ] Support matrix updated or confirmed unchanged
- [ ] Validation/audit evidence updated
- [ ] `docs/ahpy/changes/` fragment added
- [ ] `TODO.md` and `AGENTTODO.md` status kept consistent

## Checklist

- [ ] Unsupported Universal behavior fails closed with a source-located diagnostic
- [ ] No `Python.h`, `PyObject *`, CPython symbol, or HPy Hybrid fallback entered generated Universal code
- [ ] New external GitHub Actions are pinned to full 40-character commit SHAs
- [ ] Generated files, build outputs, environments, and unrelated changes are excluded
