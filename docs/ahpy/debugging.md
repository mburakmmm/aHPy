# Debugging aHPy Universal failures

Start by identifying the first failing boundary. Do not switch to CPython or
HPy Hybrid to make a failure disappear; that changes the product being tested
and destroys the evidence needed to fix Universal mode.

## 1. Freeze the environment

Record the exact aHPy and Cython commits, interpreter executable and patch,
HPy version/commit, OS, architecture, compiler and flags. Validate the selected
toolchain before reducing the failure:

```console
.venv-hpy09/bin/python Tools/ahpy/doctor.py \
  --python .venv-hpy09/bin/python --strict --json
python3 Tools/ahpy/maintenance_policy.py --json
python3 Tools/ahpy/rebase_log.py --json
```

Use a clean temporary build directory. Preserve stdout/stderr and never attach
virtual environments, credentials, unrelated files or an entire dirty tree to
a report.

## 2. Classify the failing stage

| Stage | Evidence to retain | Correct next tool |
| --- | --- | --- |
| Source compatibility | original source location, diagnostic and action ID | `scan_compatibility.py --json` |
| Compiler crash/internal error | complete traceback and minimized source | compiler/seam tests and issue form |
| Generated-source boundary | emitted C and forbidden spelling | source audit in `test_generated_hpy.py` |
| Native compile/link | exact compiler command, flags and stderr | `direct_build.py --plan-only` then direct integration |
| Binary ABI | undefined/imported symbols and tool output | `nm`, `llvm-nm`, `dumpbin` or `objdump` audit |
| Import/module init | loader path, ABI mode, first exception/signal | staged portability smoke |
| Runtime semantics | smallest call, arguments, result/exception | normal/Trace/Debug semantic oracle |
| Ownership/cleanup | allocation boundary, early exit and leak/fault selector | HPy Debug and fault injection |
| External runtime | handwritten public-HPy reproducer | upstream dependency inventory |

An expected source rejection has a stable source-located migration action. A
traceback, signal, unlocated compiler exit or forbidden generated/binary symbol
is never an expected compatibility result.

## 3. Reduce compiler and source failures

Run the strict scanner with the same interpreter used to compile:

```console
.venv-hpy09/bin/python Tools/ahpy/scan_compatibility.py \
  path/to/failure.pyx --python .venv-hpy09/bin/python --json
```

Delete unrelated declarations while preserving the first diagnostic and its
line/column. Check `diagnostics.md` and `migration-scanner.md` before inventing
a workaround. If the minimal input succeeds, compare compiler directives,
qualified module name, included `.pxd` files and build frontend. If it crashes,
add a focused compiler-seam regression that proves the error becomes either a
supported result or a deliberate diagnostic.

## 4. Inspect generated source and the native plan

Generate without hiding the output in a build cache. Universal C must include
`hpy.h` and must not contain `Python.h`, `PyObject *`, CPython symbols, legacy
HPy/PyObject conversions or a Hybrid initializer. Use the direct build planner
to capture compile/link inputs before executing them:

```console
.venv-hpy09/bin/python Tools/ahpy/direct_build.py \
  --python .venv-hpy09/bin/python \
  --source generated_module.c --module-name generated_module --plan-only
```

Do not manually add Python libraries or headers to “fix” a link. Preserve the
symbol-reader output when an audit fails. On Windows also retain the selected
MSVC/vswhere/vcvarsall environment; on macOS retain architecture selection and
`otool` evidence; on Linux retain the compiler-selected sanitizer runtime.

## 5. Separate semantics from ownership

Reproduce once in normal mode, then in a fresh HPy Trace process and a fresh
HPy Debug `LeakDetector` process. Never import the same extension first in one
mode and then claim another mode in the same interpreter. Exercise success,
conversion failure, callable-raised exceptions, early return, partial
construction, GC cycles and repeated import/unload when relevant.

Trace explains API count and handle churn; it is not a leak detector. HPy Debug
finds handle misuse/leaks; it does not replace ASan/UBSan, Valgrind or Windows
Application Verifier for native memory. A sanitizer run with an
uninstrumented CPython host must retain the documented limitations.

## 6. Prove whether the fault belongs upstream

Replace generated code with the smallest handwritten public-HPy module that
uses the same operation. If both fail, record the dependency as external and
attach the handwritten reproducer; if only generated code fails, keep the bug
in aHPy. Also reproduce ordinary Cython behavior without
`runtime_backend="hpy-universal"` before routing a frontend-neutral problem to
Cython.

The current dependency inventory is `upstream-dependencies.md`. It distinguishes
prepared reports from filed issues and links immutable hosted evidence. Filing
an upstream issue, posting private vulnerability data or changing a support
tier remains an owner-approved external action.

## 7. Minimum report bundle

Include the minimal source, exact command/environment, scanner JSON, generated
C when available, native compiler/link output, binary-symbol audit, normal and
Debug/Trace outcome, failing and passing versions, and the proposed ownership
or migration classification. For a release blocker also include the affected
support-matrix row and a deterministic regression test.
