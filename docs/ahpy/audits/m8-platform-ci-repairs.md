# M8 hosted platform CI repair audit

Status: required hosted platform/compiler matrix green; alternate-interpreter
early warnings remain unsupported.

The first broad hosted run exposed four independent infrastructure boundaries,
not a reason to weaken Universal semantics:

- the doctor symlink assertion ran after its temporary directory had removed
  the symlink, with macOS `/var` path normalization hiding the test defect;
- MSVC emitted `.hpy0.lib` and `.hpy0.exp` sidecars that a broad glob confused
  with the loadable `.hpy0.pyd`;
- `actions/setup-python` reported `universal2` on the ARM64 sanitizer runner,
  while native objects and a signed Python launcher prevented a correct early
  Apple ASan runtime;
- PyPy failed with a signal in an opaque all-in-one smoke process and GraalPy
  was rejected before execution by an unconditional CPython
  `hpy.universal` import.

The repairs keep the test strength:

1. the symlink target remains alive while `doctor.main()` and `realpath()` are
   compared;
2. one shared artifact helper matches the complete native `.hpy0.so` or
   `.hpy0.pyd` suffix, excluding linker sidecars across integration, fuzz,
   fault, and portability tools. Generated runtime checks execute from
   temporary scripts, retaining the full semantic corpus without exceeding
   the Windows `CreateProcess` command-line limit. The non-setuptools direct
   builder uses `vswhere.exe` and `vcvarsall.bat` when `cl.exe` is not already
   available, then invokes the compiler and linker commands itself;
3. macOS forces one native architecture and uses a temporary
   ASan-linked `Py_BytesMain` launcher. A preload probe rejects the lane unless
   the compiler-selected runtime is already loaded before extension import;
4. portability smoke revalidates the manifest and runs four isolated stages.
   Python-stub and native HPy import paths are explicit, while every tested
   `.hpy0` byte remains unchanged. PyPy's bundled `hpy.universal` is its native
   HPy bridge and therefore keeps using the unchanged loader stubs. GraalPy
   25.1.3 exposes neither that bridge nor a native `.hpy0` import suffix.
5. hosted Ubuntu GCC 13 exceeded both 60- and 180-second O3 trials while O0
   remained near 5 seconds. O0 is the required C-validity/liveness gate and O3
   is a bounded diagnostic; relative generated/reference budgets remain
   unchanged. A skipped stress step no longer produces a misleading
   missing-artifact failure. The hosted stable, pinned-development, and
   portability semantic builds now explicitly use O0 (`/Od` on MSVC), while
   direct-build and performance checks keep independent explicit optimization
   profiles.

## Reviewed hosted evidence

