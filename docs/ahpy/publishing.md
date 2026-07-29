# TestPyPI and PyPI publication policy

The `aHPy-compiler` distribution is unpublished and its project name is not
reserved. This document defines the publication path without authorizing or
performing an upload.

## Artifact scope

Only these two frontend files may enter a package index:

- `ahpy_compiler-<version>.tar.gz`;
- `ahpy_compiler-<version>-py3-none-any.whl`.

The host-tagged example wheel, HPy wheel, setuptools wheel, `.hpy0` evidence,
checksums, SBOM, license inventory, and provenance report are release evidence,
not `aHPy-compiler` distributions. In particular, no CPython-tagged example
wheel may be described or uploaded as a Universal wheel.

`Tools/ahpy/prepare_publish_dist.py` reads the validated release bundle,
requires its exact source commit and frozen HPy/setuptools versions, rehashes
the selected files, rejects a non-empty destination, and copies only the two
frontend distributions. Its JSON record always says `actual_upload: false`;
the tool has no network or upload implementation.

## No-upload rehearsal

From the repository root, after creating a fresh release bundle:

```console
.venv-hpy09/bin/python Tools/ahpy/prepare_publish_dist.py \
  --bundle-dir /tmp/ahpy-release-bundle \
  --publish-dir /tmp/ahpy-publish-dist \
  --repository testpypi \
  --output /tmp/ahpy-testpypi-dry-run.json
python -m twine check --strict /tmp/ahpy-publish-dist/*
```

The maintained GitHub workflow `.github/workflows/ahpy-testpypi.yml` performs
the same clean build, two-root byte comparison, selection, hashing, and strict
Twine metadata check. Manual dispatch defaults `publish` to false, so its
ordinary execution uploads only an Actions artifact and cannot contact
TestPyPI.

## Approved TestPyPI upload

Before setting `publish` to true, the project owner must:

1. reserve or create `aHPy-compiler` on TestPyPI;
2. configure a Trusted Publisher for owner `mburakmmm`, repository `aHPy`,
   workflow `ahpy-testpypi.yml`, and environment `testpypi`;
3. configure the GitHub `testpypi` environment with a maintainer approval
   rule; and
4. confirm that the candidate version has never been uploaded before.

The build job has no OIDC permission. A separate environment-gated publish job
downloads the immutable candidate and alone receives `id-token: write`. It
uses the official PyPA publishing action pinned to a full commit, TestPyPI's
explicit repository URL, `skip-existing: false`, and default PEP 740
attestations. It contains no username, password, API token, or repository
secret.

An actual TestPyPI upload is an external release action and requires explicit
project-owner approval. After upload, verify all of the following before any
PyPI work:

- the index filename and SHA-256 equal the dry-run record;
- `pip download --no-deps` retrieves those exact bytes;
- the wheel/sdist Core Metadata names `aHPy-compiler`, the exact version,
  aHPy source commit, Cython base, and HPy compatibility;
- `pypi-attestations verify pypi --repository
  https://github.com/mburakmmm/aHPy <file-url>` succeeds; and
- installing from TestPyPI with dependencies supplied by the pinned release
  wheelhouse passes the maintained onboarding example.

Do not let TestPyPI resolve an unrelated `ahpy`, upstream Cython, moving HPy,
or unpinned setuptools dependency.

## Production PyPI boundary

Production PyPI publication is tag-only and must remain a separate minimal
workflow and `pypi` environment. It may be enabled only after:

- the `aHPy-compiler` name is reserved by the project owner;
- an approved non-development release version and matching `ahpy-v<version>`
  tag exist;
- all required checks are green on that exact commit;
- GitHub SLSA/SPDX attestations for the exact files verify;
- the TestPyPI rehearsal and install verification are recorded; and
- release notes and the support contract state that the frontend is preview
  and that no standardized Universal extension wheel is being published.

PyPI publishing must use OIDC Trusted Publishing and the official PyPA action
with attestations enabled. Long-lived tokens and local uploads are prohibited.

## Immutability, yanking, and recovery

- Never replace, overwrite, or silently rebuild files for an existing version.
- Keep `skip-existing: false`; a collision is a release failure.
- For a packaging or compatibility defect, publish a new PEP 440 version.
- Yank a defective file/release with a concrete public reason when preventing
  new installs is necessary; do not treat deletion as ordinary rollback.
- Delete only for credential disclosure, malware, legal demand, or another
  exceptional incident that requires removal, and preserve a public incident
  record when legally possible.
- Never unyank without a new review of the original reason and recorded owner
  approval.

Yanking changes installer selection; it does not make already downloaded bytes
disappear. Security response follows `SECURITY.md`, while support and artifact
claims remain bound to the exact immutable hashes.
