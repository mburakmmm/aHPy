# ADR 0016: One-way NOX consumer package contract

- Status: accepted; consumer support remains planned/blocked
- Date: 2026-10-16

## Context

aHPy already emits Universal HPy source and `.hpy0` extensions. NOX has an HPy
host boundary, but a developer-machine probe is not a package contract: it does
not define export metadata, target selection, artifact integrity, lifetime
ownership, capability negotiation, or reproducible installation. Coupling an
aHPy generator directly to current NOX compiler internals would also make both
projects evolve in lockstep and could disguise missing runtime guarantees.

The project needs a narrow interoperability direction that can be implemented
and tested in aHPy without modifying NOX. The reverse direction—loading NOX
modules from Python or generating Python packages from NOX—is a separate design
and is not authorized by this decision.

## Decision

### Direction and repository ownership

The only in-scope direction is:

```text
aHPy source -> Universal HPy artifact + nox-hpy manifest + typed NOX facade
            -> NOX package consumer
```

| aHPy owns | NOX owns |
| --- | --- |
| Export analysis from compiler type data | Package/dependency resolution |
| Canonical manifest generation and validation | Host ABI and capability query |
| Typed `.nox` facade source generation | Dynamic loading and target staging |
| Universal artifact build and source/binary audit | QBE/LLVM backend correctness |
| Deterministic package assembly and provenance | Object/module lifetime safety |
| Frontend-neutral conformance package | Runtime error translation |

An aHPy task may consume a released or immutable NOX binary for conformance
testing, but it must not edit, vendor, commit, or push NOX source. Missing NOX
capabilities stay external blockers and are listed in
[`NOX-INTEGRATION-TODO.md`](../../../NOX-INTEGRATION-TODO.md).

### Versioned contract

`tests/ahpy/nox-integration-policy.toml` is the normative machine-readable
policy. Contract version 1 defines:

- manifest filename `nox-hpy.json` and JSON Schema
  `tests/ahpy/nox-hpy-package.schema.json`;
- host profile `nox-hpy-host-v1`, HPy 0.9, Universal ABI only;
- package-relative `.hpy0` paths, exact target matching, SHA-256 integrity,
  canonical UTF-8 JSON, provenance, and reproducible package output;
- public typed facade source with `.nox` suffix and a private bridge boundary;
- fail-closed behavior for incompatible versions, missing capabilities,
  unsupported signatures, partial output, and fallback attempts.

No released NOX version is declared compatible yet. The minimum consumer
release is therefore the literal state `unreleased`, the support state is
`blocked`, and every target is `planned`. Changing any of those values requires
retained cross-repository evidence and synchronized support documentation.

### Initial surface classification

The required v1 value vocabulary is `none`, `void`, `bool`, signed 64-bit
integer, 64-bit float, Unicode, and opaque extension object. Bytes are
capability-gated. C pointers, callbacks, containers, fused types, memoryviews,
and CPython C-API objects are rejected by the initial contract.

Module functions, constructors, methods, and positional-only calls form the
required call vocabulary. Keyword forms remain capability-gated. Callbacks,
overloads, and variadic exports are rejected. These are generator-contract
requirements, not current support claims: no mapping becomes supported until
the exporter, facade, package, and pinned consumer evidence all pass.

### Manifest and artifact rules

The v1 manifest is a closed JSON object. It binds package identity, exact aHPy
and Cython producer identity, source/compiler-option digests, host profile,
module/init symbol, typed exports, and one or more target artifacts. Artifact
records use repository/package-relative `.hpy0` paths, a positive byte size,
and a lowercase SHA-256 digest. Unknown fields are rejected so semantics cannot
change silently.

Canonical serialization, name normalization, duplicate handling, and the first
source-positioned compiler-owned export-analysis pass are implemented in M12.
The pass emits a versioned intermediate descriptor and fails closed where
manifest v1 cannot preserve source semantics. Full manifest composition,
artifact/provenance binding, facade generation, and consumer support remain
implementation work; the schema alone is not a support claim.

### Compatibility and change control

Additive behavior is allowed only where the current schema explicitly permits
it. A new required field, changed ownership rule, changed mapping, or different
host behavior requires a new contract/schema version. Old readers reject a new
required version before module initialization. There is no CPython, HPy Hybrid,
or older-schema fallback.

Support promotion requires immutable evidence containing the exact aHPy commit,
NOX release/commit, host profile, backend, target, HPy version, package bytes,
and artifact hashes. A local probe can classify a blocker but cannot promote a
support state.

## Consequences

aHPy can implement deterministic metadata, facade generation, and package
assembly without importing NOX compiler internals. NOX may independently
implement the same published host/package contract. Until that happens,
consumer execution remains blocked even when local QBE experiments succeed.

The stricter boundary adds schema/version work and requires explicit failures
for tempting shortcuts such as arbitrary library paths or raw pointer APIs.
That cost is intentional: a package that cannot prove target, integrity,
ownership, and host capability must not be emitted as usable.
