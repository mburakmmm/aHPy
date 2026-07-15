# M8 focused coverage validation record

Date: 2026-07-15  
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`  
Status: deterministic focused Python coverage gate enabled

The gate uses only the standard-library tracer and code-object line tables.
It runs each feature family independently, accumulates line hits, and produces
stable JSON or Markdown. No timestamp, temporary path, hash-randomized order,
or third-party coverage version enters the report.

| Area | Python 3.11 | Python 3.14 | CI floor |
| --- | ---: | ---: | ---: |
| Universal backend | 72.61% | 71.65% | 71% |
| Cython frontend seam | 25.20% | 25.07% | 25% |
| aHPy quality tools | 40.57% | 40.62% | 35% |

The 352-test execution is split into 56 ownership-model, 48 Runtime API, 135
Universal emitter, 62 compiler-seam, and 51 quality-tool tests. All families
pass on both validated local interpreters. Four focused unit tests separately
verify nested executable-line discovery, area aggregation, threshold failure,
unknown-area rejection, and deterministic Markdown rendering.

```console
python3 Tools/ahpy/report_coverage.py \
    --fail-under backend=71 \
    --fail-under frontend_seam=25 \
    --fail-under quality_tools=35
```

The percentages cover Python execution only. The real HPy module, generated C,
native runtime, binary ABI, sanitizer, fault-injection, and subprocess oracles
remain separate mandatory gates and are not represented as traced Python lines.
