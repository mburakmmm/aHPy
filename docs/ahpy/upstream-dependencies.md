# Upstream dependency and reproducer inventory

This inventory tracks external blockers without treating an unfiled draft as
an upstream issue or an early-warning failure as supported behavior. Publishing
a report is an external maintainer action; local preparation can make that
action reproducible but cannot create its URL.

| ID | Target | Current evidence | Upstream state | aHPy status |
| --- | --- | --- | --- | --- |
| `HPY-PY314-NEW` | `hpyproject/hpy` | Handwritten GC heap type and generated closure both fault in `HPy_New` on CPython 3.14.6 + HPy `b57a33c…`; CPython 3.11 + HPy 0.9 passes normal/Trace/Debug | General Python 3.13/3.14 tracking: [HPy #488](https://github.com/hpyproject/hpy/issues/488); exact crash report prepared, not filed | blocked early warning; not aHPy-generated-code proof |
| `HPY-PYPY-BRIDGE` | PyPy bundled HPy bridge / generated sequence boundary | Hosted job `102401673045` passes handwritten and generated positional/named keyword calls plus constant-only oracles and Fibonacci import, then captures 65 native frames after signal 11 in `fibonacci-semantics`; generated Fibonacci's second `HPy_Length` consumes a `range` result | Guarded report in `audits/prd5-pypy-bridge-upstream-report.md`; isolated public-HPy `range`/`HPy_Length` classification and filing authorization pending | unsupported early warning |
| `HPY-GRAALPY-LOADER` | GraalPy HPy/import integration | GraalPy 25.1.3 exposes neither `hpy.universal` nor a native `.hpy0` suffix; hosted job `101478712970` fails to discover the unchanged handwritten binary | Complete hosted evidence in `audits/prd5-graalpy-loader-upstream-report.md`; owner filing authorization pending | unsupported early warning |
| `HPY-PY315-BUILD` | HPy 0.9 / CPython 3.15 | HPy build fails under `-Werror` on `_POSIX_C_SOURCE` redefinition before aHPy executes; manual job `88897432348` retains environment evidence | Moving nightly signal; no issue filed | unsupported early warning |
| `HPY-BUFFER-CONSUMER` | public HPy API | No selected public buffer acquire/release consumer contract for typed memoryviews and bytes-buffer wrappers in HPy 0.9 | API/design gap; no project-specific issue URL | blocked source surface |
| `HPY-ITER-EXC-STATE` | public HPy API | Generic iterator-next and complete active-exception state are insufficient for the declared generator/handler surface | API/design gap; no project-specific issue URL | blocked source surface |

## Ready-to-file report

`audits/prd5-hpy-dev314-upstream-report.md` contains the exact title,
environment, handwritten/generated reproductions, expected/actual behavior,
stack and hosted link for `HPY-PY314-NEW`. The report must link rather than
duplicate HPy #488 and should ask whether the crash is covered by that general
tracking issue. Once filed, replace “prepared, not filed” with the immutable
issue URL in this inventory, the PRD-5 audit, validation matrix and production
roadmap.

## Prepared alternate-interpreter reports

`audits/prd5-pypy-bridge-upstream-report.md` and
`audits/prd5-graalpy-loader-upstream-report.md` contain exact pinned target
identities, reproduction commands, expected behavior, hosted evidence, and
filing guards. Run `34331675408` proved the handwritten no-argument and
`HPyFunc_KEYWORDS` paths plus constant-only and minimal generated keyword
modules on PyPy, reduced its first
failure to signal 11 while executing the small generated Fibonacci function,
and retained a bounded 65-frame native trace rooted at PyPy's `HPy_Length`
implementation. Because both handwritten positional/no-keyword and named-call
stages and both generated keyword-identity calls pass, the next artifact must
isolate `HPy_Length` on the `range` result before filing so the issue is routed
to the correct tracker.
Run `34030366000` reconfirmed GraalPy's loader gap with an unchanged handwritten
binary and complete suffix/loader evidence. Do not publish either report
without explicit owner authorization.

## Routing rules

1. First prove the failure with a supported/early-warning environment and a
   minimal aHPy source.
2. Build a handwritten public-HPy reproducer before assigning an HPy runtime or
   API defect.
3. Reproduce without Universal mode before assigning a frontend-neutral issue
   to Cython.
4. Keep PyPy/GraalPy signals outside support until their native bridge/loader
   can execute the unchanged binary and the declared matrix is green.
5. Never publish vulnerability details through a public issue; follow
   `SECURITY.md` and coordinated disclosure.
