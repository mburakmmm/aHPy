# M1 Runtime API validation record

Date: 2026-07-14  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Python: 3.14.6 for the final aggregate run (initial bootstrap runs used 3.14.2)  
Compiler: Apple Clang 16, C and C++ backends

## Targeted validation

The Runtime API and command-line unit tests passed 63 tests. They cover:

- accepted, unknown, and reserved backend names;
- context-local backend instances;
- cache fingerprint separation;
- capability diagnostics and source positions;
- failure before CPython code generation for not-yet-enabled HPy backends; and
- byte-identical output for default and explicit `cpython` selection.

The five-module aHPy CPython oracle corpus passed all 19 doctests after the
central reference/null/error operations were routed through the Runtime API.
The Runtime API/CLI unit set later grew to 66 passing tests as call layouts and
their validation were added. The same oracle corpus remained at 19/19.

## Full Cython regression matrix

The unrestricted first run completed the suite but returned a nonzero status
only for C++ tests already listed in Cython's
`tests/macos_cpp_bugs.txt`. The failures were Apple SDK/libc++ compatibility
issues such as a changed permutation comparator binding and APIs marked
unavailable below macOS 11; no aHPy-modified compiler path appeared in those
failures.

The authoritative rerun used Cython's platform exclusion list:

```console
python runtests.py -vv -j 4 --excludefile tests/macos_cpp_bugs.txt
```

It completed with exit code 0 and `ALL DONE`. The run produced and exercised
2,767 C/C++ extension modules. Four tests were skipped in one reported shard;
additional tests were excluded automatically when optional dependencies were
not installed, including NumPy, Pythran, Cython coverage support, IPython test
support, and `setuptools.sandbox`.

### Post-lifecycle/call-routing rerun

The expanded lifecycle, type-error-condition, and call-layout refactor was
validated again on Python 3.14.6 with the same authoritative command. The first
rerun correctly found two omitted context-propagation paths:

- three C-tuple Tempita expressions called `CType.error_condition()` without
  the compilation's runtime API; and
- the double C++ exception translator called `get_exception_handler()` twice
  without the runtime API.

The runtime API is now an explicit member of the C-tuple utility template
context, and both C++ handler calls receive the code writer's context-local
instance. Targeted reruns passed for `ctuple`, `pure_ctuple`, `extra_patma`,
`pep526_variable_annotations_cy`, and `cpp_operator_exc_handling` in their
applicable C/C++ modes.

The complete four-shard suite was then rerun from the beginning. It completed
with exit code 0 and `ALL DONE`, generating 2,817 extension modules. The
platform exclusion list and missing optional-dependency exclusions were the
same class of expected exclusions as the earlier run. This second clean run is
the authoritative result for the expanded M1 slice.

## Generated-code result

The seam delegates type-specific CPython spelling to the existing type methods
and now also owns the direct reference duplication, close/clear, null, and
error-state operations emitted by the general code generator. No generated
CPython code change is required or accepted for this slice. A golden regression
test compiles the same representative module with the implicit default and with
`runtime_backend="cpython"` and requires the output bytes to match.

The stronger clean-tree oracle compares the modified compiler with an archive
of the exact upstream base commit. Both compilers were run from the same working
directory, against the same absolute `.pyx` paths, to prevent filename-table
noise. All five generated C files were byte-identical:

- `ahpy_cleanup_paths.pyx`;
- `ahpy_module_functions.pyx`;
- `ahpy_imports_globals.pyx`;
- `ahpy_exceptions.pyx`; and
- `ahpy_containers.pyx`.

An initial comparison from different working directories correctly detected
only the expected filename-table spelling difference
(`ahpy_containers.pyx` versus `tests/run/ahpy_containers.pyx`). Re-running from
one directory removed that environmental difference; it was not a generated
runtime-code regression.

