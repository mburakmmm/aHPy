Freeze the planning-only, one-way aHPy Universal HPy package to NOX consumer
contract in ADR 0016, a strict machine-readable policy, and a versioned JSON
manifest schema.  The new validation gate rejects reverse-direction scope,
fallback, partial packages, NOX source mutation, and premature support claims;
it does not yet advertise a compatible NOX release.
Add a canonical manifest validator and negative corpus that fail closed on
schema/host/signature/ownership drift, unsafe or duplicate target artifacts,
and malformed integrity metadata; the checked-in fixture remains contract
evidence rather than generated consumer support.
Add an opt-in compiler-owned export-analysis pass and canonical CLI that derive
the initial callable/type/ownership/capability surface from analysed Cython AST
and symbol data, reproduce a retained fixture byte-for-byte, and fail closed
with source-positioned ``AHPY_NOX00x`` diagnostics instead of scraping C or
silently dropping unsupported public members.
Compose the compiler descriptor into canonical manifest v1 with deterministic
source and compiler-option digests, exact aHPy/Cython/host identity, safe target
paths, artifact sizes, and SHA-256 integrity; CI now regenerates the retained
fixture while continuing to label its payload as non-loadable contract data.
