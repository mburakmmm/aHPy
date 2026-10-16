#!/usr/bin/env python3
"""Compose a canonical nox-hpy manifest from compiler and artifact evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import AHPY_VERSION, CYTHON_BASE_COMMIT  # noqa: E402
import nox_export  # noqa: E402
import nox_integration_policy  # noqa: E402
import nox_manifest  # noqa: E402


SOURCE_DIGEST_PROTOCOL = b"ahpy-nox-source-inputs-v1\0"


class NoxPackageManifestError(RuntimeError):
    """The full manifest cannot be composed from the supplied evidence."""


def _require(condition, message):
    if not condition:
        raise NoxPackageManifestError(message)


def _source_inputs(paths, root):
    root = Path(root).resolve()
    inputs = []
    names = set()
    for value in paths:
        path = Path(value).resolve()
        _require(path.is_file(), "source input does not exist: %s" % path)
        try:
            name = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise NoxPackageManifestError(
                "source input escapes source root: %s" % path) from exc
        _require(name not in names, "duplicate source input: %s" % name)
        names.add(name)
        inputs.append((name, path.read_bytes()))
    _require(inputs, "at least one source input is required")
    return sorted(inputs)


def source_inputs_digest(paths, root=ROOT):
    digest = hashlib.sha256(SOURCE_DIGEST_PROTOCOL)
    for name, content in _source_inputs(paths, root):
        name_bytes = name.encode("utf8")
        digest.update(len(name_bytes).to_bytes(8, "big"))
        digest.update(name_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def compiler_options_digest(module_name):
    options = {
        "language_level": 3,
        "module_name": str(module_name),
        "nox_export_analysis": True,
        "runtime_backend": "hpy-universal",
    }
    rendered = json.dumps(
        options, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((rendered + "\n").encode("utf8")).hexdigest()


def artifact_record(target, package_path, source_path):
    source_path = Path(source_path)
    _require(source_path.is_file(), "artifact does not exist: %s" % source_path)
    path = PurePosixPath(package_path)
    _require(
        not path.is_absolute() and ".." not in path.parts
        and path.as_posix() == package_path,
        "artifact package path is unsafe: %s" % package_path,
    )
    content = source_path.read_bytes()
    _require(content, "artifact is empty: %s" % source_path)
    return {
        "target": str(target),
        "path": package_path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


def _validate_analysis(analysis):
    _require(isinstance(analysis, dict), "export analysis must be an object")
    _require(
        set(analysis) == {
            "protocol", "module", "required_capabilities", "exports",
        },
        "export analysis keys do not match protocol v1",
    )
    _require(
        analysis["protocol"] == nox_export.NOX_EXPORT_PROTOCOL,
        "export analysis protocol is incompatible",
    )
    return analysis


def build_manifest(
    source, module_name, package_name, package_version, artifacts, *,
    source_inputs=(), source_root=ROOT,
):
    analysis = _validate_analysis(
        nox_export.analyze_source(source, module_name=module_name))
    _require(
        analysis["module"]["name"] == module_name,
        "compiler analysis returned the wrong module identity",
    )
    all_sources = [source] + list(source_inputs)
    artifact_records = sorted(
        (artifact_record(*artifact) for artifact in artifacts),
        key=lambda item: item["target"],
    )
    _require(artifact_records, "at least one target artifact is required")
    policy = nox_integration_policy.load_policy()
    manifest = {
        "schema_version": policy["contract_version"],
        "package": {"name": package_name, "version": package_version},
        "producer": {
            "ahpy_version": AHPY_VERSION,
            "cython_base": CYTHON_BASE_COMMIT,
            "source_digest": source_inputs_digest(
                all_sources, root=source_root),
            "compiler_options_digest": compiler_options_digest(module_name),
        },
        "host": {
            "profile": policy["host"]["profile"],
            "hpy_abi": policy["host"]["hpy_abi"],
            "hpy_version": policy["host"]["hpy_version"],
            "required_capabilities": analysis["required_capabilities"],
        },
        "module": analysis["module"],
        "exports": analysis["exports"],
        "artifacts": artifact_records,
    }
    try:
        return nox_manifest.validate_manifest(manifest, policy=policy)
    except nox_manifest.NoxManifestError as exc:
        raise NoxPackageManifestError(str(exc)) from exc


def write_manifest(manifest, output, check=False):
    try:
        rendered = nox_manifest.canonical_manifest_bytes(manifest)
    except nox_manifest.NoxManifestError as exc:
        raise NoxPackageManifestError(str(exc)) from exc
    output = Path(output)
    if check:
        try:
            existing = output.read_bytes()
        except OSError as exc:
            raise NoxPackageManifestError(
                "cannot read package manifest %s: %s" % (output, exc)) from exc
        _require(existing == rendered, "%s is stale or non-canonical" % output)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
    return rendered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--module-name", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--source-input", action="append", type=Path, default=[])
    parser.add_argument(
        "--artifact", action="append", nargs=3, required=True,
        metavar=("TARGET", "PACKAGE_PATH", "SOURCE_PATH"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(argv)
    if options.check and options.output is None:
        parser.error("--check requires --output")
    try:
        manifest = build_manifest(
            options.source,
            options.module_name,
            options.package_name,
            options.package_version,
            options.artifact,
            source_inputs=options.source_input,
            source_root=options.source_root,
        )
        if options.output is None:
            sys.stdout.buffer.write(nox_manifest.canonical_manifest_bytes(manifest))
        else:
            write_manifest(manifest, options.output, check=options.check)
    except (NoxPackageManifestError, nox_export.NoxExportCommandError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
