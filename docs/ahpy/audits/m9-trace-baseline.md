# M9 HPy Trace API-call and handle-churn baseline

Date: 2026-07-16
Status: nine-operation Trace baseline locally green

`Tools/ahpy/benchmark_hpy.py` now runs each generated and handwritten
Universal HPy operation 1,000 times in a separate `HPY=trace` child. It records
the exact per-API delta around each operation, total calls per iteration, and
`ctx_Dup`/`ctx_Close` handle churn in the same timestamped CI JSON as runtime,
footprint, compiler, and Debug leak evidence.

The local CPython 3.11.15/HPy 0.9/Apple Clang run recorded:

| Operation | Generated calls/iteration | Reference calls/iteration | Generated dup/close | Reference dup/close |
| --- | ---: | ---: | ---: | ---: |
| identity | 1 | 1 | 1 / 0 | 1 / 0 |
| arithmetic | 11 | 1 | 4 / 2 | 0 / 0 |
| container | 14 | 4 | 4 / 2 | 0 / 0 |
| attribute | 1 | 1 | 0 / 0 | 0 / 0 |
| call | 1 | 1 | 0 / 0 | 0 / 0 |
| exception | 1 | 1 | 0 / 0 | 0 / 0 |
| type create | 15 | 2 | 3 / 4 | 0 / 0 |
| type method | 8.015 | 2.002 | 1.003 / 3.004 | 0 / 0 |
| external C | 7 | 1 | 0 / 2 | 0 / 0 |

The generated arithmetic/container overhead includes `ctx_Tracker_New`,
`ctx_Tracker_Add`, and `ctx_Tracker_Close` per invocation. These counts identify
candidate ownership optimizations; they do not prove a duplication or tracker
is removable. The original attribute/call result was invalidly inflated because
the generated functions accepted keywords while their `HPyFunc_O` handwritten
references did not. After both sides were made positional-only, an ownership-
proven optimization borrows direct live Name handles for `HPy_GetAttr_s` and
zero-argument `HPy_Call`; their Trace count is now exactly the reference count
with no Dup/Close churn. Type-method totals include construction
of one object outside the timed loop but inside the Trace delta. The external-C
generated path loads and converts its two cached integer constants before the
shared C call, while the reference uses C literals directly. No cleanup pair will be changed until its
borrowed/owned/failure-path proof and normal/Debug/fault regressions exist.

The post-optimization Apple Silicon run measured Universal ratios of 0.82×
identity, 2.99× arithmetic, 2.86× container, 0.87× attribute, 1.02× call,
1.00× exception, 3.74× type construction, 5.95× type method, and 3.85× external
C. Generated/reference binaries were 76,816/76,080 bytes. These are local
baselines, not release budgets. Blocked iteration/memoryviews, classic
Cython, HPy CPython ABI, and hosted history remain separate M9 work. Separate
clean peak-RSS children recorded 35,995,648 generated versus 35,799,040
reference bytes (1.005×) across 10,000 iterations of every operation.

## Positional-varargs and borrowed-operand follow-up

Required functions with two or more positional-only arguments now emit
`HPyFunc_VARARGS`. Their incoming `args[]` handles are call-scoped borrowed
values, so the generated wrapper validates exact `nargs` without constructing
an `HPyTracker` or invoking `HPyArg_ParseKeywords`. Closure `HPy_tp_call`
wrappers use the same binding rule. An empty keyword-name tuple from `**{}`
remains valid; the wrapper measures it and rejects only a non-zero keyword
count, including the `HPy_Length` failure path.

Binary APIs and fixed list/tuple builders now reuse direct live Name handles
when their HPy contracts borrow the operand. The left side of a binary
operation is borrowed only if the right side is also a direct Name; otherwise
it is duplicated before the potentially side-effectful right expression is
evaluated. The final Trace record is:

