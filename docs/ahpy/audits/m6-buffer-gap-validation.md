# M6 buffer/memoryview HPy 0.9 gap validation

Date: 2026-07-16
Status: producer planned; consumer diagnose-only gate implemented

The installed HPy 0.9 headers expose `HPy_buffer` and producer slots but no
public consumer acquisition/release function. A focused regression compiles a
`double[:]` argument in Universal mode. Declaration analysis emits exactly one
actionable HPy diagnostic and the HPy-only early abort prevents the previously
observed five unrelated `View.MemoryView` GIL errors. No C file is emitted.

ADR 0008 records the owned exporter handle, auxiliary-storage lifetime,
rollback, idempotent release, and enablement tests. Producer emission and every
typed-memoryview operation remain open; this record makes no support claim.

The same audit exposed an older class-boundary regression in `Optimize.py`:
the HPy early-builtin filter had captured the base transform's helper and
handler methods, causing CPython pipelines to raise an `AttributeError`.
Restoring those methods to `EarlyReplaceBuiltinCalls` and leaving only the HPy
overrides in the subclass returns the focused CPython oracle to 38/38 passing
C/C++ tests. A structural unit test now protects the class boundary.

The post-fix focused suites pass 340 compiler tests and 70 quality-tool tests;
coverage traces 410 tests at 73.83% backend, 27.86% frontend seam, and 40.62%
quality tools. The generated Universal corpus remains green in normal, Trace,
and Debug modes.
