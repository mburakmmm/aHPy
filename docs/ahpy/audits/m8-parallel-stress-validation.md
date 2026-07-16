# M8 bounded parallel HPy stress validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
HPy: `0.9.0` Universal ABI  
Host: Apple Silicon, CPython 3.11.15  
Status: five-round local acceptance passed; one-round CI recurrence enabled

## Reason for the gate

An early ad-hoc run of the complete fault-injection gate alongside three HPy
build/execution tools produced one import `SystemError` without an active
exception. It did not reproduce sequentially. A later attempt exposed a
separate, concrete orchestration defect: cancelling the parent tool cell did
not terminate two generated-corpus process trees or their Apple Clang children.
Two simultaneous `bootstrap_types.c -O3` compilations then consumed CPU for
more than five minutes. This was neither acceptable cleanup nor valid evidence
of a backend hang.

`Tools/ahpy/stress_parallel_hpy.py` replaces that orchestration. It starts the
fault, generated corpus, setuptools integration, and fixed fuzz commands in
separate process groups and gives each a unique temporary root. stdout and
stderr stream directly to separate files. The schema-versioned JSON records
their SHA-256 digests, sizes, tails, exact argv, status, exit/signal, duration,
timeout, and round. On timeout or interruption the entire process group is
terminated, escalated after a grace period, and reaped.

Nine focused tests cover deterministic command construction, unique names,
preserved optimization flags, success, start failure, nonzero exit, retained
stdout/stderr, timeout, descendant cleanup, and multi-round JSON reporting.
The descendant positive control starts a process that would write a marker
after its parent timeout; no marker appears after recursive cleanup.

## Stress profile

A clean normal run showed Apple Clang spending more than 4 minutes 36 seconds
of CPU optimizing the generated type corpus at `-O3`. Concurrent O3 builds are
therefore a compiler-cost stress rather than a useful HPy concurrency signal.
The bounded runner appends `-O0 -g0` (`/Od` on MSVC) after ordinary build flags.
This changes native optimization only; all generated source, HPy API calls,
normal/Debug semantic programs, fault boundaries, ABI audits, wheel install,
and Python oracles remain identical. Normal and release jobs retain their
ordinary optimization profile.

## Five-round acceptance result

Command:

```console
.venv-hpy09/bin/python Tools/ahpy/stress_parallel_hpy.py \
    --python .venv-hpy09/bin/python \
    --rounds 5 \
    --fuzz-cases 48 \
    --native-optimization 0 \
    --timeout-seconds 600 \
    --output /tmp/ahpy-parallel-five-rounds.json
```

| Round | Fault | Generated | Setuptools | Fuzz |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13.87 s | 10.40 s | 5.37 s | 7.28 s |
| 2 | 14.17 s | 11.42 s | 5.31 s | 8.04 s |
| 3 | 15.83 s | 12.09 s | 5.83 s | 8.53 s |
| 4 | 17.33 s | 13.81 s | 7.04 s | 10.02 s |
| 5 | 15.04 s | 12.23 s | 6.17 s | 9.08 s |

All twenty child commands exited zero with no timeout. All 640 isolated fault
selectors passed in normal/Debug mode, as did five generated corpora, five
wheel builds/installations, and five complete 48-case fuzz oracles. The exact
historical `SystemError` did not reproduce. A subsequent ordinary sequential
128-case fault run also passed.

The event is therefore classified as a non-reproduced result from unsafe
ad-hoc orchestration, with process-tree leakage and native optimization
contention proven as real harness defects. It is not classified as a fixed
backend defect because no repeatable backend failure was isolated. The bounded
one-round CI gate preserves recurrence evidence without weakening the separate
sequential and release-profile gates.

After the five rounds, the ordinary sequential 128-case fault gate passed. A
separate normal generated-corpus retry entered Apple Clang optimization of
`bootstrap_types.c` and continued consuming CPU beyond 15 minutes without an
error or second process tree; it was deliberately terminated and reaped rather
than reported green. The same generated corpus had already passed all five O0
stress rounds and the normal profile was green before this tooling-only change,
so this does not contradict the concurrency result. It is recorded as an open
M9 compile-time/footprint investigation and not concealed as a successful
post-stress release-profile run.
