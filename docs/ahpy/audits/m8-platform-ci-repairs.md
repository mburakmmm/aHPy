# M8 hosted platform CI repair audit

Status: local regressions and macOS ARM64 sanitizer gate green; hosted rerun
pending.

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

Local evidence on macOS ARM64 / CPython 3.11 / HPy 0.9 includes 127 quality
tests, generated normal/Trace/Debug execution, a staged CPython portability
artifact, and the full ASan/UBSan generated corpus. No hosted platform or
alternate interpreter is promoted until the replacement GitHub run is green
and its exact URLs are recorded.

The same-binary early-warning evidence remains intentionally red. PyPy job
`88139862401` reached the first import through its bundled `hpy.universal` and
terminated with signal 11. An experimental native-only staging attempt in job
`88185919115` proved that PyPy does not install a `.hpy0` import hook, failing
cleanly with `ModuleNotFoundError`; the bridge path is therefore restored.
GraalPy job `88185919098` likewise reports `ModuleNotFoundError` with the
unchanged binary. Neither interpreter is listed as supported.

Two hosted retries also exposed a cross-platform HPy 0.9 failure-path race:
successful attribute deletions during non-memory module rollback could clear
the active import exception, yielding `SystemError` in Linux sanitizer job
`88126392914` and Windows Debug job `88186685203`. The backend now performs
attribute rollback only for `MemoryError`, which HPy 0.9 can reconstruct after
cleanup; arbitrary exceptions retain their original identity and traceback.
