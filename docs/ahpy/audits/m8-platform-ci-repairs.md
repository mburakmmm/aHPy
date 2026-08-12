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
4. portability smoke revalidates the manifest and runs six isolated stages,
   beginning with a handwritten public-HPy import and semantic oracle.
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

## Fixture-local MSVC serialization

The later full Cython run
[30439469712](https://github.com/mburakmmm/aHPy/actions/runs/30439469712)
at `b173e6f3797298723d8b5c325a68ad5d5aa6e577` showed that outer isolation was
necessary but not sufficient. Its isolated Windows C++/Python 3.11 job
[90542124435](https://github.com/mburakmmm/aHPy/actions/runs/30439469712/job/90542124435)
ran `memoryview_shared_utility` alone at outer `-j1`, but the fixture's own
`setup_with_sources.py build_ext -j3` launched three MSVC links and one again
failed with `LNK1158: cannot run 'rc.exe'`. Adjacent links used the same
compiler and SDK successfully, so this remains resource-compiler contention,
not an aHPy semantic or generated-code defect.

The second-stage repair changes all three
`memoryview_shared_utility.srctree` and all five
`shared_utility_module.srctree` build commands to `build_ext -j1`. The two
fixture trees remain excluded from the ordinary Windows four-worker pool and
run in their isolated outer `-j1` pass, eliminating both levels of link
concurrency. Other Cython fixtures retain explicit parallel-build coverage.
A quality contract locks all eight serial commands and rejects reintroduction
of fixture-local `-j3`. The real local Python 3.14 C-backend run passed all
three selected end-to-end trees in 21.04 seconds; replacement Windows hosted
confirmation is still required.

## Downstream benchmark reference and failure propagation repair

PR benchmark run
[30339567375](https://github.com/mburakmmm/aHPy/actions/runs/30339567375)
failed before producing its first CSV. The inherited Cython workflow compared
against `origin/3.0.x`, `origin/3.1.x`, and `origin/master`, but aHPy's `origin`
is the downstream repository and intentionally publishes only its integration
and topic branches. `git describe --long origin/3.0.x` therefore failed. The
loop was piped through `tee` without `pipefail`, hiding that first error until
the summary script received the literal unmatched
`benchmark_results_*.csv` spelling and raised `FileNotFoundError`.

Both regular and weekly workflows now fetch the exact release branches,
`master`, and tags from `https://github.com/cython/cython.git` into an
`upstream` remote and benchmark those refs against aHPy `HEAD`. Their pipelines
enable `pipefail`, summary rendering expands null-safe timing and size arrays
and rejects either missing set, and artifact upload names the actual CSV globs
with `if-no-files-found: error`. Expensive workflow push triggers are limited
to aHPy `main` and `ahpy/**` release branches; topic branches retain
pull-request validation without running a second push matrix. The benchmark
selector still skips its expensive body for unrelated PRs while publishing a
stable required context. Focused quality contracts lock the upstream refs,
irrelevant-change filter, pipeline propagation, CSV validation, artifact
policy, and downstream branch trigger policy.
`tests/ahpy/ci-policy.toml` additionally classifies every job in all ten
workflows exactly once; four regressions reject unknown workflows/jobs,
duplicate classifications or job-level YAML keys, failure-policy drift, and
branch-trigger drift. Benchmark and coverage workflows now retain stable
required aggregate contexts when lightweight selectors skip irrelevant
changes, and `.github/rulesets/production-branches.json` binds the five stable
aggregate contexts to pull-request-only, no-bypass protection for `main` and
`ahpy/**`; each required context is restricted to GitHub Actions App
integration ID `15368`. Local CPython 3.11 and 3.14 coverage runs pass all 601
tests. Policy implementation commit
`e791c8983bcb1a3c38aa932617a91ea976cb5c55` produced green required
aggregates for
[`aHPy required checks` job 90238576086](https://github.com/mburakmmm/aHPy/actions/runs/30347252766/job/90238576086),
[`benchmark required checks` job 90250254151](https://github.com/mburakmmm/aHPy/actions/runs/30347253289/job/90250254151),
[`coverage required checks` job 90245943934](https://github.com/mburakmmm/aHPy/actions/runs/30347253159/job/90245943934),
and
[`sanitizers-success` job 90246538721](https://github.com/mburakmmm/aHPy/actions/runs/30347253367/job/90246538721).
The aHPy workflow remained successful while the explicitly allowed HPy
development 3.14 and same-binary PyPy/GraalPy jobs failed, proving that those
early warnings do not poison the required aggregate.

The inherited regular benchmark serially ran all five Python interpreters in
one job; current upstream evidence shows successful instances taking roughly
three to four hours. The downstream workflow now preserves all interpreter,
revision, Limited API, size, and timing comparisons as five independent
fail-fast-disabled matrix entries. Each entry has an isolated ccache key,
uniquely named CSV/log artifacts, and a 90-minute bound. Hosted run
[`30347253289`](https://github.com/mburakmmm/aHPy/actions/runs/30347253289)
passed all five entries and the required aggregate: Python 3.14t took
32m23s, 3.12 took 42m00s, 3.13 took 43m11s, 3.10 took 1h00m25s, and 3.14 took
1h03m28s. This preserves the complete benchmark semantics while reducing the
hosted wall time from roughly three-to-four serial hours to about 64 minutes.

The same implementation HEAD's full Cython run exposed one mandatory,
interpreter-specific test-fixture defect in PyPy 3.9 job
[`90243188768`](https://github.com/mburakmmm/aHPy/actions/runs/30347253678/job/90243188768):
`SimpleNamespace(self=...)` conflicts with PyPy's named `self` receiver and
raised `TypeError` before exercising the backend. Commit `1b3805e30` assigns
the identical synthetic AST field after construction instead. The focused
fixture passes all 248 `TestHPyModuleWriter` tests under both local CPython and
PyPy; at that point the full five-context replacement run was still required
as PRD-0 same-HEAD exit evidence. The subsequent roadmap-only HEAD
`7ad48c495e9410ec1aa0ab28cdd2a7201282e991` has green
[`aHPy required checks` job 90262950998](https://github.com/mburakmmm/aHPy/actions/runs/30355000922/job/90262950998);
[`coverage required checks` job 90270294573](https://github.com/mburakmmm/aHPy/actions/runs/30355000919/job/90270294573)
and
[`sanitizers-success` job 90270728209](https://github.com/mburakmmm/aHPy/actions/runs/30355001070/job/90270728209)
and
[`benchmark required checks` job 90279175748](https://github.com/mburakmmm/aHPy/actions/runs/30355000934/job/90279175748)
are also green. Full Cython run `30355001166` reached a cold-cache capacity
limit in Ubuntu shared-utility C++ job
[`90261190485`](https://github.com/mburakmmm/aHPy/actions/runs/30355001166/job/90261190485):
tests were still compiling and passing when the 80-minute job timeout
cancelled the run, and ccache reported only 109 hits against 442 misses.
The replacement retains the full corpus while bounding non-Windows
shared-utility mode to four outer workers and assigning only that heavy lane a
120-minute fail-closed ceiling. Its focused contract test, full 153-test
quality suite, shell syntax, YAML parse, compileall, and diff checks pass
locally. Repair HEAD `8ed77677ee6bd69fdc93a81bdfe3e704ea7d924b`
has green
[`aHPy required checks` job 90283757405](https://github.com/mburakmmm/aHPy/actions/runs/30361153504/job/90283757405),
[`benchmark required checks` job 90296401321](https://github.com/mburakmmm/aHPy/actions/runs/30361153497/job/90296401321),
[`coverage required checks` job 90291908521](https://github.com/mburakmmm/aHPy/actions/runs/30361153526/job/90291908521),
and
[`sanitizers-success` job 90296760091](https://github.com/mburakmmm/aHPy/actions/runs/30361153809/job/90296760091).
The repaired
[shared-utility C++ job 90281110328](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90281110328)
passed in 14m39s, and
[PyPy 3.9 job 90288783333](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90288783333)
is green. The audit kept PRD-0's hosted gate open until full run
`30361153866` published a green replacement `ci-success`. That run completed
all 103 jobs successfully
and published
[`ci-success` job 90328870116](https://github.com/mburakmmm/aHPy/actions/runs/30361153866/job/90328870116),
closing the same-HEAD PRD-0 hosted evidence gate.

## Production branch ruleset

GitHub repository ruleset
[`19886870`](https://github.com/mburakmmm/aHPy/rules/19886870) was created from
the committed `.github/rulesets/production-branches.json` source. The live API
reports:

- enforcement `active`;
- no bypass actors and `current_user_can_bypass: never`;
- ref includes `refs/heads/main` and `refs/heads/ahpy/**`;
- deletion and non-fast-forward protection;
- pull requests with resolved review threads and zero required approvals for
  the current single-maintainer phase; and
- five up-to-date required contexts, all bound to GitHub Actions integration
  ID `15368`.

The branch-rules endpoint returns `deletion`, `non_fast_forward`,
`pull_request`, and `required_status_checks` for both existing `main` and the
non-existent probe `ahpy/3.2`, proving that the future release-branch pattern
is active rather than merely stored. After removing GitHub's response-only
empty `required_reviewers` field, the normalized live API object is byte-for-
byte JSON-equivalent to the committed ruleset source.
