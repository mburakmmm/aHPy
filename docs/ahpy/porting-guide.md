# Porting a Cython library to aHPy Universal HPy

This guide is for library authors evaluating the explicit aHPy-supported
subset. It does not promise that arbitrary Cython packages compile unchanged.
Universal mode must either produce public-HPy-only code with proven ownership
or stop at the original source location with migration guidance.

## 1. Freeze a reproducible input

Record the upstream project URL, full 40-character commit, version metadata,
SPDX license, license file and exact `.py`/`.pyx`/`.pxd`/native sources. Work
from a detached clean checkout. Keep the port patch separate so its checksum
and complete diff can be attached to CI evidence.

## 2. Inventory incompatible boundaries

Run the strict scanner before editing:

```console
.venv-hpy09/bin/python Tools/ahpy/scan_compatibility.py \
  path/to/module.pyx --json
```

Classify each finding instead of replacing API names mechanically:

- `cpython.*`, `Python.h`, `PyObject *` and legacy HPy/PyObject conversions
  must leave the Universal translation unit;
- relative cross-module Cython cimports must become ordinary Python imports
  and Python-callable boundaries; module-level `cdef`/`cpdef` entry points
  should become `def`, with genuinely native helpers isolated separately;
- `libcpp` runtime state such as atomics must use a semantically equivalent
  supported native scalar or move behind a Python-independent C-compatible
  shim; never silently discard synchronization guarantees;
- `cimport numpy` and `from numpy ... cimport ...` use NumPy's CPython C API;
  keep arrays as ordinary Python objects or select an independently reviewed
  HPy-compatible boundary;
- pointer/length buffer access remains blocked on HPy 0.9 because it has no
  public buffer-consumer acquire/release API;
- Python-independent external C may cross only through the scalar contracts in
  `external-c.md`;
- extension object references require `HPyField`, traverse/clear ownership and
  Debug Mode validation; supported inheritance is same-module single
  inheritance from an earlier generated aHPy type;
- iterator-protocol, fused-type, unsupported exception-state, C++ and parallel
  surfaces stay outside the subset unless their support-matrix row says
  otherwise.

Never resolve a finding by selecting CPython ABI, HPy Hybrid, including
`Python.h`, or converting an HPy handle to `PyObject *`.

## 3. Minimize and separate the port

Prefer these transformations:

1. move CPython-only behavior to a pure Python helper called through an
   ordinary Python boundary;
2. expose a small Python-independent scalar C shim instead of native structs,
   pointers, callbacks or interpreter-aware error checks;
3. materialize an arbitrary iterator before entering a supported
   sequence-index loop when that preserves the public semantics;
4. express state as module-owned handles, `HPyField` references or supported
   native scalar fields with explicit ownership;
5. keep unsupported optional acceleration disabled while preserving a working
   pure Python package path.

If a transformation changes public semantics or performance characteristics,
record it as a blocking decision rather than hiding the difference.

The maintained murmurhash pilot demonstrates the scalar-shim case: an
unsigned 64-bit value crosses the Universal boundary, while serialization,
byte pointers and the upstream MurmurHash3 call stay in C++. Because this does
not preserve upstream `hash(str | bytes)`, the evidence says
`partial-scalar-adapter`; it must not be promoted to whole-library `pass`.

The frozenlist pilot demonstrates a second honest subset: object-field GC and
same-module inheritance can pass while atomic free-threading and iterator/rich
comparison APIs remain excluded. A subset report must name both the preserved
semantics and every omitted public surface.

## 4. Generate and audit Universal source

Use the selected build integration (`setuptools`, direct build, PEP 517,
CMake, Meson or scikit-build-core) with
`runtime_backend="hpy-universal"`. Generated code must include `hpy.h`, must
not include `Python.h`, and must not reference forbidden CPython or legacy HPy
conversion symbols. An unsupported construct must produce a source-located
diagnostic; a traceback or internal compiler error is a compiler bug.

## 5. Prove runtime and ownership behavior

Run the upstream test subset and a focused semantic oracle in all three modes:

- normal execution for public results and exceptions;
- HPy Trace for API calls and handle churn;
- HPy Debug with leak detection, failure cleanup and repeated import/unload.

Exercise success, conversion failure, exception propagation, early returns,
GC cycles, inheritance construction/cleanup and allocation/API fault injection
as applicable. Import the produced binary through the declared production
loader/build path, not an in-process compiler shortcut.

## 6. Record comparable performance only

Measure generation time, native build time, generated C size, binary size,
peak RSS and representative runtime only after semantics are comparable and
supported. Separate HPy runtime/interpreter cost from aHPy code-generation
overhead. A blocked NumPy/buffer/iterator path receives no fabricated ratio.

## 7. Report a compatibility result

Attach exact revisions, environment, commands, full source diff, scanner JSON,
generated-source and binary audits, normal/Trace/Debug logs, tests and artifact
checksums. Use the `Library compatibility report` issue form. Status vocabulary
is fail-closed:

- `pass`: every declared gate passed for the exact evidence set;
- `fail`: a supported gate regressed or produced incorrect behavior;
- `blocked`: a documented API/semantic boundary prevents the port;
- `compiler-error`: a traceback, crash or unclassified internal failure;
- `not-run`: no retained evidence exists.

Only repeated port changes with general ownership and failure-path proofs
should become backend support. Project-specific workarounds remain migration
rules or documented adapters.
