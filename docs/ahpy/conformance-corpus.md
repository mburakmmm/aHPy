# Frontend-neutral HPy conformance corpus

The versioned conformance protocol lets another compiler or language runtime
exercise the same Python-visible semantics without importing Cython, parsing a
`.pyx` file, or depending on Cython compiler internals. It is a semantic
contract for Universal HPy modules, not a source-language grammar.

The two portable inputs are:

- `tests/ahpy-conformance.toml`, the schema, protocol, suite checksum and
  mandatory surrounding gates;
- `tests/ahpy/conformance-v1.json`, 21 calls covering module functions,
  positional/default/keyword arguments, identity, containers, exceptions and
  chaining, imports/globals/builtins, early returns and cleanup paths.

`Tools/ahpy/run_conformance.py` uses only Python's standard library. The
manifest explicitly sets `frontend_sources_required = false`, pins the suite
by SHA-256, and names a `python-callable-surface-map` contract. No Cython test
path or frontend node is part of schema v2.

## Implement the five surfaces

Compile one or more importable Universal HPy modules that export the callable
names used by these surfaces:

| Surface | Required callables |
| --- | --- |
| `module-functions` | `add_ints`, `echo`, `keyword_mix` |
| `containers` | `build_containers`, `mutate_containers` |
| `exceptions` | `divide_or_none`, `raise_with_payload`, `chained_error` |
| `imports-globals` | `use_import`, `read_global`, `builtin_lookup` |
| `cleanup` | `consume_or_raise`, `nested_early_return`, `loop_cleanup` |

A frontend may put every surface in one extension or use separate modules; the
runner receives the mapping explicitly and never assumes a source layout.
Tagged JSON values preserve Python tuples, lists, sets, dictionaries, fixture
identity, exact builtin exception types/arguments and explicit exception
causes without embedding executable Python in the corpus.

First validate the immutable contract:

```console
python3 Tools/ahpy/run_conformance.py --validate-only
```

Then map each surface to the generated import names:

```console
python3 Tools/ahpy/run_conformance.py \
  --module module-functions=my_language_conformance \
  --module containers=my_language_conformance \
  --module exceptions=my_language_conformance \
  --module imports-globals=my_language_conformance \
  --module cleanup=my_language_conformance \
  --mode normal \
  --output conformance-normal.json
```

Repeat the unchanged binary and mapping in separate processes under HPy Trace
and HPy Debug, passing `--mode trace` or `--mode debug` so retained reports do
not blend runtime modes. A semantic pass alone is insufficient for a Universal
compatibility claim: the manifest also requires generated-source and binary
legacy-API audits, same-binary cross-interpreter execution, HPy Debug and fault
injection. Those compiler- and platform-specific gates remain outside this
frontend-neutral runner and must be retained alongside its JSON reports.

## Versioning and extensions

Consumers must reject unknown manifest, suite or protocol versions. New value
tags, cases or surface callables require a new checksum; an incompatible
contract requires a new protocol name and suite file. Language-specific source
adapters belong in that language's repository and must not be added to the
portable protocol.
