# Draft upstream report: CPython 3.14 closure allocation SIGSEGV

Target: `hpyproject/hpy`
Status: prepared, not filed

## Suggested title

Universal `HPy_New` for a handwritten heap type crashes on CPython 3.14.6

## Environment

- HPy commit: `b57a33c1cec766a1cc3e89f6fd1e2eff73ba9381`
- HPy version: `0.9.1.dev100+gb57a33c1c`
- CPython: 3.14.6
- reproduced on macOS 26 ARM64 and Ubuntu 24.04 x86-64
- compile flags: `-O0`
- HPy ABI: Universal

## Reproduction

From the aHPy repository:

```console
python3.14 -m venv /tmp/ahpy-hpydev314
/tmp/ahpy-hpydev314/bin/python -m pip install \
  -r tests/ahpy/requirements-hpy-dev.txt
CFLAGS=-O0 /tmp/ahpy-hpydev314/bin/python \
  Tools/ahpy/reproduce_hpy_dev_closure.py \
  --python /tmp/ahpy-hpydev314/bin/python
```

The command first builds
`tests/ahpy/hpy_dev_type_reproducer.c`, a handwritten Universal HPy module
containing one GC heap type with one `HPyField`, `HPy_tp_new`,
`HPy_tp_traverse`, and this allocation:

```c
self = HPy_New(ctx, type, &data);
```

It also builds this independently generated aHPy input:

```cython
def closure_roundtrip(value, /):
    captured = value

    def read_capture():
        return captured

    return read_capture()
```

## Actual result

The first handwritten type construction in normal mode terminates with signal
11, before the generated module executes. The macOS crash report records
`EXC_BAD_ACCESS` at address `0x10` with this top stack:

```text
_PyObject_GC_New
ctx_New
_HPy_New
handwritten `reproducer_new_impl`
ctx_CallRealFunctionFromTrampoline
```

The handwritten heap type and generated closure both pass normal, HPy Trace,
and HPy Debug on CPython 3.11.15 with stable HPy 0.9.0. A separate handwritten
Universal HPy module using only ordinary module methods and containers passes
on CPython 3.14.6 with the pinned development revision. This narrows the
failure to HPy heap-type allocation rather than basic loader availability or
aHPy-generated code.

## Expected result

The closure environment allocated through `HPy_New` should be created and the
captured object returned without a native crash, or the unsupported
interpreter/revision combination should fail safely.

The full hosted failure is
[`aHPy` job 90501555346](https://github.com/mburakmmm/aHPy/actions/runs/30428968553/job/90501555346).
