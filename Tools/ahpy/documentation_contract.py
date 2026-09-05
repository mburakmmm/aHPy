#!/usr/bin/env python3
"""Validate aHPy's production documentation corpus and internal links."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "tests" / "ahpy" / "documentation-contract.toml"
CATEGORIES = ("architecture", "contributor", "debugging", "release", "user")
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REQUIRED_PATHS = {
    "AGENTTODO.md",
    "CONTRIBUTING.md",
    "TODO.md",
    "production-todo.md",
    "docs/ahpy/README.md",
    "docs/ahpy/adr/0001-backend-architecture.md",
    "docs/ahpy/build-systems.md",
    "docs/ahpy/context-model.md",
    "docs/ahpy/debugging.md",
    "docs/ahpy/diagnostics.md",
    "docs/ahpy/direct-build.md",
    "docs/ahpy/external-c.md",
    "docs/ahpy/handle-model.md",
    "docs/ahpy/known-limitations.md",
    "docs/ahpy/maintenance.md",
    "docs/ahpy/migration-scanner.md",
    "docs/ahpy/module-state.md",
    "docs/ahpy/onboarding.md",
    "docs/ahpy/pep517.md",
    "docs/ahpy/performance-release-gate.md",
    "docs/ahpy/porting-guide.md",
    "docs/ahpy/publishing.md",
    "docs/ahpy/release-contract.md",
    "docs/ahpy/release-signing.md",
    "docs/ahpy/runtime-api.md",
    "docs/ahpy/support-matrix.md",
    "docs/ahpy/upstream-dependencies.md",
    "docs/ahpy/validation-matrix.md",
}


class DocumentationContractError(ValueError):
    """The documentation contract is incomplete, unsafe, or inconsistent."""


def _require(condition, message):
    if not condition:
        raise DocumentationContractError(message)


def _exact_keys(mapping, keys, context):
    _require(isinstance(mapping, dict), f"{context} must be a table")
    expected = set(keys)
    observed = set(mapping)
    _require(observed == expected, "%s keys mismatch; missing=%s unknown=%s" % (
        context,
        ",".join(sorted(expected - observed)) or "none",
        ",".join(sorted(observed - expected)) or "none",
    ))


def _safe_path(value, context):
    _require(isinstance(value, str) and value, f"{context} must be a path")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts,
             f"{context} must stay inside the repository")
    return path


def _headings(text):
    return {
        match.group(1).strip().rstrip("#").rstrip()
        for line in text.splitlines()
        if (match := re.fullmatch(r"#{1,6}\s+(.+)", line.strip()))
    }


def _link_target(raw_target, source, root):
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1:target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    if (not target or target.startswith(("#", "//")) or re.match(
            r"[a-z][a-z0-9+.-]*:", target, re.IGNORECASE)):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    _require(target, f"{source}: empty local link target")
    candidate = Path(target)
    _require(not candidate.is_absolute(),
             f"{source}: local link must be relative: {target}")
    resolved = (source.parent / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise DocumentationContractError(
            f"{source}: local link escapes repository: {target}") from exc
    _require(resolved.exists(), f"{source}: broken local link: {target}")
    return resolved


def _validate_local_links(path, root):
    text = path.read_text(encoding="utf8")
    targets = set()
    for raw_target in MARKDOWN_LINK_RE.findall(text):
        target = _link_target(raw_target, path, root)
        if target is not None:
            targets.add(target)
    return targets


def _is_indexed(path, index_targets):
    for target in index_targets:
        if target == path:
            return True
        if target.is_dir():
            try:
                path.relative_to(target)
            except ValueError:
                continue
            return True
    return False


def validate_contract(data, root=ROOT, source="documentation contract"):
    _exact_keys(data, {"schema_version", "status", "categories", "documents"},
                source)
    _require(data["schema_version"] == 1,
             f"{source}: unsupported schema version")
    _require(data["status"] == "preview",
             f"{source}: status must remain preview before release")
    _require(data["categories"] == list(CATEGORIES),
             f"{source}: categories must be exact and ordered")
    documents = data["documents"]
    _require(isinstance(documents, list) and documents,
             f"{source}: documents must be a non-empty array")

    parsed = []
    ids = set()
    paths = set()
    for index, document in enumerate(documents):
        context = f"documents[{index}]"
        _exact_keys(document, {
            "id", "category", "path", "indexed", "required_headings",
        }, context)
        document_id = document["id"]
        _require(isinstance(document_id, str) and ID_RE.fullmatch(document_id),
                 f"{context}.id must be lowercase kebab-case")
        _require(document_id not in ids, f"duplicate document id: {document_id}")
        ids.add(document_id)
        category = document["category"]
        _require(category in CATEGORIES,
                 f"{document_id}: unknown category {category!r}")
        relative_path = _safe_path(document["path"], f"{document_id}.path")
        normalized = relative_path.as_posix()
        _require(normalized not in paths, f"duplicate document path: {normalized}")
        paths.add(normalized)
        _require(type(document["indexed"]) is bool,
                 f"{document_id}.indexed must be boolean")
        required_headings = document["required_headings"]
        _require(isinstance(required_headings, list) and required_headings and
                 len(required_headings) == len(set(required_headings)) and
                 all(isinstance(heading, str) and heading.strip()
                     for heading in required_headings),
                 f"{document_id}.required_headings must be unique strings")
        path = Path(root) / relative_path
        try:
            path.resolve().relative_to(Path(root).resolve())
        except ValueError as exc:
            raise DocumentationContractError(
                f"required documentation path escapes repository: {normalized}"
            ) from exc
        _require(path.is_file(), f"required documentation file is missing: {normalized}")
        text = path.read_text(encoding="utf8")
        observed_headings = _headings(text)
        missing_headings = [
            heading for heading in required_headings
            if heading not in observed_headings
        ]
        _require(not missing_headings, "%s missing required headings: %s" % (
            normalized, ", ".join(missing_headings)))
        targets = _validate_local_links(path, Path(root))
        parsed.append({
            "id": document_id,
            "category": category,
            "path": normalized,
            "indexed": document["indexed"],
            "heading_count": len(observed_headings),
            "local_link_count": len(targets),
        })

    _require(paths == REQUIRED_PATHS,
             "%s: document path set mismatch; missing=%s unknown=%s" % (
                 source,
                 ",".join(sorted(REQUIRED_PATHS - paths)) or "none",
                 ",".join(sorted(paths - REQUIRED_PATHS)) or "none"))
    category_counts = {
        category: sum(item["category"] == category for item in parsed)
        for category in CATEGORIES
    }
    _require(all(category_counts.values()),
             f"{source}: every category needs at least one document")

    index_path = Path(root) / "docs" / "ahpy" / "README.md"
    index_targets = _validate_local_links(index_path, Path(root))
    for item in parsed:
        if item["indexed"]:
            path = (Path(root) / item["path"]).resolve()
            _require(_is_indexed(path, index_targets),
                     f"documentation index does not link {item['path']}")

    try:
        contract_label = Path(source).resolve().relative_to(
            Path(root).resolve()).as_posix()
    except ValueError:
        contract_label = str(source)
    return {
        "schema_version": 1,
        "status": "valid",
        "contract": contract_label,
        "categories": category_counts,
        "document_count": len(parsed),
        "local_link_count": sum(
            item["local_link_count"] for item in parsed),
        "documents": parsed,
    }


def load_contract(path=DEFAULT_CONTRACT, root=ROOT):
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DocumentationContractError(
            f"cannot read documentation contract {path}: {exc}") from exc
    return validate_contract(data, root=root, source=str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    try:
        report = load_contract(options.contract, options.root)
    except DocumentationContractError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
