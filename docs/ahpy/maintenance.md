# Maintenance, support lifetime, and change policy

This document makes aHPy's maintenance process explicit so updating the Cython
fork or producing a release is not unwritten single-person knowledge. The
machine-readable source of truth is
`tests/ahpy/maintenance-policy.toml`; validate it with:

```console
python3 Tools/ahpy/maintenance_policy.py
python3 Tools/ahpy/maintenance_policy.py --json
```

The production documentation surface is separately frozen in
`tests/ahpy/documentation-contract.toml` and validated with
`python3 Tools/ahpy/documentation_contract.py`. It prevents required user,
contributor, architecture, debugging or release instructions from disappearing
or becoming unreachable while the fork evolves.

## Ownership and current capacity

`@mburakmmm` is the currently named project, security, and release maintainer.
`.github/CODEOWNERS` records the same ownership for the backend, quality tools,
workflows, policy and documentation. The current bus factor is explicitly one;
this is a project risk, not a higher support claim. Add a maintainer to the
machine contract and CODEOWNERS only after that person accepts the named
responsibilities. One release-maintainer approval is required while only one
release maintainer exists; increase the approval minimum when ownership grows.

Responsibilities are divided even when one person currently holds them:

- project maintenance: issue classification, roadmap and Cython rebase;
- security maintenance: private report handling and coordinated disclosure;
- release maintenance: same-commit gates, provenance, signing, publication and
  rollback decisions.

## Supported versions and end of life

aHPy is an unpublished preview. Only current `main`, the exact Cython base,
CPython 3.11, HPy 0.9.0 and the lanes named in `release-contract.md` can carry
a support claim. There are currently zero stable release lines and no response
SLA. Early-warning Python, HPy, PyPy and GraalPy lanes do not extend support.

After the first stable release, at most one stable
`ahpy/<cython-major>.<cython-minor>` line is maintained at a time. A line stays
supported until an explicit dated EOL record is added to this document and the
release/support contracts. EOL is never inferred from a newer tag. Security,
correctness, packaging and compatibility fixes may be backported; new feature
families normally remain on `main`.

## Branch, rebase, and backport procedure

`main` tracks current Cython integration. Topic branches remain short-lived;
release branches match `ahpy/<cython-major>.<cython-minor>`. Direct pushes and
history rewrites are forbidden by policy. Before each upstream update:

1. record old and proposed Cython commits in the rebase log;
2. fetch upstream and inspect the complete commit range;
3. rebase or merge only on a topic branch;
4. classify each conflict as upstream-taken, backend-neutral, aHPy-specific or
   obsolete, recording the file and decision;
5. run the full upstream Cython suite plus all applicable aHPy gates;
6. update the exact base commit, support contract, changelog and provenance in
   one reviewed change.

A backport starts from the release branch, names its source commit and category,
includes the original regression test, and reruns that line's mandatory matrix.
It must not broaden the documented feature or platform tier. A security
backport follows private advisory coordination until disclosure.

The no-publication recovery rehearsal is executable and retained as CI
evidence:

```console
python3 Tools/ahpy/release_recovery_drill.py \
  --output /tmp/ahpy-release-recovery-drill.json
```

It creates an isolated Git repository, branches an `ahpy/3.2` release-line
fixture, makes a correctness fix with its original regression test on a topic
branch, and cherry-picks it with source provenance onto a separate backport
topic branch. The validator rejects direct-push/history-rewrite policy,
support-tier expansion, missing regression tests, unnamed source commits, or a
missing mandatory-matrix requirement. It does not create a real release branch
or publish/yank/delete an artifact.

## Deprecation and compatibility breaks

Preview status permits change but not surprise: every removed or narrowed
documented behavior requires a changelog entry, support-matrix update and
migration guidance before it can ship. A stable supported surface remains
available for at least one subsequent aHPy release cycle on the same Cython
line. Correctness or security emergencies may bypass that waiting cycle only
with an explicit rationale, migration path and release note.

