# Upstream dependency and reproducer inventory

This inventory tracks external blockers without treating an unfiled draft as
an upstream issue or an early-warning failure as supported behavior. Publishing
a report is an external maintainer action; local preparation can make that
action reproducible but cannot create its URL.

| ID | Target | Current evidence | Upstream state | aHPy status |
| --- | --- | --- | --- | --- |
| `HPY-PY314-NEW` | `hpyproject/hpy` | Handwritten GC heap type and generated closure both fault in `HPy_New` on CPython 3.14.6 + HPy `b57a33c…`; CPython 3.11 + HPy 0.9 passes normal/Trace/Debug | General Python 3.13/3.14 tracking: [HPy #488](https://github.com/hpyproject/hpy/issues/488); exact crash report prepared, not filed | blocked early warning; not aHPy-generated-code proof |
| `HPY-PYPY-BRIDGE` | PyPy bundled HPy bridge | Same CPython-built `.hpy0` reaches `hpy.universal` then exits by signal during first import in hosted job `90501653601`; the next artifact runs a handwritten HPy oracle before generated modules | Minimal report prepared in `audits/prd5-pypy-bridge-upstream-report.md`; hosted handwritten confirmation and filing pending | unsupported early warning |
| `HPY-GRAALPY-LOADER` | GraalPy HPy/import integration | GraalPy 25.1.3 exposes neither `hpy.universal` nor a native `.hpy0` suffix; hosted job `90501653614` fails before module semantics; the next artifact begins with a handwritten HPy oracle | Minimal report prepared in `audits/prd5-graalpy-loader-upstream-report.md`; hosted loader reconfirmation and filing pending | unsupported early warning |
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
identities, reproduction commands, expected behavior, existing hosted evidence,
and filing guards. The portability artifact now executes
`tests/ahpy/minimal_universal.c` before either generated corpus, separating the
runtime bridge/loader boundary from the Cython frontend. These two drafts are
not ready to publish until a new hosted run records the handwritten binary's
digest and exact first-stage result in the unconditionally uploaded
target-specific JSON report.

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
