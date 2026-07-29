"""Create a self-contained, auditable aHPy release evidence bundle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from ahpy_version import (
    AHPY_DISTRIBUTION,
    AHPY_HPY_SUPPORTED_VERSION,
    AHPY_SETUPTOOLS_VERSION,
    AHPY_VERSION,
    CYTHON_BASE_COMMIT,
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


def license_inventory(source_revision):
    """Describe the licenses shipped or consumed by the preview bundle."""
    source_revision = validate_source_commit(source_revision)
    return {
        "schema_version": 1,
        "source_commit": source_revision,
        "components": [
            {
                "name": AHPY_DISTRIBUTION,
                "version": AHPY_VERSION,
                "license": "Apache-2.0",
                "evidence": ["LICENSE.txt", "COPYING.txt"],
                "notes": (
                    "The embedded Cython tree preserves its Apache-2.0 and "
                    "historical Pyrex notices in the source distribution."
                ),
            },
            {
                "name": "ahpy-pep517-example",
                "version": "0.0.0",
                "license": "Apache-2.0",
                "evidence": [
                    "docs/ahpy/adr/0004-project-and-release-policy.md",
                ],
            },
            {
                "name": "hpy",
                "version": AHPY_HPY_SUPPORTED_VERSION,
                "license": "MIT",
                "evidence": ["wheel Core Metadata: License: MIT"],
            },
            {
                "name": "setuptools",
                "version": AHPY_SETUPTOOLS_VERSION,
                "license": "MIT",
                "evidence": [
                    "wheel Core Metadata: License-Expression: MIT",
                ],
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
    source_revision = validate_source_commit(
        report["provenance"]["source_commit"])
    packages = []
    relationships = []
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

    evidence = {
        "SHA256SUMS": checksum_manifest(report),
        "licenses.json": json.dumps(
            license_inventory(report["provenance"]["source_commit"]),
            indent=2,
            sort_keys=True,
        ) + "\n",
        "provenance.json": json.dumps(
            report, indent=2, sort_keys=True) + "\n",
        "sbom.spdx.json": json.dumps(
            spdx_document(report), indent=2, sort_keys=True) + "\n",
    }
    for name, source in sorted(provided.items()):
        shutil.copy2(source, directory / name)
    for name, content in evidence.items():
        directory.joinpath(name).write_text(content, encoding="utf8")
    return sorted(path.name for path in directory.iterdir())
