# M2 handle-model validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: M2 in progress; a strict M3 bootstrap emitter is enabled while general
Universal HPy code generation remains gated

## Completed foundation

The compiler-visible model now covers:

- local `HPy`, object-owned `HPyField`, registered `HPyGlobal`, and
  context-constant storage;
- owned, borrowed-argument, and immortal ownership;
- live, moved, and closed states;
- exhaustive contracts for the M1 HPy handle-operation surface;
- duplicate, close, operation-result, load, store, and return transitions;
- reusable C temporary slots with distinct logical handle generations;
- owned Python-expression temp disposal, absorbed-result moves, and generic
  coercion ownership;
- cleanup planning plus strict state merging across every early-exit kind;
- the sole ownership-aware runtime-global load/disposal writer path, with a
  static bypass guard;
- backend and function-level call-scoped context propagation contracts; and
- exact `HPy` and opaque builder C storage plus builder lifecycle integration.

Most of this layer remains executable without C compilation. A narrow M3
bootstrap emitter now exercises call-scoped context, borrowed positional
arguments, `HPy_Dup`, owned scalar returns, nested owned temporaries,
container cleanup, loop break/continue body-temp cleanup, return/raise from
loops, and mixed terminating/continuing conditional branches in generated C.
Broader expression/coercion ownership and utility-context propagation remain
gated.

## Validation

The focused unit command covers the handle model, Runtime API, CLI, function
temporary integration, expression integration, and existing code-writer tests:

```console
python3 -m unittest \
    Cython.Compiler.Tests.TestHandleModel \
    Cython.Compiler.Tests.TestRuntimeAPI \
    Cython.Compiler.Tests.TestHPyModuleWriter \
    Cython.Compiler.Tests.TestCmdLine \
    Cython.Compiler.Tests.TestCode
```

It currently passes 303 tests, including 56 focused handle-model tests. Python bytecode
compilation and `git diff --check` also pass. The generated Universal corpus also
passes normal/Trace/Debug with the new loop-exit and mixed-branch surface under
the documented O0 stress profile (ordinary Apple Clang `-O3` on
`bootstrap_types.c` remains an independent M9 timing gate).

The CPython behavioral oracle was run in both generated languages:

```console
python3 runtests.py -vv --backends=c,cpp ahpy_
```

It passes 38/38 executions (`ALL DONE`), rerun after the HPy storage and builder
slice: 19 doctests over five modules under
both C and C++. This confirms that the dormant handle-aware path has not altered
the selected CPython runtime behavior.

## Real HPy 0.9 execution oracle

An isolated Python 3.11 environment pins `hpy==0.9.0` and
`setuptools==80.9.0`; HPy 0.9's generated loader still imports
`pkg_resources`, which newer setuptools releases remove. The handwritten
`tests/ahpy/minimal_universal.c` reference module uses only public HPy and
contains `HPy_MODINIT`, no-argument methods, owned scalar returns, `HPy_Dup`,
and a list-builder path with allocation-failure cleanup.

```console
.venv-hpy09/bin/python Tools/ahpy/test_minimal_hpy.py
```

The command builds a `.hpy0` binary outside the worktree with
`HPY_ABI_UNIVERSAL` and HPy's `forbid_python_h` include guard. It scans the
source for legacy C-API spellings, loads and checks the module normally, then
loads it with `HPY=debug` and wraps all calls in `hpy.debug.LeakDetector`.
Both lanes pass with zero reported open handles. This remains the handwritten
toolchain and ownership oracle; the separate M3 bootstrap audit records the
first generated aHPy execution.

Authoritative HPy ownership references verified for this slice:

- <https://docs.hpyproject.org/en/latest/api.html#handles>
- <https://docs.hpyproject.org/en/latest/api-reference/builder.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-field.html>
- <https://docs.hpyproject.org/en/latest/api-reference/hpy-global.html>
