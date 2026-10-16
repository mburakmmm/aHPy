# NOX-side aHPy integration TODO

This document is the implementation queue owned by
[`mburakmmm/nox-lang`](https://github.com/mburakmmm/nox-lang) for consuming
packages produced by aHPy.

> **Ownership boundary:** this file is planning material only. aHPy agents must
> not implement, commit, or push any NOX source change. Every checkbox below is
> intentionally open and must be completed in the NOX repository by its owner.

The supported direction is **aHPy-generated Universal HPy extension -> NOX**.
Loading NOX modules from Python, generating Python packages from NOX, and a
general NOX/Python bridge are explicitly outside this plan.

## Evidence baseline

- [ ] Reproduce and retain a minimal cross-repository fixture from exact aHPy
      and NOX commits before changing either contract.
- [ ] Record the installed/runtime NOX version separately from the analyzed
      repository commit and reject mixed-version evidence.
- [ ] Preserve the current positive QBE proof: an aHPy `.hpy0` module can be
      opened and can execute a module function, an external-C-backed function,
      an extension-type constructor, a method, and an identity operation.
- [ ] Turn the current LLVM failure into a minimal regression. The observed
      generated IR compares the `i64` result of `nox_hpy_take_error` as `i32`
      (`%t7 defined with type i64 but expected i32`).
- [ ] Audit the published HPy documentation against the repository before
      claiming CPython compatibility, exception barriers, or source paths that
      do not exist.

## N0 - Freeze the NOX HPy host contract

- [ ] Publish a versioned, machine-readable NOX HPy host profile.
- [ ] Declare the supported HPy version, Universal ABI level, context layout,
      required symbols, calling convention, integer/pointer widths, and
      platform triples.
- [ ] Generate or validate the HPy context declarations from one authoritative
      source so QBE and LLVM cannot drift.
- [ ] Expose a capability/version query that package tooling can check before
      loading an artifact.
- [ ] Reject an incompatible manifest, ABI version, target, or capability set
      with an actionable diagnostic before dynamic loading.
- [ ] Define whether one process may host multiple module contexts and how
      module state is isolated between NOX runtimes.

### N0 exit gate

- [ ] The same checked-in contract drives the loader, both native backends,
      documentation, and conformance tests.
- [ ] A deliberately incompatible aHPy package is rejected without executing
      its initialization function.

## N1 - Repair and harden the existing HPy bridge

- [ ] Fix the LLVM error-state width/type mismatch without weakening QBE.
- [ ] Add QBE and LLVM golden tests for every HPy bridge function signature.
- [ ] Define one error-transfer representation across generated IR, the runtime
      bridge, and NNI declarations.
- [ ] Prove null handles, integer zero, booleans, signed values, pointer-sized
      values, and error sentinels on 32- and 64-bit targets where supported.
- [ ] Add success, native failure, HPy exception, malformed module, missing
      symbol, and double-close regressions.
- [ ] Remove stale or unreachable compatibility code, or mark it explicitly as
      unsupported instead of documenting it as implemented.
- [ ] Replace conditional HPy test skips with a pinned, reproducible test
      dependency and a visible unavailable/failure result.

### N1 exit gate

- [ ] The same minimal aHPy fixture passes through QBE and LLVM with equivalent
      values and equivalent surfaced errors.
- [ ] Sanitizer/debug runs show no bridge-originated invalid access, leak,
      double close, or use-after-close.

## N2 - Add package-relative, policy-controlled loading

- [ ] Extend `nox.json` or introduce a versioned companion manifest for native
      HPy artifacts; do not infer package identity from a caller-provided
      arbitrary path.
- [ ] Resolve the selected artifact relative to the installed dependency root,
      executable bundle, or managed cache rather than the current directory.
- [ ] Define platform selection for at least macOS ARM64/x86-64, Linux
      ARM64/x86-64, and Windows x86-64, while rejecting undeclared targets.
- [ ] Validate normalized paths, package boundaries, file kind, declared hash,
      size limits, duplicate entries, and symlink/traversal behavior before
      loading.
- [ ] Define deterministic precedence when both source and prebuilt artifacts
      exist.
- [ ] Stage or copy required native artifacts into the executable/package
      output without losing provenance or executable-relative discoverability.
- [ ] Keep direct arbitrary-library loading as an explicitly unsafe developer
      feature, separate from dependency package loading.

### N2 exit gate

- [ ] A relocated installed application loads its dependency without relying
      on the build directory or process working directory.
- [ ] Tampered, wrong-platform, missing, duplicated, and path-traversing
      artifacts all fail before module initialization.

## N3 - Provide a safe typed NOX HPy API

- [ ] Add an owned `Module` abstraction with deterministic close behavior.
- [ ] Add an owned/borrowed `Object` abstraction whose type state prevents or
      detects double close, use-after-close, and lifetime beyond its module.
- [ ] Ensure all live modules and objects are closed on normal return, error,
      early return, and program shutdown.
- [ ] Translate an HPy error into a stable NOX error value/exception without
      discarding the original type and message.
- [ ] Keep raw pointers and bridge intrinsics out of generated package public
      APIs; confine them to an audited runtime module.
- [ ] Specify thread, reentrancy, concurrency, and runtime-shutdown behavior.
- [ ] Add fault injection around open, lookup, call, conversion, allocation,
      close, and shutdown paths.

### N3 exit gate

- [ ] User code can consume the generated facade without spelling a raw
      pointer or manual bridge intrinsic.
- [ ] Repeated load/call/unload and injected-failure stress is clean under all
      supported native-memory tools.

## N4 - Complete value and call marshalling required by aHPy packages

- [ ] Implement and test the agreed scalar profile: `None`/void, `bool`,
      signed integers, finite floats, Unicode strings, and bytes.
- [ ] Implement object-return, attribute get/set, method calls, and constructor
      calls with explicit ownership at every boundary.
- [ ] Define positional-only, positional-or-keyword, keyword-only, default,
      variadic, and rejected-call behavior; do not guess unsupported layouts.
- [ ] Add lists, tuples, and dictionaries only after their element ownership,
      failure cleanup, and recursive conversion limits are specified.
- [ ] Preserve embedded NULs, Unicode edge cases, integer overflow, non-finite
      floats, and conversion exceptions.
- [ ] Reject unsupported signatures using the aHPy manifest before invoking
      the native symbol.

### N4 exit gate

- [ ] Every declared mapping has round-trip, boundary, exception, and cleanup
      tests shared by QBE and LLVM.
- [ ] Every undeclared mapping is rejected deterministically with a source or
      package diagnostic.

## N5 - Integrate with the NOX package manager

- [ ] Teach dependency resolution to validate the aHPy package schema and
      minimum NOX HPy host version.
- [ ] Verify artifact hashes and source provenance before cache admission and
      again before load.
- [ ] Define lockfile identity for manifest version, aHPy version, source
      commit, HPy ABI, platform artifact, and content digest.
- [ ] Support reproducible offline installation from a complete cache and fail
      clearly when a required platform artifact is absent.
- [ ] Preserve license, notice, SBOM, signature/attestation, and source-offer
      metadata when repackaging.
- [ ] Prevent build scripts from receiving publish credentials or unrestricted
      loader paths.
- [ ] Specify cache invalidation and conflict behavior for two packages with
      the same module name but different identities.

### N5 exit gate

- [ ] Clean online and offline installs produce the same verified package
      identity and execute the same conformance result.
- [ ] Dependency removal, cache cleanup, and reinstall leave no stale native
      artifact selected by the loader.

## N6 - Cross-repository CI, documentation, and release

- [ ] Pin one released or immutable aHPy fixture instead of building against a
      floating branch.
- [ ] Run module functions, external-C calls, extension types, attributes,
      identity, exceptions, module state, and cleanup through QBE and LLVM.
- [ ] Run the declared OS/architecture matrix and retain exact artifact hashes,
      compiler versions, NOX commit, aHPy commit, and HPy host profile.
- [ ] Add positive controls to sanitizer/native-memory jobs so an unavailable
      detector cannot be reported as a clean result.
- [ ] Test relocation, read-only installation, paths with spaces/Unicode,
      parallel package builds, repeated execution, and interrupted installs.
- [ ] Correct HPy documentation so every path, API, compatibility claim, and
      limitation matches the released tree.
- [ ] Publish a NOX-side package-author guide and troubleshooting table without
      claiming the excluded NOX-to-Python direction.
- [ ] Define preview/stable versioning, deprecation, security reporting,
      supported-version, and rollback policies for the HPy host contract.

### NOX-side definition of done

- [ ] The aHPy package contract is versioned and accepted by the NOX package
      manager without ad-hoc path wiring.
- [ ] QBE and LLVM pass the same semantics, ownership, failure, and relocation
      corpus on every declared release platform.
- [ ] Public NOX code uses a typed lifetime-safe facade; raw HPy pointers remain
      inside the runtime boundary.
- [ ] All package bytes are hash/provenance bound and verified before load.
- [ ] Documentation states exactly what works, what is blocked, and which
      aHPy/HPy/NOX versions were proven together.
- [ ] No checkbox in this file is closed by an aHPy-only change or by an
      unretained local experiment.
