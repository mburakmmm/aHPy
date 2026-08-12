# M8 expanded fault-injection validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: expanded sequential normal/Debug gate passes

One generated Universal module is source- and binary-audited, then executed in
150 isolated processes. Runtime injection covers 14 operation families and 44
failure/one-past boundaries per mode: scalar conversion, the scalar and fixed-
array buffer exporters' two ordered `HPy_Dup` transfers, three nested list and
tuple builder builds, three dictionary insertions, four direct call layouts,
one expanded call, one `HPy_CallMethod` direct method-call layout, three
attribute/item reads, and attribute/item set/delete.

The import lane derives its bounds from the generated module-exec function. It
fails every `HPyType_FromSpec` call and every `HPy_SetAttr_s` publication
positions, plus each one-past success boundary, in normal and Debug modes.
Every failure must be exact `MemoryError`, remove the module from `sys.modules`,
survive collection, and leave Debug `LeakDetector` clean.

The expanded publication sweep found that HPy 0.9 cleanup attribute deletion
can clear an active allocation error. Module exec now records each successful
publication once, matches `MemoryError` before cleanup, closes live handles and
builders, removes publications in reverse order, and restores only the
positively identified `MemoryError`. Other exception classes retain the normal
propagation path because HPy 0.9 has no public exception fetch/restore API.

```console
.venv-hpy09/bin/python Tools/ahpy/test_fault_injection.py \
    --python .venv-hpy09/bin/python
```

The deterministic gate is intentionally sequential. The bounded process-group
stress runner separately passed five concurrent rounds containing all 750
fault selectors, with generated, setuptools, and fixed-fuzz siblings in every
round.
