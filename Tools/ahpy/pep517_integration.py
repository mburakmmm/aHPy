#!/usr/bin/env python3
"""Build the aHPy frontend wheel, then use it in real PEP 517 isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import (
    AHPY_DISTRIBUTION,
    AHPY_VERSION,
    provenance_project_urls,
    source_commit,
)
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


EXAMPLE = ROOT / "examples" / "ahpy_pep517"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_frontend_source(destination):
    destination.mkdir()
    ignored = shutil.ignore_patterns(
        "__pycache__", "*.pyc", "*.so", "*.pyd", ".DS_Store")
    shutil.copytree(ROOT / "Cython", destination / "Cython", ignore=ignored)
    shutil.copytree(ROOT / "bin", destination / "bin", ignore=ignored)
    shutil.copytree(ROOT / "pyximport", destination / "pyximport", ignore=ignored)
    for name in ("Tools/ahpy", "tests/ahpy", "docs/ahpy", "examples"):
        shutil.copytree(ROOT / name, destination / name, ignore=ignored)
    for name in (
        "setup.py", "setup.cfg", "pyproject.toml", "README.rst",
        "CHANGES.rst", "COPYING.txt", "LICENSE.txt", "MANIFEST.in",
        "cython.py", "ahpy_version.py", "ahpy_build_backend.py",
        "ahpy_build_config.py", "ahpy_hpy_compat.py", "TODO.md", "AGENTTODO.md",
        "CONTRIBUTING.md", "SECURITY.md",
    ):
        shutil.copy2(ROOT / name, destination / name)
    destination.joinpath(".gitrev").write_text(
        source_commit(ROOT) + "\n", encoding="ascii")


def _frontend_metadata(wheel, expected_commit=None):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA"))
        metadata_text = archive.read(metadata_name).decode("utf8")
        entry_point_names = [
            name for name in names
            if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(entry_point_names) != 1:
            raise AssertionError(
                "frontend wheel must contain exactly one entry_points.txt")
        entry_points_text = archive.read(entry_point_names[0]).decode("utf8")
    if "Name: %s\n" % AHPY_DISTRIBUTION not in metadata_text:
        raise AssertionError("frontend wheel is not the aHPy distribution")
    if "Version: %s\n" % AHPY_VERSION not in metadata_text:
        raise AssertionError("frontend wheel has the wrong aHPy version")
    expected_commit = expected_commit or source_commit(ROOT)
    for label, url in provenance_project_urls(expected_commit).items():
        field = "Project-URL: %s, %s\n" % (label, url)
        if field not in metadata_text:
            raise AssertionError(
                "frontend wheel lacks exact provenance field %s" % label)
    for required in (
        "ahpy_build_backend.py", "ahpy_build_config.py", "ahpy_hpy_compat.py",
        "ahpy_version.py",
    ):
        if required not in names:
            raise AssertionError("frontend wheel is missing %s" % required)
    hook_entry = (
        "[cython.runtime_backend_build_hooks]\n"
        "hpy-universal = "
        "ahpy_hpy_compat:install_hpy_universal_loader_compat\n"
    )
    if hook_entry not in entry_points_text:
        raise AssertionError(
            "frontend wheel lacks the Universal backend build hook")
    if not any(name.startswith("Cython/") for name in names):
        raise AssertionError("frontend wheel is missing the Cython package")


def _runtime_program(debug):
    prefix = ""
    suffix = ""
    if debug:
        prefix = (
            "from hpy.debug import LeakDetector\n"
            "detector = LeakDetector()\n"
            "detector.start()\n"
        )
        suffix = "detector.stop()\n"
    return (
        "import ahpy_pep517_example as module\n" + prefix +
        "assert module.answer() == 42\n"
        "marker = object()\n"
        "box = module.Box(marker)\n"
        "assert box.value is marker\n"
        "assert box.identity() is marker\n"
        "del box\n" + suffix
    )


def build_and_run(python, report_path=None):
    python = os.path.abspath(python) if Path(python).exists() else shutil.which(python)
    if python is None:
        raise ValueError("Python interpreter not found")
    with TemporaryDirectory(prefix="ahpy-pep517-") as temp_dir:
        temp = Path(temp_dir)
        frontend_source = temp / "frontend-source"
        _copy_frontend_source(frontend_source)
        wheelhouse = temp / "wheelhouse"
        wheelhouse.mkdir()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("HPY", None)
        environment["NO_CYTHON_COMPILE"] = "true"
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        run([
            python, "-m", "pip", "wheel", "--no-build-isolation",
            "--no-deps", "--wheel-dir", str(wheelhouse),
            str(frontend_source),
        ], env=environment)
        frontend_wheels = sorted(wheelhouse.glob("ahpy_compiler-*.whl"))
        if len(frontend_wheels) != 1:
            raise AssertionError("expected one aHPy frontend wheel")
        frontend_wheel = frontend_wheels[0]
        _frontend_metadata(frontend_wheel)

        run([
            python, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(wheelhouse),
            "hpy==0.9.0", "setuptools==83.0.0",
        ], env=environment)
        dependency_wheels = sorted(
            path for path in wheelhouse.glob("*.whl")
            if path != frontend_wheel)
        if len(dependency_wheels) != 2:
            raise AssertionError(
                "expected exactly HPy and setuptools dependency wheels")
        dependency_names = [path.name.lower() for path in dependency_wheels]
        if not any(name.startswith("hpy-0.9.0-") for name in dependency_names):
            raise AssertionError("wheelhouse lacks exact HPy 0.9.0")
        if not any(
                name.startswith("setuptools-83.0.0-")
                for name in dependency_names):
            raise AssertionError("wheelhouse lacks exact setuptools 83.0.0")

        project = temp / "project"
        shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("__pycache__"))
        dist = temp / "dist"
        dist.mkdir()
        isolated_environment = environment.copy()
        isolated_environment.pop("NO_CYTHON_COMPILE", None)
        isolated_environment["PIP_FIND_LINKS"] = str(wheelhouse)
        isolated_environment["PIP_NO_INDEX"] = "1"
        run([
            python, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(dist), str(project),
        ], cwd=temp, env=isolated_environment)

        wheels = sorted(dist.glob("ahpy_pep517_example-*.whl"))
        if len(wheels) != 1:
            raise AssertionError("expected one PEP 517 example wheel")
        wheel = wheels[0]
        extract = temp / "wheel-extract"
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            archive.extractall(extract)
            hpy_members = [name for name in names if ".hpy0." in name]
            stubs = [name for name in names if name == "ahpy_pep517_example.py"]
            wheel_metadata = next(
                name for name in names if name.endswith(".dist-info/WHEEL"))
            wheel_text = archive.read(wheel_metadata).decode("utf8")
        if len(hpy_members) != 1 or len(stubs) != 1:
            raise AssertionError("PEP 517 wheel lacks .hpy0 binary/stub")
        binary = extract / hpy_members[0]
        verify_binary_boundary(binary)
        generated = project / "ahpy_pep517_example.c"
        verify_source_boundary(
            generated,
            required=("#include <hpy.h>", "HPyType_FromSpec", "HPy_MODINIT"),
        )

        installed = temp / "installed"
        run([
            python, "-m", "pip", "install", "--no-deps", "--target",
            str(installed), str(wheel),
        ], env=environment)
        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(installed)
        run([python, "-c", _runtime_program(False)], env=runtime_environment)
        debug_environment = runtime_environment.copy()
        debug_environment["HPY"] = "debug"
        run([python, "-c", _runtime_program(True)], env=debug_environment)

        tags = sorted(
            line.removeprefix("Tag: ")
            for line in wheel_text.splitlines() if line.startswith("Tag: "))
        report = {
            "schema_version": 1,
            "frontend": {
                "name": frontend_wheel.name,
                "version": AHPY_VERSION,
                "sha256": _sha256(frontend_wheel),
            },
            "build_dependencies": [
                {"name": path.name, "sha256": _sha256(path)}
                for path in dependency_wheels
            ],
            "example_wheel": {
                "name": wheel.name,
                "sha256": _sha256(wheel),
                "tags": tags,
                "hpy_binary": hpy_members[0],
            },
            "build_isolation": True,
            "runtime_modes": ["normal", "debug"],
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
    report = build_and_run(args.python, args.output)
    print("aHPy isolated PEP 517 build passed: %s" %
          report["example_wheel"]["name"])


if __name__ == "__main__":
    main()
