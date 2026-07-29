# M8 focused Universal backend coverage

Date: 2026-07-29

Status: local dual-interpreter gate green

The dependency-free focused coverage gate now traces 606 tests and reaches
100% of the executable Python lines in the three Universal backend
implementation modules:

- `Cython/Compiler/HPyModuleWriter.py`
- `Cython/Compiler/HandleModel.py`
- `Cython/Compiler/RuntimeAPI.py`

| Interpreter | Backend | Frontend seam | Quality tools |
| --- | ---: | ---: | ---: |
| CPython 3.11 | 9408/9408 (100.00%) | 15576/34007 (45.80%) | 2326/5377 (43.26%) |
| CPython 3.14.6 | 9295/9295 (100.00%) | 15673/34113 (45.94%) | 2322/5373 (43.22%) |

The interpreter-specific executable-line totals differ because Python bytecode
line tables differ; both independently satisfy the same CI floors:

```console
python Tools/ahpy/report_coverage.py \
    --fail-under backend=100 \
    --fail-under frontend_seam=45 \
    --fail-under quality_tools=41
```

The five traced families contain 65 ownership-model, 56 Runtime API, 249
Universal emitter, 62 compiler-seam, and 174 quality-tool tests; two
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
