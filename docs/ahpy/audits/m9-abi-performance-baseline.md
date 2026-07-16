# M9 separate ABI performance baseline

Date: 2026-07-16
Status: local three-profile measurement green

`Tools/ahpy/benchmark_hpy.py` measures the same nine semantic operations in
three profiles but does not collapse them into a cross-ABI ratio:

- classic Cython/CPython records standalone per-call timings;
- generated HPy CPython ABI is compared only with the handwritten HPy CPython
  ABI build;
- generated HPy Universal ABI is compared only with the handwritten HPy
  Universal build and remains the profile with enforced local budgets.

The CPython 3.11.15, HPy 0.9, Apple Clang 21 local run recorded:

| Operation | Classic Cython ns | HPy CPython ratio | HPy Universal ratio |
| --- | ---: | ---: | ---: |
| identity | 19.520 | 5.395× | 4.642× |
| arithmetic | 21.232 | 4.401× | 3.969× |
| container | 27.600 | 3.249× | 3.268× |
| attribute | 17.343 | 2.431× | 2.303× |
| call | 118.877 | 1.549× | 1.582× |
| exception | 112.784 | 1.005× | 1.001× |
| type create | 23.806 | 5.301× | 4.766× |
| type method | 11.932 | 6.533× | 5.993× |
| external C | 13.353 | 6.625× | 5.987× |

The two HPy ratios are generated/reference comparisons inside the named ABI;
they are not relative to classic Cython or to each other. The classic profile
produced 425,541 bytes of C and a 109,232-byte extension; its frontend/native
times were 0.354/0.534 seconds and clean-process peak RSS was 25,100,288 bytes.
The HPy CPython generated/reference binaries were 116,896/115,744 bytes, its
combined native build took 2.446 seconds, and peak RSS was
25,247,744/25,100,288 bytes (1.006×). Universal peak RSS was
35,602,432/35,635,200 bytes (0.999×).

The same run regenerated the 4,978,328-byte/87,259-line extension-type corpus.
Frontend generation took 0.806 seconds; isolated Apple Clang 21 compilation
took 1.593 seconds at `-O0` and 5.290 seconds at `-O3` (3.321×). Both profiles
are subject to a 60-second liveness ceiling. This controlled single-compiler
measurement did not reproduce the earlier >15-minute post-stress state.

These absolute local timings and memory values are diagnostic baselines, not
portable limits. Only same-process, same-ABI generated/reference Universal
ratios use the current conservative regression ceilings. Hosted history is
required before promoting HPy CPython or absolute resource values into release
budgets.

## Post-baseline ownership correction

The initial table exposed a contract mismatch: generated benchmark functions
accepted keywords while the handwritten `HPyFunc_O`/`HPyFunc_VARARGS`
references did not. The fixtures now declare matching positional-only
interfaces and the semantic oracle verifies keyword rejection. The first
ownership-proven backend optimization then borrows a direct live Name handle
where `HPy_GetAttr_s` or zero-argument `HPy_Call` only borrows its input.

The follow-up Universal run recorded 0.82× identity, 0.87× attribute, and 1.02×
call ratios. HPy CPython ABI recorded 1.00×, 1.03×, and 1.03× respectively.
Trace now reports exactly one API call and zero Dup/Close churn for generated
and reference attribute/call paths. Debug Mode, the full generated corpus in
the documented O0 stress profile, 179 emitter tests, and all 128 isolated
allocation/API fault selectors pass. Runtime ceilings for identity, attribute,
and call were tightened to 1.5×.

## Positional-varargs and borrowed-operand follow-up

The next ownership-proven slice replaces the keyword parser/tracker for two or
more required positional-only arguments with `HPyFunc_VARARGS`, then passes
direct live Name operands to borrowing binary and fixed sequence-builder APIs.
Side-effectful binary right operands retain an owned left value, preserving
Python evaluation order and lifetime semantics.

The follow-up generated/reference ratios were:

| Operation | HPy CPython ratio | HPy Universal ratio |
| --- | ---: | ---: |
| identity | 1.00× | 1.01× |
| arithmetic | 1.00× | 0.97× |
| container | 0.98× | 1.07× |
| attribute | 1.01× | 1.02× |
| call | 0.99× | 1.00× |
| exception | 1.01× | 0.98× |
| type create | 4.90× | 4.74× |
| type method | 6.59× | 6.19× |
| external C | 6.64× | 5.40× |

Classic Cython remains a standalone profile; its local values ranged from
17.434 ns for identity to 177.430 ns for the exception operation and are not a
denominator for either HPy column. Trace proves arithmetic/container now match
their handwritten references at 1/4 API calls with zero Dup/Close churn.
Generated Universal C is 33,703 bytes and its binary is 76,672 bytes versus a
76,080-byte reference. The isolated 4,930,017-byte/86,250-line type corpus
compiled in 2.367 seconds at `-O0` and 10.321 seconds at `-O3`, both below the
60-second liveness ceiling. Hosted history is still required before any local
absolute value becomes a release budget.

## Extension owner and initializer follow-up

Call-scoped extension-field owners and direct Name store values now remain
borrowed, type/module owners load only at their first actual use, and required
positional-only initializer slots bypass the keyword tracker. The final local
generated/reference ratios are 1.03×/1.02× for type creation and 1.02×/0.96×
for type methods in HPy CPython/HPy Universal respectively. Both Universal
ceilings are tightened to 1.5×.

Universal Trace records 3 generated versus 2 reference calls for construction
and 2.003 versus 2.002 for the method workload, with zero Dup/Close churn on
both generated paths. Construction retains one separate generated `__cinit__`
`AsStruct`; the handwritten reference receives the data pointer from `HPy_New`.
Generated C/binary size is 30,987/76,592 bytes versus the 76,080-byte reference
binary, and clean peak RSS is 36,012,032/35,962,880 bytes. The isolated
4,654,176-byte/81,349-line type corpus compiled in 1.449/5.190 seconds at
`-O0`/`-O3`. These remain local same-host measurements; hosted history is still
required for release-grade absolute budgets.

## Portable external-C literal follow-up

The external-C benchmark passes two representable integer constants to a
validated `long long` function. The generated backend now emits typed portable
C literals for that proven side-effect-free case; dynamic and non-portable
inputs retain checked HPy conversions.

The final same-ABI generated/reference ratios were 1.002× for HPy CPython and
0.990× for HPy Universal. Universal Trace matches the handwritten reference
at one result-conversion API call per iteration with zero Dup/Close churn, and
the Universal budget is tightened from 8.0× to 1.5×. The complete final
Universal ratio set remained green: identity 1.004×, arithmetic 0.978×,
container 1.004×, attribute 1.020×, call 0.995×, exception 1.004×, type
creation 1.020×, type method 0.945×, and external C 0.990×. Generated C
and binary sizes were 29,536 and 76,576 bytes; the reference binary was 76,080
bytes. Clean peak RSS was 35,831,808/35,946,496 bytes. These are local evidence,
not cross-host absolute budgets.
