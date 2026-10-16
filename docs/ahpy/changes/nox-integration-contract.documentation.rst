Freeze the planning-only, one-way aHPy Universal HPy package to NOX consumer
contract in ADR 0016, a strict machine-readable policy, and a versioned JSON
manifest schema.  The new validation gate rejects reverse-direction scope,
fallback, partial packages, NOX source mutation, and premature support claims;
it does not yet advertise a compatible NOX release.
Add a canonical manifest validator and negative corpus that fail closed on
schema/host/signature/ownership drift, unsafe or duplicate target artifacts,
and malformed integrity metadata; the checked-in fixture remains contract
evidence rather than generated consumer support.
