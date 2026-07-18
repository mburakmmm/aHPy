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
   fault, and portability tools;
3. macOS forces one native architecture and uses a temporary
   ASan-linked `Py_BytesMain` launcher. A preload probe rejects the lane unless
   the compiler-selected runtime is already loaded before extension import;
4. portability smoke revalidates the manifest and runs four isolated stages.
   Python-stub and native HPy import paths are explicit, while every tested
   `.hpy0` byte remains unchanged.

Local evidence on macOS ARM64 / CPython 3.11 / HPy 0.9 includes 122 quality
tests, generated normal/Trace/Debug execution, a staged CPython portability
artifact, and the full ASan/UBSan generated corpus. No hosted platform or
alternate interpreter is promoted until the replacement GitHub run is green
and its exact URLs are recorded.
