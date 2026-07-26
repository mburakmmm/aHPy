# M8 focused Universal backend coverage

Date: 2026-07-26

Status: local dual-interpreter gate green

The dependency-free focused coverage gate now traces 562 tests and reaches
100% of the executable Python lines in the three Universal backend
implementation modules:

- `Cython/Compiler/HPyModuleWriter.py`
- `Cython/Compiler/HandleModel.py`
- `Cython/Compiler/RuntimeAPI.py`

| Interpreter | Backend | Frontend seam | Quality tools |
| --- | ---: | ---: | ---: |
| CPython 3.11 | 9161/9161 (100.00%) | 15410/33908 (45.45%) | 2086/5014 (41.60%) |
| CPython 3.14.6 | 9058/9058 (100.00%) | 15517/34017 (45.62%) | 2082/5010 (41.56%) |

The interpreter-specific executable-line totals differ because Python bytecode
line tables differ; both independently satisfy the same CI floors:

```console
python Tools/ahpy/report_coverage.py \
    --fail-under backend=100 \
    --fail-under frontend_seam=45 \
    --fail-under quality_tools=41
```

The five traced families contain 65 ownership-model, 56 Runtime API, 236
Universal emitter, 62 compiler-seam, and 143 quality-tool tests; two
platform/tool availability skips are expected on macOS.

After the source refactors, the generated Universal corpus was also rebuilt
with the required `CFLAGS=-O0` profile and passed normal, HPy Trace, and HPy
Debug execution. The unbounded local default `-O3` trial was stopped after it
entered the already documented large-C Apple Clang optimizer bottleneck; it is
diagnostic and is not the required correctness/liveness profile.

The reporter derives executable lines from nested code objects, excludes only
ellipsis-only interface stubs, and installs a source-first finder for measured
modules so an in-tree stale extension cannot steal an import. Schema 2 JSON
and Markdown outputs carry exact missing lines and compact missing ranges.

This result is deliberately limited to Python-source coverage. Generated C
validity, native HPy semantics, Debug/Trace behavior, allocation failures,
sanitizers, binary boundaries, subprocesses, and portability remain separate
mandatory gates and are not converted into an inflated line percentage.
