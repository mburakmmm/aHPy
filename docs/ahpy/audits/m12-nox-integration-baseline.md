# M12 NOX integration baseline

- Observation date: 2026-10-16
- aHPy support result: **planned/blocked; no consumer support claim**
- NOX repository analyzed: `mburakmmm/nox-lang`
- Analyzed NOX commit: `6a33eaa50bf5ce29505dc1e75695fd27ec9505e4`
- Analyzed repository release: `v2.0.16`
- Locally installed `noxc` used by the probe: `v2.0.9`

## Scope and evidence quality

This audit records the observation that motivated ADR 0016 and the M12
contract. It is not retained hosted evidence: the temporary probe package and
build cache were removed, and the experiment did not preserve a complete
artifact hash/provenance bundle. The analyzed repository version and installed
runtime version also differ. The machine policy therefore requires
`support_claim = false`, `retained_hosted_evidence = false`, and
`minimum_nox_release = "unreleased"`.

No NOX source file was changed during the analysis or by the contract work.

## Positive QBE observation

The installed NOX QBE backend opened an aHPy-produced Universal `.hpy0`
extension and returned the expected values for this small surface:

| Operation | Observed value |
| --- | ---: |
| Module function `answer()` | `42` |
| Python-independent external-C-backed `external_add(...)` | `42` |
| Extension object `Box.value` | `5` |
| Extension object identity call | `42` |

This proves only that those calls completed in one local environment. It does
not prove package-relative loading, lifecycle cleanup, exception fidelity,
artifact integrity, relocation, reproducibility, other targets, or a released
NOX host profile.

## LLVM blocker observation

The same high-level probe failed through the installed default LLVM backend
before equivalent execution. Generated IR compared the result of
`nox_hpy_take_error` using an incompatible width:

```text
%t7 defined with type i64 but expected i32
```

The M12 policy identifies this as `nox-llvm-hpy-error-width`. It is a NOX-owned
backend/bridge blocker, not an aHPy emitter defect demonstrated by the current
evidence. aHPy must keep LLVM consumer support blocked until a pinned consumer
passes the same conformance package; aHPy must not patch or vendor a NOX runtime
to hide the failure.

## Documentation and contract gaps observed

The analyzed NOX tree has an HPy bridge, NNI surface, plugin API, and package
manager, but those pieces do not yet form the v1 package contract. In
particular, the analysis did not find evidence sufficient to claim all of the
documented CPython-compatibility paths or exception-barrier behavior. The
NOX-owner verification and repair queue is intentionally separate in
`NOX-INTEGRATION-TODO.md`.

## Resulting aHPy boundary

The accepted aHPy contract now fixes one-way direction, repository ownership,
manifest/schema identity, HPy 0.9 Universal host profile, initial mapping
vocabulary, exact-target artifact selection, canonical metadata, and
fail-closed support wording. The next aHPy-owned step is deterministic export
analysis and manifest validation; executable NOX support remains blocked on
both that implementation and the independent NOX-owner gates.