Push run [29685285138](https://github.com/mburakmmm/aHPy/actions/runs/29685285138)
completed successfully for commit
`02d9f8cdd8386eaf277e89dc876fcee9f75e4054`. All mandatory jobs started from
clean checkouts. The stable evidence is:

| Target | Job | Duration | Runner image | Compiler |
|---|---:|---:|---|---|
| Linux x64 | [GCC 88188395901](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395901) | 41 s | `ubuntu-24.04` `20260714.240.1` | GCC 13.3.0 |
| Linux x64 | [Clang 88188395939](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395939) | 47 s | `ubuntu-24.04` `20260714.240.1` | Clang 18.1.3 |
| Linux ARM64 | [GCC 88188395936](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395936) | 56 s | `ubuntu-24.04-arm` `20260714.61.1` | GCC 13.3.0 |
| macOS Intel | [Clang 88188395931](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395931) | 58 s | `macos-15` `20260715.0340.1` | Apple Clang/LLVM 17.0.0 |
| macOS ARM64 | [Clang 88188395966](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395966) | 31 s | `macos-15-arm64` `20260715.0234.1` | Apple Clang/LLVM 17.0.0 |
| Windows x64 | [MSVC 88188395905](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395905) | 65 s | `windows-2025-vs2026` `20260714.173.1` | MSVC 14.44 / VS 18.7.11925.98 |

The same run also passed Linux/macOS sanitizers, pinned HPy development on
CPython 3.11, and the 10m23s
[compiler-and-quality job](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395921),
including coverage, performance, fault injection, bounded stress, both fuzz
oracles, reproducibility, C/C++ semantics, packaging, and external build
systems. The portability builder
[job 88188395887](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188395887)
recorded CPython 3.11.15. Its downloaded manifest was independently rehashed:

- `bootstrap_answer.hpy0.so`: 3,101,256 bytes,
  `2630e3aef4f00d277742b0b331a01b7916a2f04759f3a77c4cd5f967a75dcaac`;
- `bootstrap_types.hpy0.so`: 2,432,936 bytes,
  `cd0a86cd37c89f83d237300123cfb46faf3841eba69711fbc0cd1776d8ba0655`.

Local evidence on macOS ARM64 / CPython 3.11 / HPy 0.9 includes 127 quality
tests, generated normal/Trace/Debug execution, a staged CPython portability
artifact, and the full ASan/UBSan generated corpus. The six stable hosted
platform/compiler entries are now promoted for the CPython 3.11/HPy 0.9
baseline. Alternate interpreters remain outside that claim.

The same-binary early-warning evidence remains intentionally red. PyPy job
[`88188460273`](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188460273)
reached the first import through its bundled `hpy.universal` and
terminated with signal 11. An experimental native-only staging attempt in job
`88185919115` proved that PyPy does not install a `.hpy0` import hook, failing
cleanly with `ModuleNotFoundError`; the bridge path is therefore restored.
GraalPy job
[`88188460282`](https://github.com/mburakmmm/aHPy/actions/runs/29685285138/job/88188460282)
likewise reports `ModuleNotFoundError` with the unchanged binary. Neither
interpreter is listed as supported.

Two hosted retries also exposed a cross-platform HPy 0.9 failure-path race:
successful attribute deletions during non-memory module rollback could clear
the active import exception, yielding `SystemError` in Linux sanitizer job
`88126392914` and Windows Debug job `88186685203`. The backend now performs
attribute rollback only for `MemoryError`, which HPy 0.9 can reconstruct after
cleanup; arbitrary exceptions retain their original identity and traceback.

## Current-head classic regression repairs

General Cython PR run
[29900694989](https://github.com/mburakmmm/aHPy/actions/runs/29900694989)
first exposed that three executable Universal-only aHPy fixtures were also
being discovered by GraalPy's generic classic-C-API test lane. The classic
output reached GraalPy 25.1.3's unimplemented
`PyUnicode_DecodeUnicodeEscape` before the Universal contract could run.
`graal_bugs.txt` now excludes only `bootstrap_answer`, `bootstrap_types`, and
`fault_injection` on GraalPy; compile-only `benchmark_generated` and
`retry_case` remain in the generic C/C++ suite, and the dedicated Universal
workflow retains the executable semantics.

The same broad run's Windows C++/Python 3.11 job
[88866582910](https://github.com/mburakmmm/aHPy/actions/runs/29900694989/job/88866582910)
compiled 1,418 C++ test modules before one concurrent end-to-end package link
failed with `LNK1158: cannot run 'rc.exe'`. The runner had successfully used
the same Windows SDK helper in adjacent links, the run's early Windows C++ job
was green, and the previous full Windows C++ job was green. This is the
intermittent parallel-link failure already documented beside the Windows
bootstrap build policy, not generated aHPy behavior. The full test runner had
nevertheless still launched seven independent MSVC test trees; Windows now
bounds that outer parallelism at four while retaining GraalPy's independent
two-worker policy.

Replacement run
[29905498043](https://github.com/mburakmmm/aHPy/actions/runs/29905498043)
proved that the outer cap alone was insufficient. Windows C++/Python 3.9 job
[88881761829](https://github.com/mburakmmm/aHPy/actions/runs/29905498043/job/88881761829)
compiled all 1,418 C++ modules, then the `shared_utility_module` end-to-end
test launched its own `build_ext -j3` while other outer workers were active;
one of those three links again received `LNK1158`. Windows therefore excludes
the two `tag:shared_utility` trees from the four-worker pass and executes them
in a separate one-tree pass. Their internal `-j3` behavior remains tested,
but no unrelated outer build competes for `rc.exe`. A quality contract locks
the separation, Windows limit, and GraalPy limit.

Replacement hosted evidence for the stronger fix is now complete. At commit
`d0026d83b3880663c1aff6c69accbac93556f13c`, push run
[29912142526](https://github.com/mburakmmm/aHPy/actions/runs/29912142526)
(attempt 2) and PR run
[29912145346](https://github.com/mburakmmm/aHPy/actions/runs/29912145346)
each passed all 103 jobs, including the final `ci-success` aggregators.
Coverage run
[29912145042](https://github.com/mburakmmm/aHPy/actions/runs/29912145042)
passed both coverage jobs. The PR early Windows C job
[88897719146](https://github.com/mburakmmm/aHPy/actions/runs/29912145346/job/88897719146)
and C++ job
[88897719306](https://github.com/mburakmmm/aHPy/actions/runs/29912145346/job/88897719306)
excluded `tag:shared_utility` from the outer four-worker pass, then ran the tag
at outer `-j1`; both `memoryview_shared_utility` and
`shared_utility_module` completed successfully with their internal parallel
builds and no `LNK1158`.
