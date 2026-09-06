# Prepared upstream report: GraalPy Universal HPy loader gap

Status: hosted loader classification confirmed; technically ready, but do not
file without explicit owner authorization.

Target issue tracker: `https://github.com/oracle/graalpython/issues`

## Proposed title

`GraalPy 25.1.3 cannot discover an unchanged Universal HPy 0.9 .hpy0 module`

## Environment

- Builder: CPython 3.11.15, HPy 0.9.0, setuptools 83.0.0, Ubuntu 24.04 x86-64.
- Target: `graalpy-25.1.3` from `actions/setup-python`.
- Artifact: unchanged Universal `.hpy0.so`; no target-side rebuild.
- Current evidence: GitHub Actions run `34030366000`, job `101478712970`.

## Minimal source

`tests/ahpy/minimal_universal.c` is a handwritten public-HPy module independent
of Cython and the aHPy emitter. `Tools/ahpy/build_portability_artifact.py`
builds the module and records the byte identity of its binary and loader stub.
`Tools/ahpy/portability_smoke.py` checks whether `hpy.universal` is discoverable.
If it is not, the driver removes CPython's generated loader stubs, retains only
the unchanged `.hpy0` binaries, and tries the native import in an isolated
`import-minimal` subprocess.

## Reproduction

On an Ubuntu 24.04 x86-64 builder with CPython 3.11 and the repository's
pinned requirements:

```console
python -m pip install -r tests/ahpy/requirements-hpy09.txt
CFLAGS=-O0 python Tools/ahpy/build_portability_artifact.py \
  --python python --output portability-artifact
```

Transfer `portability-artifact` byte-for-byte to the target, then run:

```console
graalpy -m pip install setuptools==83.0.0
graalpy portability-artifact/portability_smoke.py \
  --report portability-result-GraalPy-25.1.3.json
```

The command prints the interpreter identity, selected loader mode, verified
builder identity, native filenames, and first failing isolated stage.

## Expected result

GraalPy exposes either an HPy Universal Python loader or a native `.hpy0`
import suffix, imports the unchanged module, and returns `42`, `None`, and
`[1, 2]` from its three methods.

## Current actual result

In run `34030366000`, job `101478712970`, GraalPy 25.1.3 reported
`EXTENSION_SUFFIXES` as `.graalpy250-312-native-x86_64-linux.so`, `.so`, and
`.pyd`, exposed neither
`hpy.universal` nor a native `.hpy0` suffix. Native-only staging therefore
failed at the first module import with `ModuleNotFoundError`. The artifact was
not rebuilt, renamed to a CPython suffix, or routed through a CPython C-API
fallback. The unchanged handwritten binary SHA-256 was
`fd4be0297fcc40c74941d8db59d443be722b9985b070b6668428dd5376f498b5`.
Artifact `9988411879` has GitHub archive digest
`50fc6bd9b3d13fdcbd60f2ac912dabfb85d7dac00e574618dd254d091d1f5cd7`;
the retained JSON SHA-256 is
`697353d1c6e7c4025c71b16d91ce15a39f326126942a240a3a32bedc7bf67b71`.
The byte-identical JSON is retained at
[`evidence/portability-34030366000/portability-result-GraalPy-25.1.3.json`](evidence/portability-34030366000/portability-result-GraalPy-25.1.3.json).

## Filing guard

The required run/job URL, binary digest, extension suffixes, loader probe, and
full `ModuleNotFoundError` are retained in the uploaded
`ahpy-portability-GraalPy-25.1.3` JSON. External publication remains an owner
decision; if a newer GraalPy supplies a Universal HPy loader before filing,
rerun and replace this evidence.