No deprecation or break may introduce CPython/Hybrid fallback, private HPy APIs
or false Universal wheel metadata. Source incompatibility should fail at the
original location with a stable migration action. ABI or artifact-policy
changes require an ADR and clean release-evidence regeneration.

The compatibility classification is exhaustive for the production contract:

| Surface | Breaking examples | Required migration evidence |
| --- | --- | --- |
| Source | accepted syntax becomes rejected, or ownership requirements narrow | source-located stable action ID, replacement or explicit rationale, old/new tests |
| Runtime semantics | return, exception, cleanup, GC or module-state behavior changes | semantic and failure-path tests plus release note |
| Generated source | public generated-C seam, header boundary or build input changes | ADR when architectural, source/binary audits and regenerated evidence |
| Artifact | ABI, suffix, tag, metadata, loader or supported HPy version changes | support-matrix update, clean package evidence and installation migration |
| CLI/configuration | option, default, exit status or machine schema changes | old/new CLI tests and replacement command or schema guidance |
| Diagnostics | diagnostic/action ID disappears or changes meaning | replacement action ID, catalog update and migration guidance |

During preview, a breaking change may ship only when the same commit updates
the changelog, release notes, support matrix and migration guide, supplies a
stable action ID, and carries old/new regression evidence. After a stable
release, a deprecated surface remains functional through at least one complete
subsequent release cycle on the same Cython line; if notice begins in release
N, removal is no earlier than the release after N+1. Removal happens only at a
release boundary, never in an unannounced patch artifact.

Only a correctness or security emergency may shorten that stable interval. It
still requires release-owner approval, an explicit rationale, replacement or
containment guidance, old/new tests and release notes. Emergency handling never
permits silent CPython/Hybrid fallback or private HPy API use.

## Review cadence

| Input | Required review |
| --- | --- |
| Python and build dependencies | Monthly Dependabot review |
| GitHub Actions | Monthly Dependabot review; immutable SHA remains mandatory |
| Cython upstream | Monthly commit-range and conflict review |
| HPy stable/development | Monthly API/version/reproducer review |
| Python interpreters | Monthly supported and early-warning review |
| OS, runner images and compilers | Quarterly matrix review |
| CodeQL and dependency vulnerabilities | Every change plus weekly scheduled scan |

An urgent private security report is handled outside this calendar. The
pre-stable project deliberately promises no acknowledgement or remediation
time; `SECURITY.md` defines the private channel and evidence requested.

## Automated security gates

`.github/workflows/ahpy-security.yml` runs dependency review on pull requests
and CodeQL `security-extended` queries for Python and C/C++ on changes and a
weekly schedule. Every action is pinned to a full immutable commit. Dependabot
reviews Actions plus root, aHPy-test and wheel-build Python dependencies
monthly. A scanner outage or unavailable dependency graph is a failed gate,
not permission to publish without review.

Security tooling supplements rather than replaces the HPy-specific source,
binary, ownership, fault-injection, sanitizer and Debug Mode gates. Findings
are triaged as release-blocking until reproduced and assigned to aHPy, Cython,
HPy, a dependency or infrastructure with retained evidence.

## Issue triage and release responsibility

New reports are classified as security-private, release-blocker, correctness,
compatibility, packaging, documentation or upstream/infrastructure. Public
issues must never contain undisclosed vulnerability details. Every external
blocker needs a minimal reproducer and upstream link before PRD-9 closes. Use
`debugging.md` to preserve the first failing boundary and keep prepared reports,
filed issue URLs, hosted evidence, and unsupported lanes distinct in
`upstream-dependencies.md`.

The release maintainer verifies the exact version/base commit, two clean RC
runs, mandatory checks, compatibility dashboard, performance proposal,
checksums, SBOM, licenses, provenance, attestations, onboarding and rollback
procedure. TestPyPI/PyPI upload, release-branch creation and tags remain
owner-approved external actions; documenting this procedure does not perform
them.
