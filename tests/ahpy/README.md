# Universal HPy reference corpus

`minimal_universal.c` is a handwritten public-HPy oracle, not generated aHPy
output. It proves that the pinned HPy toolchain can build and load a Universal
module and gives generated-code tests a known-good structural target.

Create the isolated pinned environment and run it from the repository root:

```console
.venv-hpy09/bin/python -m pip install -r tests/ahpy/requirements-hpy09.txt
.venv-hpy09/bin/python Tools/ahpy/test_minimal_hpy.py
```

The test builds outside the worktree, scans out legacy C-API spellings, loads
the `.hpy0` binary normally, and repeats the same semantic checks in HPy Debug
Mode.

`bootstrap_answer.pyx` is the first strict generated-code vertical slice. Run
`Tools/ahpy/test_generated_hpy.py` to compile it through Cython's
`hpy-universal` backend, reject legacy C-API spellings, build its `.hpy0`
binary, and execute it in both normal and HPy debug modes.

The separate `conformance-v1.json` suite is frontend-neutral. Its checksummed
descriptor is `tests/ahpy-conformance.toml`, and
`Tools/ahpy/run_conformance.py` executes the same 21 Python-visible cases
against explicit import-name mappings from any language frontend. See
`docs/ahpy/conformance-corpus.md`; no Cython source path is part of that
protocol.

The opt-in NOX export-analysis fixture proves that metadata comes from the
analysed Cython tree and symbol types rather than generated C. Reproduce and
byte-check it from the repository root with:

```console
.venv-hpy09/bin/python Tools/ahpy/nox_export.py \
    tests/ahpy/nox_export_source.pyx --module-name example.exports \
    --output tests/ahpy/nox-export-analysis-v1.json --check
```

This intermediate descriptor is not a complete NOX package manifest: package
identity, producer/source/options provenance, target artifacts, and hashes are
bound by the later package-composition stage.

The current v1 composer can reproduce the full retained manifest after export
analysis and artifact integrity checks:

```console
.venv-hpy09/bin/python Tools/ahpy/nox_package_manifest.py \
    tests/ahpy/nox_export_source.pyx \
    --module-name example.exports \
    --package-name example_exports --package-version 0.1.0 \
    --source-root . \
    --artifact macos-aarch64 artifacts/macos-aarch64/exports.hpy0 \
      tests/ahpy/nox-artifact-fixture.hpy0 \
    --output tests/ahpy/nox-hpy-manifest-v1.json --check
```

`nox-artifact-fixture.hpy0` is deterministic integrity-test data, not a
loadable extension and not consumer conformance evidence.
