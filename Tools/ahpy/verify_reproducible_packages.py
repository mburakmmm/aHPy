#!/usr/bin/env python3
"""Require byte-identical aHPy frontend archives from two clean builds."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

from pep517_integration import _copy_frontend_source


SOURCE_DATE_EPOCH = "1767225600"


def _run(command, *, cwd=None, env=None):
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if completed.returncode:
        raise subprocess.CalledProcessError(
            completed.returncode, command, output=completed.stdout)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_sdist(path):
    """Rewrite a gzip/tar sdist with deterministic archive metadata."""
    path = Path(path)
    normalized = path.with_name(path.name + ".normalized")
    epoch = int(SOURCE_DATE_EPOCH)
    with tarfile.open(path, "r:gz") as source, normalized.open("wb") as raw:
        with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw,
                compresslevel=9, mtime=epoch) as compressed:
            with tarfile.open(
                    fileobj=compressed, mode="w|",
                    format=tarfile.PAX_FORMAT) as target:
                for member in sorted(source.getmembers(), key=lambda item: item.name):
                    payload = source.extractfile(member) if member.isfile() else None
                    member.mtime = epoch
                    member.uid = 0
                    member.gid = 0
                    member.uname = ""
                    member.gname = ""
                    member.pax_headers = {}
                    target.addfile(member, payload)
    os.replace(normalized, path)
    return path


def _build_once(python, root):
    root.mkdir()
    source = root / "source"
    dist = root / "dist"
    _copy_frontend_source(source)
    dist.mkdir()
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("HPY", None)
    environment.update({
        "NO_CYTHON_COMPILE": "true",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
    })
    _run([
        python, "-m", "build", "--sdist", "--wheel", "--no-isolation",
        "--outdir", str(dist), str(source),
    ], env=environment)
    for sdist in dist.glob("*.tar.gz"):
        normalize_sdist(sdist)
    artifacts = sorted(path for path in dist.iterdir() if path.is_file())
    suffixes = {".whl", ".gz"}
    if len(artifacts) != 2 or {path.suffix for path in artifacts} != suffixes:
        raise AssertionError(
            "expected exactly one sdist and one wheel, got %r" %
            [path.name for path in artifacts])
    return dist


def compare_artifact_directories(first, second):
    first_names = sorted(path.name for path in first.iterdir() if path.is_file())
    second_names = sorted(path.name for path in second.iterdir() if path.is_file())
    if first_names != second_names:
        raise AssertionError(
            "package artifact sets differ: %r != %r" %
            (first_names, second_names))
    mismatches = [
        name for name in first_names
        if (first / name).read_bytes() != (second / name).read_bytes()
    ]
    if mismatches:
        raise AssertionError(
            "package archives are not byte-reproducible: %s" %
            ", ".join(mismatches))
    return [
        {
            "name": name,
            "sha256": _sha256(first / name),
            "size": (first / name).stat().st_size,
        }
        for name in first_names
    ]


def _provenance(python):
    program = (
        "import json, platform, sys\n"
        "from importlib import metadata\n"
        "print(json.dumps({\n"
        "  'python': platform.python_version(),\n"
        "  'implementation': platform.python_implementation(),\n"
        "  'platform': platform.platform(),\n"
        "  'build': metadata.version('build'),\n"
        "  'setuptools': metadata.version('setuptools'),\n"
        "}, sort_keys=True))\n"
    )
    return json.loads(subprocess.check_output(
        [python, "-c", program], text=True,
        env={key: value for key, value in os.environ.items()
             if key not in {"PYTHONPATH", "HPY"}},
    ))


def verify(python, report_path=None):
    python = os.path.abspath(python) if Path(python).exists() else shutil.which(python)
    if python is None:
        raise ValueError("Python interpreter not found")
    with TemporaryDirectory(prefix="ahpy-package-reproducibility-") as temp_dir:
        root = Path(temp_dir)
        first = _build_once(python, root / "first")
        second = _build_once(python, root / "second")
        artifacts = compare_artifact_directories(first, second)
    report = {
        "schema_version": 1,
        "build_roots": 2,
        "byte_identical": True,
        "source_date_epoch": int(SOURCE_DATE_EPOCH),
        "artifacts": artifacts,
        "provenance": _provenance(python),
    }
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.python, args.output)
    print(
        "aHPy reproducible package archives passed: %s" %
        ", ".join(artifact["name"] for artifact in report["artifacts"]))


if __name__ == "__main__":
    main()
