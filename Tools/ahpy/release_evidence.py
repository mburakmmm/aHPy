"""Create a self-contained, auditable aHPy release evidence bundle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import (
    AHPY_BUILD_FRONTEND_VERSION,
    AHPY_DISTRIBUTION,
    AHPY_HPY_SUPPORTED_VERSION,
    AHPY_SETUPTOOLS_VERSION,
    AHPY_VERSION,
    CYTHON_BASE_COMMIT,
    CYTHON_BASE_VERSION,
    validate_source_commit,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_DATE_EPOCH = 1767225600


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_records(report):
    """Return all release artifact records after strict identity validation."""
    records = [
        report["sdist"],
        report["frontend_wheel"],
        report["example_wheel"],
        *report["build_dependencies"],
    ]
    names = [record["name"] for record in records]
    if len(names) != len(set(names)):
        raise ValueError("release artifact names must be unique")
    for record in records:
        if Path(record["name"]).name != record["name"]:
            raise ValueError("release artifact names must be plain filenames")
        if not _SHA256.fullmatch(record["sha256"]):
            raise ValueError(
                "release artifact %s lacks a lowercase SHA-256" %
                record["name"])
    return records


def checksum_manifest(report):
    """Render a deterministic GNU-compatible SHA256SUMS manifest."""
    return "".join(
        "%s  %s\n" % (record["sha256"], record["name"])
        for record in sorted(
            artifact_records(report), key=lambda item: item["name"])
    )


def _component_artifacts(report, component):
    return [
        {"name": record["name"], "sha256": record["sha256"]}
        for record in artifact_records(report)
        if _component_for_artifact(record["name"])[0] == component
    ]


def _validated_provenance(report):
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("release report lacks build provenance")
    source_revision = validate_source_commit(
        provenance.get("source_commit", ""))
    expected = {
        "cython_base_commit": CYTHON_BASE_COMMIT,
        "build_frontend_version": AHPY_BUILD_FRONTEND_VERSION,
        "installed_hpy": AHPY_HPY_SUPPORTED_VERSION,
        "installed_setuptools": AHPY_SETUPTOOLS_VERSION,
    }
    for field, value in expected.items():
        if provenance.get(field) != value:
            raise ValueError(
                "release provenance requires %s=%s" % (field, value))
    return source_revision


def license_inventory(report):
    """Describe all direct licenses shipped or used to build the bundle."""
    source_revision = _validated_provenance(report)
    return {
        "schema_version": 2,
        "source_commit": source_revision,
        "scope": "direct-shipped-and-build-components",
        "components": [
            {
                "id": "ahpy-compiler",
                "name": AHPY_DISTRIBUTION,
                "version": AHPY_VERSION,
                "role": "project-artifact",
                "license_expression": "Apache-2.0",
                "evidence": ["LICENSE.txt", "COPYING.txt"],
                "provenance": {
                    "revision": source_revision,
                    "source": "https://github.com/mburakmmm/aHPy",
                    "artifacts": _component_artifacts(
                        report, AHPY_DISTRIBUTION),
                },
            },
            {
                "id": "embedded-cython",
                "name": "Cython",
                "version": CYTHON_BASE_VERSION,
                "role": "embedded-source",
                "license_expression": "Apache-2.0",
                "evidence": ["LICENSE.txt", "COPYING.txt"],
                "provenance": {
                    "revision": CYTHON_BASE_COMMIT,
                    "source": "https://github.com/cython/cython",
                    "artifacts": _component_artifacts(
                        report, AHPY_DISTRIBUTION),
                },
            },
            {
                "id": "packaging-example",
                "name": "ahpy-pep517-example",
                "version": "0.0.0",
                "role": "packaging-example",
                "license_expression": "Apache-2.0",
                "evidence": [
                    "docs/ahpy/adr/0004-project-and-release-policy.md",
                ],
                "provenance": {
                    "revision": source_revision,
                    "source": "https://github.com/mburakmmm/aHPy",
                    "artifacts": _component_artifacts(
                        report, "ahpy-pep517-example"),
                },
            },
            {
                "id": "hpy",
                "name": "hpy",
                "version": AHPY_HPY_SUPPORTED_VERSION,
                "role": "runtime-build-input",
                "license_expression": "MIT",
                "evidence": ["wheel Core Metadata: License: MIT"],
                "provenance": {
                    "revision": None,
                    "source": "https://github.com/hpyproject/hpy",
                    "artifacts": _component_artifacts(report, "hpy"),
                },
            },
            {
                "id": "setuptools",
                "name": "setuptools",
                "version": AHPY_SETUPTOOLS_VERSION,
                "role": "build-backend",
                "license_expression": "MIT",
                "evidence": [
                    "wheel Core Metadata: License-Expression: MIT",
                ],
                "provenance": {
                    "revision": None,
                    "source": "https://github.com/pypa/setuptools",
                    "artifacts": _component_artifacts(report, "setuptools"),
                },
            },
            {
                "id": "pypa-build",
                "name": "build",
                "version": AHPY_BUILD_FRONTEND_VERSION,
                "role": "build-frontend",
                "license_expression": "MIT",
                "evidence": [
                    "installed Core Metadata: License-Expression: MIT",
                    "tests/ahpy/requirements-build-systems.txt",
                ],
                "provenance": {
                    "revision": None,
                    "source": "https://github.com/pypa/build",
                    "artifacts": [],
                },
            },
        ],
    }


def _component_for_artifact(name):
    normalized = name.lower().replace("-", "_")
    if normalized.startswith("ahpy_compiler_"):
        return AHPY_DISTRIBUTION, AHPY_VERSION, "Apache-2.0"
    if normalized.startswith("ahpy_pep517_example_"):
        return "ahpy-pep517-example", "0.0.0", "Apache-2.0"
    if normalized.startswith("hpy_") or normalized.startswith("hpy-"):
        return "hpy", AHPY_HPY_SUPPORTED_VERSION, "MIT"
    if normalized.startswith("setuptools_"):
        return "setuptools", AHPY_SETUPTOOLS_VERSION, "MIT"
    raise ValueError("unclassified release artifact %s" % name)


def spdx_document(report):
    """Build a deterministic SPDX 2.3 JSON document for the release bundle."""
    source_revision = _validated_provenance(report)
    packages = []
    relationships = []
    ahpy_package_ids = []
    for index, record in enumerate(sorted(
            artifact_records(report), key=lambda item: item["name"]), 1):
        component, version, license_id = _component_for_artifact(record["name"])
        spdx_id = "SPDXRef-Package-%d" % index
        packages.append({
            "SPDXID": spdx_id,
            "name": component,
            "versionInfo": version,
            "packageFileName": record["name"],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": license_id,
            "licenseDeclared": license_id,
            "copyrightText": "NOASSERTION",
            "checksums": [{
                "algorithm": "SHA256",
                "checksumValue": record["sha256"],
            }],
            "primaryPackagePurpose": "LIBRARY",
            "externalRefs": [{
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": "pkg:pypi/%s@%s" % (
                    component.lower(), version),
            }],
        })
        relationships.append({
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": spdx_id,
        })
        if component == AHPY_DISTRIBUTION:
            ahpy_package_ids.append(spdx_id)
    cython_id = "SPDXRef-Embedded-Cython"
    packages.append({
        "SPDXID": cython_id,
        "name": "Cython",
        "versionInfo": CYTHON_BASE_VERSION,
        "downloadLocation": (
            "git+https://github.com/cython/cython@%s" % CYTHON_BASE_COMMIT),
        "filesAnalyzed": False,
        "licenseConcluded": "Apache-2.0",
        "licenseDeclared": "Apache-2.0",
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "LIBRARY",
        "externalRefs": [{
            "referenceCategory": "PACKAGE-MANAGER",
            "referenceType": "purl",
            "referenceLocator": (
                "pkg:github/cython/cython@%s" % CYTHON_BASE_COMMIT),
        }],
    })
    relationships.append({
        "spdxElementId": "SPDXRef-DOCUMENT",
        "relationshipType": "DESCRIBES",
        "relatedSpdxElement": cython_id,
    })
    for package_id in ahpy_package_ids:
        relationships.append({
            "spdxElementId": package_id,
            "relationshipType": "CONTAINS",
            "relatedSpdxElement": cython_id,
        })
    build_id = "SPDXRef-Build-Frontend"
    packages.append({
        "SPDXID": build_id,
        "name": "build",
        "versionInfo": AHPY_BUILD_FRONTEND_VERSION,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "MIT",
        "licenseDeclared": "MIT",
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "APPLICATION",
        "externalRefs": [{
            "referenceCategory": "PACKAGE-MANAGER",
            "referenceType": "purl",
            "referenceLocator": (
                "pkg:pypi/build@%s" % AHPY_BUILD_FRONTEND_VERSION),
        }],
    })
    relationships.append({
        "spdxElementId": "SPDXRef-DOCUMENT",
        "relationshipType": "DESCRIBES",
        "relatedSpdxElement": build_id,
    })
    for package_id in ahpy_package_ids:
        relationships.append({
            "spdxElementId": build_id,
            "relationshipType": "BUILD_TOOL_OF",
            "relatedSpdxElement": package_id,
        })
    created = datetime.fromtimestamp(
        int(report["provenance"].get(
            "source_date_epoch", _SOURCE_DATE_EPOCH)),
        timezone.utc,
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "%s-%s-release-bundle" % (AHPY_DISTRIBUTION, AHPY_VERSION),
        "documentNamespace": (
            "https://github.com/mburakmmm/aHPy/releases/spdx/%s/%s" % (
                source_revision, report["sdist"]["sha256"])
        ),
        "creationInfo": {
            "created": created,
            "creators": [
                "Tool: aHPy Tools/ahpy/release_artifact_integration.py",
            ],
        },
        "documentDescribes": [
            package["SPDXID"] for package in packages
        ],
        "packages": packages,
        "relationships": relationships,
        "externalDocumentRefs": [],
        "annotations": [{
            "annotationDate": created,
            "annotationType": "OTHER",
            "annotator": "Tool: aHPy release evidence",
            "comment": (
                "Embedded Cython base commit %s; HPy compatibility %s." %
                (CYTHON_BASE_COMMIT, AHPY_HPY_SUPPORTED_VERSION)
            ),
        }],
    }


def evidence_documents(report):
    """Render the exact evidence files bound to one validated report."""
    return {
        "SHA256SUMS": checksum_manifest(report),
        "licenses.json": json.dumps(
            license_inventory(report), indent=2, sort_keys=True) + "\n",
        "provenance.json": json.dumps(
            report, indent=2, sort_keys=True) + "\n",
        "sbom.spdx.json": json.dumps(
            spdx_document(report), indent=2, sort_keys=True) + "\n",
    }


def validate_release_bundle_evidence(directory, report):
    """Rehash every artifact and require exact regenerated evidence files."""
    directory = Path(directory)
    for record in artifact_records(report):
        artifact = directory / record["name"]
        if not artifact.is_file() or _sha256(artifact) != record["sha256"]:
            raise ValueError(
                "release artifact content mismatch for %s" % record["name"])
    for name, expected in evidence_documents(report).items():
        try:
            observed = (directory / name).read_text(encoding="utf8")
        except OSError as exc:
            raise ValueError(
                "release bundle lacks required evidence %s" % name) from exc
        if observed != expected:
            raise ValueError("release bundle evidence mismatch for %s" % name)
    return True


def write_release_bundle(directory, report, artifact_paths):
    """Copy artifacts and write checksum, SPDX, license, and provenance data."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("release bundle directory must be empty")
    expected = {record["name"]: record for record in artifact_records(report)}
    artifact_paths = [Path(path) for path in artifact_paths]
    provided = {path.name: path for path in artifact_paths}
    if len(provided) != len(artifact_paths) or set(provided) != set(expected):
        raise ValueError("release bundle artifact set does not match report")
    for name, source in sorted(provided.items()):
        if not source.is_file() or _sha256(source) != expected[name]["sha256"]:
            raise ValueError("release artifact content mismatch for %s" % name)

    evidence = evidence_documents(report)
    for name, source in sorted(provided.items()):
        shutil.copy2(source, directory / name)
    for name, content in evidence.items():
        directory.joinpath(name).write_text(content, encoding="utf8")
    validate_release_bundle_evidence(directory, report)
    return sorted(path.name for path in directory.iterdir())