The remaining direct lifecycle spellings are confined to the CPython object
type implementation in `PyrexTypes.py`; `CPythonRuntimeAPI` is the only general
code-generation entry point that delegates to those type methods. Type
conversion error conditions now receive the context-local runtime API
explicitly, so they no longer spell `PyErr_Occurred` independently. The five
clean-tree byte comparisons, 63 Runtime API/CLI unit tests, and 19 aHPy oracle
tests all passed again after this final lifecycle/error routing step.

Tuple/dict, zero-argument, one-argument, no-argument method, and array-based
calls now also pass through the runtime API. Array calls carry receiver and
keyword-layout metadata, and the CPython backend selects the same utility names
and call spellings as upstream. The five clean-tree outputs remained
byte-identical after this call-routing slice.

Performance equivalence remains a separate M1 gate: the seam adds Python-level
dispatch only while compiling and does not add a generated runtime operation.
Dedicated compiler-time and extension-runtime benchmarks are still required
before M1 exits.

### Post-container-routing validation

The container slice added explicit list/tuple builder metadata and operations
for fixed-size, empty, array-based, and packed sequence construction. It also
routed dictionary creation, presizing, item insertion, string-key insertion,
and direct copies in the main code emitters. The HPy contract captures its
distinct builder/result storage, non-stealing `Set`, delayed error reporting,
and mandatory `Build`/`Cancel` lifecycle without enabling incomplete HPy code
generation.

The Runtime API/CLI unit set now passes 71 tests, including a static bypass
guard over `Code.py`, `ExprNodes.py`, `ModuleNode.py`, `Nodes.py`, and
`PyrexTypes.py`. The aHPy oracle selector passes 38 executions: 19 logical
doctests under both the C and C++ backends. All five current compiler outputs
remain byte-identical to the clean-tree outputs from the exact upstream base.

The authoritative full command was then run again for this slice. It completed
with exit code 0 and `ALL DONE`, producing and exercising 2,831 extension
modules. The same platform exclusion file and expected optional-dependency
exclusions applied. This clean run supersedes the earlier full-suite result for
the container-routing state.

### Primitive-conversion routing validation

Scalar conversion descriptors now distinguish direction and semantic kind
instead of exposing only a C helper name. The central `CType` conversion path
uses the context-local runtime API; CPython delegates to the established type
logic and the gated HPy path fails with the value-conversion capability rather
than emitting CPython code.

The Runtime API/CLI set passes 73 tests after adding conversion metadata and
HPy failure-contract checks. The five clean-tree oracle outputs remain
byte-identical. A focused C/C++ conversion selector ran 362 tests successfully,
covering signed/unsigned integer widths, local/external typedefs, booleans,
floats, complex values, C-function conversions, memoryview wrappers, and the
selected subinterpreter tests. It completed with `ALL DONE` and exit code 0.

### Exception-state routing validation

The exception slice models public current-error operations independently from
CPython's type/value/traceback exception triple. Core set-string, set-object,
set-none, format, clear, out-of-memory, matching, current-type, fetch/restore,
raise/reraise, normalize/get, save/reset, and swap emission now enters through
the context-local runtime API. HPy spellings are defined only where the public
API has an exact operation; exception-triple and supplied-exception operations
fail with the `exceptions` capability instead of emitting CPython helpers.

A static bypass test covers `Buffer.py`, `Code.py`, `ExprNodes.py`,
`ModuleNode.py`, `Nodes.py`, and `PyrexTypes.py`. Feature-specific argument,
buffer, unpacking, and C++ helpers remain assigned to their later milestones.

Validation after this slice:

- 23/23 Runtime API unit tests;
- 76/76 combined Runtime API and command-line tests;
- 5/5 generated C files byte-identical to the exact clean upstream archive;
- 38/38 aHPy conformance executions, representing 19 doctests under both C and
  C++ backends; and
- `git diff --check` and Python bytecode compilation passed.

The authoritative full suite was then rerun from a clean test-output state with
the platform exclusion file. All four shards completed successfully with exit
code 0 and `ALL DONE`; the run generated and exercised 2,831 C/C++ extension
modules. The optional-dependency and platform exclusions were the same expected
set documented for the preceding container-routing run. This result supersedes
that run as the full-suite oracle for the current exception-state slice.

