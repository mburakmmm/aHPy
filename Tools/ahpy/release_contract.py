#!/usr/bin/env python3
"""Validate aHPy's machine-readable preview/release support contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import (
    AHPY_DISTRIBUTION,
    AHPY_HPY_SUPPORTED_VERSION,
    AHPY_SETUPTOOLS_VERSION,
    AHPY_VERSION,
    CYTHON_BASE_COMMIT,
    CYTHON_BASE_VERSION,
)


DEFAULT_CONTRACT = ROOT / "tests" / "ahpy" / "release-contract.toml"
HPY_VERSIONS = Path("tests/ahpy/hpy-versions.toml")
UNIVERSAL_WORKFLOW = Path(".github/workflows/ahpy-universal.yml")
CONTRACT_DOCUMENT = Path("docs/ahpy/release-contract.md")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PATCH_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
EXPECTED_PLATFORMS = {
    "linux-x64-gcc": ("ubuntu-24.04", "x86-64", "GCC"),
    "linux-x64-clang": ("ubuntu-24.04", "x86-64", "Clang"),
    "linux-arm64-gcc": ("ubuntu-24.04-arm", "ARM64", "GCC"),
    "macos-intel-clang": ("macos-15-intel", "x86-64", "Clang"),
    "macos-arm64-clang": ("macos-15", "ARM64", "Clang"),
    "windows-x64-msvc": ("windows-2025", "x86-64", "MSVC"),
}
EXPECTED_FRONTENDS = {
    "compiler-cli": "supported",
    "direct-build": "partial",
    "setuptools-cythonize": "partial",
    "pep517": "partial",
    "cmake": "partial",
    "meson": "partial",
    "scikit-build-core": "partial",
}
SUPPORT_STATUSES = {"supported", "partial", "blocked", "rejected"}


class ReleaseContractError(ValueError):
    """The support contract is malformed or differs from repository policy."""


def _require(condition, message):
    if not condition:
        raise ReleaseContractError(message)


def _exact_keys(value, expected, context):
    _require(isinstance(value, dict), "%s must be a table" % context)
    _require(
        set(value) == set(expected),
        "%s keys are incomplete or unknown" % context,
    )


def _nonempty(value, context):
    _require(
        isinstance(value, str) and value.strip(),
        "%s must be a non-empty string" % context,
    )
    return value


def _load_toml(path, context):
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ReleaseContractError(
            "cannot read %s %s: %s" % (context, path, error)
        ) from error


def _unique_records(records, expected_ids, context):
    _require(isinstance(records, list), "%s must be an array" % context)
    _require(
        all(isinstance(record, dict) for record in records),
        "%s entries must be tables" % context,
    )
    identifiers = [record.get("id") for record in records]
    _require(
        len(identifiers) == len(set(identifiers)),
        "%s ids must be unique" % context,
    )
    _require(
        set(identifiers) == set(expected_ids),
        "%s ids differ from the preview contract" % context,
    )
    return {record["id"]: record for record in records}


def validate_contract(data, root=ROOT, source="release contract"):
    """Validate schema, repository identity, support claims, and evidence."""
    _exact_keys(data, {
        "schema_version", "product_level", "distribution",
        "distribution_version", "publication_status",
        "general_cython_compatibility", "cython", "hpy", "python",
        "evidence", "platforms", "frontends",
    }, source)
    _require(data["schema_version"] == 1, "%s schema must be 1" % source)
    _require(
        data["product_level"] == "preview" and
        data["publication_status"] == "unpublished" and
        data["general_cython_compatibility"] is False,
        "%s must remain an unpublished preview without general Cython claims" %
        source,
    )
    _require(
        data["distribution"] == AHPY_DISTRIBUTION and
        data["distribution_version"] == AHPY_VERSION,
        "%s distribution identity differs from ahpy_version.py" % source,
    )

    cython = data["cython"]
    _exact_keys(cython, {"version", "base_commit"}, "%s.cython" % source)
    _require(
        cython == {
            "version": CYTHON_BASE_VERSION,
            "base_commit": CYTHON_BASE_COMMIT,
        },
        "%s Cython identity differs from ahpy_version.py" % source,
    )

    versions_path = Path(root) / HPY_VERSIONS
    versions = _load_toml(versions_path, "HPy version manifest")
    _require(
        isinstance(versions.get("stable"), dict) and
        isinstance(versions.get("development"), dict),
        "HPy version manifest lacks stable/development tables",
    )
    hpy = data["hpy"]
    _exact_keys(hpy, {
        "supported_versions", "setuptools_version", "development_commit",
        "development_status",
    }, "%s.hpy" % source)
    _require(
        hpy["supported_versions"] == [AHPY_HPY_SUPPORTED_VERSION] ==
        [versions["stable"].get("version")],
        "%s supported HPy version differs from repository pins" % source,
    )
    _require(
        hpy["setuptools_version"] == AHPY_SETUPTOOLS_VERSION,
        "%s setuptools version differs from ahpy_version.py" % source,
    )
    _require(
        isinstance(hpy["development_commit"], str) and
        COMMIT_RE.fullmatch(hpy["development_commit"]) and
        hpy["development_commit"] == versions["development"].get("commit") and
        hpy["development_status"] == versions["development"].get("status") ==
        "early-warning",
        "%s HPy development identity differs from repository pins" % source,
    )

    python = data["python"]
    _exact_keys(python, {
        "supported_implementation", "supported_versions",
        "locally_validated_patch", "unsupported_implementations",
    }, "%s.python" % source)
    _require(
        python["supported_implementation"] == "CPython" and
        python["supported_versions"] == ["3.11"] ==
        versions["stable"].get("python"),
        "%s Python support differs from the stable HPy lane" % source,
    )
    patch = python["locally_validated_patch"]
    match = PATCH_RE.fullmatch(patch) if isinstance(patch, str) else None
    _require(
        match is not None and list(match.groups()[:2]) == ["3", "11"],
        "%s locally validated patch must belong to CPython 3.11" % source,
    )
    unsupported = python["unsupported_implementations"]
    _require(
        isinstance(unsupported, list) and
        len(unsupported) == len(set(unsupported)) and
        set(unsupported) == {"PyPy", "GraalPy"},
        "%s unsupported interpreter set must be exactly PyPy and GraalPy" %
        source,
    )

    evidence = data["evidence"]
    evidence_keys = {
        "implementation_commit", "ahpy_run", "benchmark_run", "ci_run",
        "coverage_run", "sanitizers_run",
    }
    _exact_keys(evidence, evidence_keys, "%s.evidence" % source)
    _require(
        isinstance(evidence["implementation_commit"], str) and
        COMMIT_RE.fullmatch(evidence["implementation_commit"]),
        "%s evidence implementation_commit must be a full commit" % source,
    )
    for field in sorted(evidence_keys - {"implementation_commit"}):
        _require(
            isinstance(evidence[field], int) and
            not isinstance(evidence[field], bool) and evidence[field] > 0,
            "%s evidence.%s must be a positive run id" % (source, field),
        )

    platforms = _unique_records(
        data["platforms"], EXPECTED_PLATFORMS, "%s.platforms" % source)
    workflow_path = Path(root) / UNIVERSAL_WORKFLOW
    try:
        workflow = workflow_path.read_text(encoding="utf8")
    except OSError as error:
        raise ReleaseContractError(
            "cannot read Universal workflow %s: %s" % (workflow_path, error)
        ) from error
    _require(
        "python Tools/ahpy/release_contract.py --json" in workflow,
        "%s is not enforced by the Universal workflow" % source,
    )
    for identifier, expected in EXPECTED_PLATFORMS.items():
        record = platforms[identifier]
        _exact_keys(
            record, {"id", "runner", "architecture", "compiler", "status"},
            "%s.platforms.%s" % (source, identifier),
        )
        _require(
            (record["runner"], record["architecture"], record["compiler"]) ==
            expected and record["status"] == "supported",
            "%s platform %s differs from the preview lane" %
            (source, identifier),
        )
        _require(
            "name: %s" % identifier in workflow and
            "os: %s" % record["runner"] in workflow,
            "%s platform %s is absent from the Universal workflow" %
            (source, identifier),
        )

    frontends = _unique_records(
        data["frontends"], EXPECTED_FRONTENDS, "%s.frontends" % source)
    for identifier, expected_status in EXPECTED_FRONTENDS.items():
        record = frontends[identifier]
        _exact_keys(
            record, {"id", "name", "status", "scope"},
            "%s.frontends.%s" % (source, identifier),
        )
        _require(
            record["status"] in SUPPORT_STATUSES and
            record["status"] == expected_status,
            "%s frontend %s has an invalid preview status" %
            (source, identifier),
        )
        _nonempty(record["name"], "%s frontend %s name" % (source, identifier))
        _nonempty(
            record["scope"], "%s frontend %s scope" % (source, identifier))

    document_path = Path(root) / CONTRACT_DOCUMENT
    try:
        document = document_path.read_text(encoding="utf8")
    except OSError as error:
        raise ReleaseContractError(
            "cannot read release contract documentation %s: %s" %
            (document_path, error)
        ) from error
    documented_values = (
        data["distribution"], data["distribution_version"],
        cython["version"], cython["base_commit"],
        AHPY_HPY_SUPPORTED_VERSION,
        evidence["implementation_commit"],
        *(str(evidence[field]) for field in sorted(
            evidence_keys - {"implementation_commit"})),
    )
    _require(
        all(value in document for value in documented_values),
        "%s machine identity/evidence differs from release-contract.md" % source,
    )
    return data


def load_contract(path=DEFAULT_CONTRACT, root=ROOT):
    return validate_contract(
        _load_toml(path, "release contract"), root=root, source=str(path))


def summary(contract):
    return {
        "schema_version": 1,
        "status": "valid",
        "product_level": contract["product_level"],
        "publication_status": contract["publication_status"],
        "distribution": contract["distribution"],
        "distribution_version": contract["distribution_version"],
        "cython_base_commit": contract["cython"]["base_commit"],
        "supported_hpy_versions": contract["hpy"]["supported_versions"],
        "supported_python_versions": contract["python"]["supported_versions"],
        "platform_count": len(contract["platforms"]),
        "frontend_count": len(contract["frontends"]),
        "evidence_commit": contract["evidence"]["implementation_commit"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    options = parser.parse_args(argv)
    try:
        result = summary(load_contract(options.contract, options.root))
    except ReleaseContractError as error:
        parser.error(str(error))
    if options.as_json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(
            "aHPy release contract: valid\n"
            "product: %(distribution)s==%(distribution_version)s "
            "(%(product_level)s, %(publication_status)s)\n"
            "Cython base: %(cython_base_commit)s\n"
            "support lanes: %(platform_count)d platforms, "
            "%(frontend_count)d frontends\n" % result
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
