# Backend-neutral upstream seam plan

Status: implementation sliced locally; maintainer discussion and upstream PRs
not yet opened

Last updated: 2026-08-12

This plan separates changes that can stand on their own in Cython from the
aHPy/HPy policy that must remain downstream. It is not evidence that upstream
maintainers have accepted the design.

## Dependency direction

The required direction is:

```text
backend integration -> public Cython seam -> compiler/build pipeline
```

Cython core must never import `ahpy_*`, the `aHPy-compiler` distribution, or a
backend's packaging dependency. The build frontend now exposes
`Cython.Build.register_runtime_backend_build_hook(name, callable)`. A backend
integration registers one idempotent preparation callable; `cythonize()` calls
it only for the selected backend before compilation options are normalized.
Duplicate registration of the same callable is harmless, while competing
callables, unknown backends, and non-callables fail closed.

`ahpy_hpy_compat` owns the HPy 0.9 loader-template workaround and registers it
for `hpy-universal`. Installed frontend wheels also publish exactly one
`cython.runtime_backend_build_hooks` entry point, so a plain installed
`Cython.Build.cythonize()` call discovers the integration without requiring a
user import. Duplicate installed providers and loading failures are rejected.
Thus `Cython/Build/Dependencies.py` contains no aHPy import or HPy loader
knowledge. CPython builds execute no HPy hook.

## Proposed independent upstream changes

Each slice must carry its own CPython regression tests and must be reviewable
without accepting Universal HPy support.

1. **Runtime backend option validation.** Introduce a validated module-wide
   runtime-backend identity in compilation options and preserve `cpython` as
   the default. No HPy emitter is part of this slice.
2. **Build preparation registry.** Add the callable registration and installed
   entry-point discovery seam exported by `Cython.Build`, with
   idempotence/conflict/invalid-input/duplicate-provider/load-failure tests. No
   backend package is named by core and an empty registry is behaviorally inert.
3. **Context-owned Runtime API service.** Attach an immutable runtime service
   to each compilation context instead of mutable global backend state. Begin
   with CPython behavior only.
4. **Typed operation contracts.** Move genuinely runtime-dependent object,
   call, container, conversion, module and type operations behind typed
   contracts in small operation-family patches; preserve node-owned syntax
   structure.
5. **Ownership-aware reference seam.** Introduce explicit owned/borrowed/moved
   transitions without changing CPython reference output, then add alternate
   handle implementations separately.
6. **Backend-specific module emitter registration.** Allow a complete module
   emitter to be selected by runtime capability while retaining the existing
   CPython writer as the default and oracle.

Slices 1–2 are the smallest maintainer-discussion starting point. Slices 3–6
need prior agreement on naming and long-term compiler architecture; they must
not be presented as one monolithic HPy patch.

## Downstream-only policy and implementation

The following remain outside neutral upstream patches unless maintainers ask
otherwise:

- HPy 0.9 version pins and the Setuptools 83 loader compatibility rewrite;
- the strict aHPy support matrix and source-family diagnostics;
- `aHPy-compiler` package identity, PEP 517 backend, release policy and
  provenance fields;
- HPy-specific generated-C/binary audits, Debug/Trace gates, fault injection,
  pilots and performance budgets; and
- claims about Universal ABI portability or standardized wheel tags.

## Required evidence before opening a PR

- `Cython.Build` imports successfully without any `ahpy_*` module loaded; a
  clean installed wheel then discovers exactly one HPy Universal provider.
- Default and explicit CPython `cythonize()` output is unchanged.
- The neutral hook registry covers identical registration, conflicting
  registration, unknown backend, non-callable hook and backend isolation.
- The real aHPy Setuptools 83 build passes normal/Trace/Debug, source/binary
  audits and wheel installation through the registered hook.
- Full upstream Cython tests applicable to the touched seam and the aHPy
  compiler/quality matrices are green on the same commit.
- The proposed PR description explicitly says that the seam does not add HPy
  support or make a portability claim.

## Maintainer discussion questions

1. Should build preparation be a callable registry in `Cython.Build`, an
   extension-object protocol, or a compiler-context service?
2. Is `runtime_backend` acceptable terminology, or should the first neutral
   slice use a less ABI-specific name?
3. Which typed operation family is small enough to validate the Runtime API
   direction without committing Cython to the full aHPy architecture?
4. Which CPython code-generation baselines should be byte-compared in CI for
   every neutral refactor?

Answers and links belong in the append-only upstream/rebase records; local
implementation must not be relabeled as upstream acceptance.