### Dynamic-name routing validation

Module-global, builtin, and class-namespace resolution now use immutable lookup
metadata and the context-local runtime API. The CPython backend preserves the
three established Cython helper spellings. The HPy contract fails explicitly
until registered global storage, module execution state, context propagation,
and owned local handles are available; dynamic namespace lookup is not treated
as interchangeable with `HPyGlobal` storage.

The Runtime API/CLI set passes 81 tests, including global-storage ownership,
invalid-layout, and static bypass checks. All five clean-tree generated C
outputs remain byte-identical,
and the C/C++ aHPy selector again passes 38/38 executions. The preceding full
2,831-module run is authoritative for the exception-state slice. The subsequent
dynamic-name source change was covered by its focused C/C++ corpus and was
subsequently included in the final aggregate full-suite gate below.

### Global-storage and module-object boundary validation

Long-lived storage metadata now distinguishes CPython `PyObject *` slots from
registered `HPyGlobal` slots, including registration, per-interpreter lifetime,
load ownership, store transfer, and runtime-managed cleanup. The compiler does
not yet load HPy globals: `HPyGlobal_Load` returns an owned local handle, so M2
must make its close visible on every control-flow edge before cache migration.

An immutable module-definition contract records HPy's mandatory multi-phase
shape and context-bearing exec slot. The module-object hooks map only the public
HPy operations with matching semantics (`HPyImport_ImportModule`, `HPy_SetAttr`,
and `HPy_SetAttr_s`). Manual creation, borrowed module-dict access, borrowed
`sys.modules` access, and CPython's add-module helper fail with the module
definition capability instead of receiving an unsafe approximation.

Validation after routing the principal compiler module-object emitters:

- 85/85 combined Runtime API and command-line unit tests;
- a static bypass guard for the seven core CPython module operations;
- 5/5 generated C files byte-identical to the exact clean upstream archive;
- 38/38 aHPy conformance executions across C and C++;
- Python bytecode compilation and `git diff --check` passed.

The preceding full-suite result was authoritative through the exception slice.
Dynamic-name, global-storage metadata, and module-object routing were
subsequently covered by the final aggregate full-suite run below.

### Definition routing and final M1 aggregate gate

Method calling layouts are now immutable runtime metadata. CPython
`PyMethodDef` entries and tables, `PyType_Slot`/`PyType_Spec` structures,
`PyModuleDef_Slot` arrays, module declarations, and `PyModuleDef_Init` all pass
through explicit definition hooks without changing generated output. The HPy
contract records `HPyDef_METH`, `HPyDef_SLOT`, definition arrays,
`HPyType_Spec`, and `HPyModuleDef`, and rejects unsupported slots or an
expression-style module init instead of synthesizing names.

The combined Runtime API and command-line unit set passes 96 tests. Static
guards cover core operation bypasses, method/type/module definition bypasses,
backend-name confinement, and separation from C/C++ language selection. All
five oracle C files remain byte-identical to the exact upstream base and the
focused C/C++ aHPy selector passes 38/38 executions.

Compiler-time sampling alternated twelve current and twelve upstream-base
processes on `ahpy_imports_globals.pyx`. The current median was 0.222 seconds;
the upstream median was 0.234 seconds, a ratio of 0.952. Since the generated C
files are byte-identical, the representative extension runtime paths and binary
semantics are unchanged.

The final aggregate command was:

```console
python3 runtests.py -vv -j 4 --excludefile tests/macos_cpp_bugs.txt
```

All four shards completed with exit code 0 and `ALL DONE`. The run executed
4,550 tests in 1,293 seconds with 126 expected skips and generated 2,831 C/C++
extension modules. Total sharded wall time was 1,297 seconds (21.6 minutes).
Missing optional dependencies and the documented Apple C++ exclusion list were
the expected set. This run is authoritative for the complete M1 state and
closes the M1 regression gate.
