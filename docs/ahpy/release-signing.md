# Release signing and verification

aHPy release evidence uses keyless Sigstore signatures issued to the exact
GitHub Actions workflow identity. No maintainer laptop, long-lived signing
key, personal access token, or locally built package is part of the signing
path.

This gate signs provenance; it does not claim that the signed code is safe or
that an unpublished preview is production-ready.

## Signing policy

`.github/workflows/ahpy-release-attestations.yml` runs only for tags named
`ahpy-v<package-version>`. The workflow rejects a tag that does not exactly
match `ahpy_version.AHPY_VERSION`, checks out that tag without persisted Git
credentials, builds with the frozen CPython 3.11/HPy 0.9.0/setuptools 80.9.0
toolchain, and reruns both clean onboarding and two-root byte-reproducibility
gates.

After those gates pass, the workflow uses the official `actions/attest`
action pinned to an immutable commit. GitHub OIDC supplies a short-lived
identity and Sigstore records the public-repository signature in its
transparency log. The workflow creates:

- SLSA provenance attestations for every file in the retained release bundle;
- an SPDX SBOM attestation for every sdist or wheel in that bundle; and
- downloadable Sigstore JSON bundles for offline verification.

The job has only `contents: read`, `id-token: write`, `attestations: write`,
and `artifact-metadata: write`. Ordinary pull requests, branch pushes,
schedules, and manual dispatches cannot invoke it.

Creating the tag remains a release-owner action. Do not create it until the
same commit has all required production contexts green, the declared support
contract and release notes are final, and any release environment approvals
configured in GitHub have passed. Never rebuild or replace files under an
existing version.

## Verify a downloaded bundle

First verify the ordinary digest manifest from inside `release-bundle`:

```console
sha256sum --check SHA256SUMS
```

On macOS, use:

```console
shasum -a 256 -c SHA256SUMS
```

Then verify each artifact against the exact repository and signer workflow.
For example:

```console
gh attestation verify \
  release-bundle/ahpy_compiler-3.3.0.1.dev0.tar.gz \
  --repo mburakmmm/aHPy \
  --signer-workflow \
  mburakmmm/aHPy/.github/workflows/ahpy-release-attestations.yml \
  --source-ref refs/tags/ahpy-v3.3.0.1.dev0 \
  --deny-self-hosted-runners
```

The default predicate is SLSA provenance. Verify the attached SPDX statement
separately:

```console
gh attestation verify \
  release-bundle/ahpy_compiler-3.3.0.1.dev0.tar.gz \
  --repo mburakmmm/aHPy \
  --signer-workflow \
  mburakmmm/aHPy/.github/workflows/ahpy-release-attestations.yml \
  --source-ref refs/tags/ahpy-v3.3.0.1.dev0 \
  --predicate-type https://spdx.dev/Document/v2.3 \
  --deny-self-hosted-runners
```

Replace the version and filename with the release being inspected. Verification
must fail if the repository, workflow, tag, predicate, signature, or artifact
digest differs.

## Offline verification

On a connected machine, download the attestations for the artifact and a fresh
trusted-root snapshot:

```console
gh attestation download \
  release-bundle/ahpy_compiler-3.3.0.1.dev0.tar.gz \
  --repo mburakmmm/aHPy
gh attestation trusted-root > trusted_root.jsonl
```

Transfer the artifact, downloaded `sha256:*.jsonl` file (or the retained
Sigstore bundles), and `trusted_root.jsonl` to the offline machine. Verify with
the same repository, workflow, tag, and runner policy:

```console
gh attestation verify \
  release-bundle/ahpy_compiler-3.3.0.1.dev0.tar.gz \
  --repo mburakmmm/aHPy \
  --signer-workflow \
  mburakmmm/aHPy/.github/workflows/ahpy-release-attestations.yml \
  --source-ref refs/tags/ahpy-v3.3.0.1.dev0 \
  --bundle sha256:REPLACE_WITH_ARTIFACT_DIGEST.jsonl \
  --custom-trusted-root trusted_root.jsonl \
  --deny-self-hosted-runners
```

Fetch a new trusted-root snapshot whenever new signed material enters the
offline environment. A stale root cannot report later key revocation or
rotation.

## PyPI boundary

These GitHub attestations do not reserve `aHPy-compiler`, upload a distribution,
or configure PyPI Trusted Publishing. When the separate publication gate is
approved, the official PyPA publishing action must use OIDC Trusted Publishing
so PyPI emits its PEP 740 publish attestations. Consumers must then verify the
index-served provenance with `pypi-attestations` in addition to the GitHub
release evidence described here.

The frontend-only candidate selection, TestPyPI Trusted Publishing boundary,
and immutable-version recovery policy are documented in
[the publication policy](publishing.md).
