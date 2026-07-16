#!/usr/bin/env python3
"""Build the maintained scikit-build-core example in PEP 517 isolation."""

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

from ahpy_version import AHPY_DISTRIBUTION, AHPY_VERSION
from pep517_integration import _copy_frontend_source, _frontend_metadata
from test_generated_hpy import verify_binary_boundary, verify_source_boundary


EXAMPLE = ROOT / "examples" / "ahpy_scikit_build"
MODULE = "ahpy_scikit_build_example"


def _run(command, *, cwd=None, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_program(debug):
    return (
        ("from hpy.debug import LeakDetector\n"
         "detector = LeakDetector()\n"
         "detector.start()\n" if debug else "") +
        "import ahpy_scikit_build_example as module\n"
        "assert module.answer() == 42\n"
        "marker = object()\n"
        "box = module.Box(marker)\n"
        "assert box.value is marker\n"
        "assert box.identity() is marker\n"
        "del box\n" +
        ("detector.stop()\n" if debug else "")
    )


def build_and_run(python, report_path=None):
    python = os.path.abspath(python) if Path(python).exists() else shutil.which(python)
    if python is None:
        raise ValueError("Python interpreter not found")
    with TemporaryDirectory(prefix="ahpy-scikit-build-") as temp_dir:
        temp = Path(temp_dir)
        wheelhouse = temp / "wheelhouse"
        wheelhouse.mkdir()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("HPY", None)
        environment["NO_CYTHON_COMPILE"] = "true"
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

        frontend_source = temp / "frontend-source"
        _copy_frontend_source(frontend_source)
        _run([
            python, "-m", "pip", "wheel", "--no-build-isolation",
            "--no-deps", "--wheel-dir", str(wheelhouse),
            str(frontend_source),
        ], env=environment)
        frontend_wheels = sorted(wheelhouse.glob("ahpy_compiler-*.whl"))
        if len(frontend_wheels) != 1:
            raise AssertionError("expected one aHPy-compiler wheel")
        frontend_wheel = frontend_wheels[0]
        _frontend_metadata(frontend_wheel)

        _run([
            python, "-m", "pip", "wheel", "--no-build-isolation",
            "--wheel-dir", str(wheelhouse),
            "hpy==0.9.0", "scikit-build-core==1.0.3",
            "cmake==4.3.4", "ninja==1.13.0", "setuptools==80.9.0",
        ], env=environment)

        project = temp / "project"
        shutil.copytree(EXAMPLE, project)
        dist = temp / "dist"
        dist.mkdir()
        isolated = environment.copy()
        isolated.pop("NO_CYTHON_COMPILE", None)
        isolated["PIP_FIND_LINKS"] = str(wheelhouse)
        isolated["PIP_NO_INDEX"] = "1"
        _run([
            python, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(dist), str(project),
        ], cwd=temp, env=isolated)
        wheels = sorted(dist.glob("ahpy_scikit_build_example-*.whl"))
        if len(wheels) != 1:
            raise AssertionError("expected one scikit-build-core example wheel")
        wheel = wheels[0]
        extract = temp / "extract"
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            archive.extractall(extract)
            binaries = [name for name in names if ".hpy0." in name]
            stubs = [name for name in names if name == MODULE + ".py"]
            wheel_meta = next(
                name for name in names if name.endswith(".dist-info/WHEEL"))
            tags = sorted(
                line.removeprefix("Tag: ")
                for line in archive.read(wheel_meta).decode("utf8").splitlines()
                if line.startswith("Tag: "))
        if len(binaries) != 1 or len(stubs) != 1:
            raise AssertionError("scikit-build wheel lacks .hpy0 binary/stub")
        binary = extract / binaries[0]
        verify_binary_boundary(binary)
        generated_files = sorted(project.rglob(MODULE + ".c"))
        if len(generated_files) != 1:
            raise AssertionError("isolated CMake build did not retain generated C")
        verify_source_boundary(
            generated_files[0],
            required=("#include <hpy.h>", "HPyType_FromSpec", "HPy_MODINIT"),
        )

        installed = temp / "installed"
        _run([
            python, "-m", "pip", "install", "--no-deps", "--target",
            str(installed), str(wheel),
        ], env=environment)
        runtime = environment.copy()
        runtime["PYTHONPATH"] = str(installed)
        _run([python, "-c", _runtime_program(False)], env=runtime)
        debug = runtime.copy()
        debug["HPY"] = "debug"
        _run([python, "-c", _runtime_program(True)], env=debug)

        dependencies = sorted(
            path for path in wheelhouse.glob("*.whl")
            if path != frontend_wheel)
        report = {
            "schema_version": 1,
            "frontend": {
                "distribution": AHPY_DISTRIBUTION,
                "version": AHPY_VERSION,
                "name": frontend_wheel.name,
                "sha256": _sha256(frontend_wheel),
            },
            "build_dependencies": [
                {"name": path.name, "sha256": _sha256(path)}
                for path in dependencies
            ],
            "wheel": {
                "name": wheel.name,
                "sha256": _sha256(wheel),
                "hpy_binary": binaries[0],
                "tags": tags,
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
    print("aHPy scikit-build-core integration passed: %s" %
          report["wheel"]["name"])


if __name__ == "__main__":
    main()
