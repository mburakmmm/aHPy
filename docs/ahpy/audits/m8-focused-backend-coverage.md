# M8 focused Universal backend coverage

Date: 2026-08-03

Status: local dual-interpreter gate green

The dependency-free focused coverage gate now traces 944 tests and reaches
100% of the executable Python lines in the three Universal backend
implementation modules:

- `Cython/Compiler/HPyModuleWriter.py`
- `Cython/Compiler/HandleModel.py`
- `Cython/Compiler/RuntimeAPI.py`

| Interpreter | Backend | Frontend seam | Quality tools |
| --- | ---: | ---: | ---: |
| CPython 3.11 | 9565/9565 (100.00%) | 18278/34275 (53.33%) | 8694/8694 (100.00%) |
| CPython 3.14.2 | 9451/9451 (100.00%) | 18377/34380 (53.45%) | 8701/8701 (100.00%) |

The interpreter-specific executable-line totals differ because Python bytecode
line tables differ; both independently satisfy the same CI floors:

```console
python Tools/ahpy/report_coverage.py \
    --fail-under backend=100 \
    --fail-under frontend_seam=45 \
    --fail-under quality_tools=100
```

The five traced families contain 65 ownership-model, 56 Runtime API, 255
Universal emitter, 62 compiler-seam, and 506 quality-tool tests; two
platform/tool availability skips are expected on macOS.

After the source refactors, the generated Universal corpus was also rebuilt
with the required `CFLAGS=-O0` profile and passed normal, HPy Trace, and HPy
Debug execution. The unbounded local default `-O3` trial was stopped after it
entered the already documented large-C Apple Clang optimizer bottleneck; it is
diagnostic and is not the required correctness/liveness profile.

The reporter derives executable lines from nested code objects, excludes only
ellipsis-only interface stubs and behavior-free top-level repository-import or
``__main__`` dispatch wiring, and installs a source-first finder for measured
modules so an in-tree stale extension cannot steal an import. Every imported
operation and ``main()`` body remains measured; subprocess tests separately
validate entrypoint wiring. Schema 2 JSON and Markdown outputs carry exact
missing lines and compact missing ranges.

This result is deliberately limited to Python-source coverage. Generated C
validity, native HPy semantics, Debug/Trace behavior, allocation failures,
sanitizers, binary boundaries, subprocesses, and portability remain separate
mandatory gates and are not converted into an inflated line percentage.
