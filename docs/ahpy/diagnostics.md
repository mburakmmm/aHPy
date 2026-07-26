# aHPy Universal diagnostics

All strict backend compatibility errors start with:

```text
aHPy bootstrap backend:
```

They are compiler rejections at a source position, not invitations to emit a
CPython or Hybrid module. The current backend has 193 explicit rejection call
sites. Their complete machine-readable inventory is
`docs/ahpy/audits/diagnostics-catalog.json`.

Each catalog record contains:

- a stable source-location `id`;
- the compiler source file and line that owns the diagnostic;
- its literal or normalized dynamic `message_template`;
- the stable migration action ID and text used by the compatibility scanner.

The catalog is generated from all `unsupported(...)` calls in the Universal
module, statement, expression, and emitter layers. It is not maintained by
hand:

```console
python3 Tools/ahpy/build_diagnostic_catalog.py \
    --output docs/ahpy/audits/diagnostics-catalog.json
python3 Tools/ahpy/build_diagnostic_catalog.py \
    --check docs/ahpy/audits/diagnostics-catalog.json
```

Repository edits must still use the normal patch workflow; the redirection
above is the documented maintainer regeneration command. The test suite rebuilds
the in-memory catalog and compares its parsed JSON exactly with the committed
artifact, so a new, removed, moved, or changed diagnostic cannot bypass review.

For library migration, run `Tools/ahpy/scan_compatibility.py`. It connects
concrete emitted messages to the catalog's action families and adds direct
`cpython.*`/`Python.h` source findings. See
[`migration-scanner.md`](migration-scanner.md) for schema and exit codes.

## Action policy

A migration action may recommend source isolation, a verified alternative
construct, or waiting for a selected public HPy capability. It must never
recommend silent ABI fallback. `compiler-error` is reserved for unclassified
failures such as a traceback or internal compiler error; those are defects to
preserve and report, not supported compatibility rejections.

Dynamic templates retain their formatting placeholders or normalized source
expression. The concrete compilation diagnostic remains authoritative for its
actual type, name, slot, or source construct; the catalog locates the owning
backend decision and supplies its migration family.
