# M8 Universal HPy performance validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
HPy: `0.9.0` Universal ABI  
Status: relative regression budgets and CI history enabled

The gate builds `tests/ahpy/benchmark_generated.pyx` through the strict aHPy
backend and builds `tests/ahpy/benchmark_reference.c` as the equivalent
handwritten public-HPy module. Both generated source and undefined binary
imports are audited. Their six operation families have identical semantic
checks and pass a separate HPy Debug `LeakDetector` run before timing results
are accepted.

Runtime measurements use 100,000 calls, two warmups, and seven alternating
repeats per module and operation. The median generated/reference ratio is the
portable regression signal; absolute nanoseconds and every raw sample remain
in the JSON only for diagnosis. The initial Apple Silicon runs established the
following observed envelope and conservative CI budget:

| Operation | Three-run observed range | Maximum ratio |
| --- | ---: | ---: |
| Identity/call wrapper | 4.73–5.14× | 6.50× |
| Arithmetic | 4.11–4.37× | 5.50× |
| List construction | 3.31–4.10× | 5.25× |
| Attribute read | 2.24–2.78× | 3.50× |
| Nested zero-argument call | 1.59–1.85× | 2.50× |
| Raised/caught exception | 0.99–1.07× | 1.50× |

The first recorded generated C file was 25,523 bytes and the generated binary
was 74,896 bytes versus 73,936 bytes for the handwritten reference, a 1.013×
binary ratio. The versioned footprint ceilings are 750,000 generated-C bytes,
2,000,000 generated-binary bytes, and a 20× reference-binary ratio. These
ceilings catch accidental explosions; they do not claim that code-size work is
finished.

The `compiler-and-quality` workflow writes
`performance-results/benchmark.json` and uploads it as
`ahpy-performance-<run-id>-<attempt>`. This yields immutable per-run history
without treating timing from unlike hosts as directly comparable. The report
contains schema version, UTC timestamp, exact Python/HPy/platform/compiler
identity, build durations, all samples, medians, ratios, footprint, budget
source, Debug status, and any violations.

Ubuntu GCC 13 reached both 60- and 180-second `-O3` ceilings while `-O0`
completed near 5 seconds. O0 is therefore the required generated-C validity
and native-compiler liveness gate. The O3 attempt remains capped at 60 seconds
and recorded as a diagnostic; its absolute cross-host duration is not a
backend performance budget.

```console
.venv-hpy09/bin/python Tools/ahpy/benchmark_hpy.py \
    --python .venv-hpy09/bin/python \
    --output /tmp/ahpy-benchmark.json
```