| Operation | Generated calls/iteration | Reference calls/iteration | Generated dup/close | Reference dup/close |
| --- | ---: | ---: | ---: | ---: |
| identity | 1 | 1 | 1 / 0 | 1 / 0 |
| arithmetic | 1 | 1 | 0 / 0 | 0 / 0 |
| container | 4 | 4 | 0 / 0 | 0 / 0 |
| attribute | 1 | 1 | 0 / 0 | 0 / 0 |
| call | 1 | 1 | 0 / 0 | 0 / 0 |
| exception | 1 | 1 | 0 / 0 | 0 / 0 |
| type create | 15 | 2 | 3 / 4 | 0 / 0 |
| type method | 8.015 | 2.002 | 1.003 / 3.004 | 0 / 0 |
| external C | 7 | 1 | 0 / 2 | 0 / 0 |

The final tightened-budget Universal ratios were 1.01× identity, 0.97×
arithmetic, 1.07× container, 1.02× attribute, 1.00× call, 0.98× exception,
4.74× type creation, 6.19× type method, and 5.40× external C. Arithmetic and container ceilings are
now 1.5×. Generated/reference binaries were 76,672/76,080 bytes; generated C
fell to 33,703 bytes. Clean-process peak RSS was 36,044,800 versus 35,995,648
bytes (1.001×). Normal/Trace/Debug runtime, 185 emitter tests, and all 128
isolated fault selectors pass.

## Extension owner and initializer follow-up

Extension-field owners now remain borrowed when they are incoming call-scoped
arguments, and direct Name field values feed `HPyField_Store` without a
temporary duplicate. Type/module owners are created lazily only when a body
uses a constant, default, global, builtin, or closure. Positional-only
`__cinit__`/`__init__` slot arrays validate exact arity and keyword cardinality
without `HPyArg_ParseKeywordsDict` or a tracker. Empty `**{}` remains valid.

The tightened-budget Trace result is:

| Operation | Generated calls/iteration | Reference calls/iteration | Generated dup/close | Reference dup/close |
| --- | ---: | ---: | ---: | ---: |
| type create | 3 | 2 | 0 / 0 | 0 / 0 |
| type method | 2.003 | 2.002 | 0 / 0 | 0 / 0 |

The type-creation difference is the separate generated `__cinit__`
`AsStruct`; the handwritten reference receives its data pointer directly from
`HPy_New`. Universal runtime ratios were 1.02× type creation and 0.96× type
method, both below new 1.5× ceilings. Generated/reference binaries were
76,592/76,080 bytes and generated C was 30,987 bytes. Clean-process peak RSS
was 36,012,032/35,962,880 bytes (1.001×). The 4,654,176-byte/81,349-line type
corpus compiled in 1.449 seconds at `-O0` and 5.190 seconds at `-O3`.

Lazy type/module owner names participate in branch lifetime snapshots. This
was required after the first large-corpus compile caught three C references to
a temporary declared in another branch; the focused fix, regenerated corpus,
native O0/O3 builds, normal/Trace/Debug runtime, 186 emitter tests, and all 128
fault selectors are green.

## Portable external-C literal follow-up

Validated external-C calls now bypass the HPy object round trip for numeric
literals only after proving that the value is portable for the destination C
scalar type. Explicit casts and fixed-width-safe spellings prevent the host
compiler from choosing a different width. Dynamic values, non-finite floats,
plain-`char` values outside 0..127, and integers outside the portable range
still use the existing checked HPy conversion and failure cleanup.

The final Trace record for the shared external add operation is:

| Operation | Generated calls/iteration | Reference calls/iteration | Generated dup/close | Reference dup/close |
| --- | ---: | ---: | ---: | ---: |
| external C | 1 | 1 | 0 / 0 | 0 / 0 |

Both paths contain only `ctx_Long_FromInt64_t`, which converts the native result
to Python. The final Universal ratio was 0.990× and the HPy CPython ABI ratio
was 1.002×, so the Universal ceiling is tightened from 8.0× to 1.5×.
Generated/reference binaries were 76,576/76,080 bytes; generated C was 29,536
bytes. Clean-process peak RSS was 35,831,808/35,946,496 bytes (0.997×). The
4,654,176-byte/81,349-line type corpus compiled in 1.416 seconds at `-O0` and
5.452 seconds at `-O3`. Normal/Trace/Debug, 188 emitter tests, checked fallback
tests, and all 128 isolated fault selectors pass.
