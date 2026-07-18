# aHPy security policy

## Supported versions

aHPy is pre-release software and has no supported stable release series yet.
Security fixes are developed against the current `main` branch. This policy
does not turn unvalidated platforms or language features into support claims;
see the [support matrix](docs/ahpy/support-matrix.md).

## Reporting a vulnerability

Do not open a public issue. Submit a private report through
[GitHub Security Advisories](https://github.com/mburakmmm/aHPy/security/advisories/new)
with:

- the affected aHPy commit or package version;
- a minimal reproducer and expected security boundary;
- Python, HPy, OS, architecture, compiler, and runtime mode;
- generated source/binary evidence when applicable;
- the potential impact and any known workaround.

The maintainer will acknowledge the report, validate scope, and coordinate a
fix and disclosure when the report is reproducible. No response-time or embargo
guarantee is claimed before a stable release and a dedicated security team
exist.

Vulnerabilities that reproduce in upstream Cython without `hpy-universal`, or
in HPy without aHPy-generated code, may need coordinated reporting to those
projects. Do not disclose them publicly while coordination is pending.
