#!/usr/bin/env python3
"""Exercise cythonize() plus HPy's setuptools Universal build integration."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "ahpy_setuptools_example"
EXAMPLE = ROOT / "examples" / "ahpy_setuptools"
SOURCE = (EXAMPLE / (MODULE_NAME + ".pyx")).read_text(encoding="utf8")
SETUP = (EXAMPLE / "setup.py").read_text(encoding="utf8")
EXTERNAL_HEADER = (EXAMPLE / "ahpy_external.h").read_text(encoding="utf8")
EXTERNAL_SOURCE = (EXAMPLE / "ahpy_external.c").read_text(encoding="utf8")


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
        "import ahpy_setuptools_example as module\n" +
        prefix +
        "assert module.answer() == 42\n"
        "assert module.external_signed_answer() == -42\n"
        "assert module.external_unsigned_answer() == 18446744073709551615\n"
        "assert module.external_ratio() == 0.125\n"
        "assert module.external_ready() is True\n"
        "assert module.external_add(20, 22) == 42\n"
        "events = []\n"
        "class Indexed:\n"
        "    def __init__(self, label, value):\n"
        "        self.label = label\n"
        "        self.value = value\n"
        "    def __index__(self):\n"
        "        events.append(self.label)\n"
        "        return self.value\n"
        "assert module.external_add(Indexed('left', 20), Indexed('right', 22)) == 42\n"
        "assert events == ['left', 'right']\n"
        "assert module.external_byte(-128) == -128\n"
        "assert module.external_scale(1.5, 4.0) == 6.0\n"
        "byte_calls = module.external_byte_calls()\n"
        "try:\n"
        "    module.external_byte(128)\n"
        "except OverflowError as error:\n"
        "    assert 'signed char' in str(error)\n"
        "else:\n"
        "    raise AssertionError('missing external C narrowing error')\n"
        "assert module.external_byte_calls() == byte_calls\n"
        "marker = object()\n"
        "box = module.Box(marker)\n"
        "assert box.value is marker\n"
        "assert box.identity() is marker\n"
        "del box\n" +
        suffix
    )


def build_and_run(python):
    with TemporaryDirectory(prefix="ahpy-setuptools-integration-") as temp_dir:
        temp = Path(temp_dir)
        source = temp / (MODULE_NAME + ".pyx")
        setup = temp / "setup.py"
        external_header = temp / "ahpy_external.h"
        external_source = temp / "ahpy_external.c"
        source.write_text(SOURCE, encoding="utf8")
        setup.write_text(SETUP, encoding="utf8")
        external_header.write_text(EXTERNAL_HEADER, encoding="utf8")
        external_source.write_text(EXTERNAL_SOURCE, encoding="utf8")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        build_root = temp / "build"
        run([
            python,
            str(setup),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)

        generated = temp / (MODULE_NAME + ".c")
        verify_source_boundary(
            generated,
            required=(
                "#include <hpy.h>", "HPyDef_METH", "HPyType_FromSpec",
                "HPy_MODINIT", '#include "ahpy_external.h"',
                "HPyLong_FromUnsignedLongLong",
            ),
        )
        binaries = list(build_root.rglob(MODULE_NAME + "*.hpy0.*"))
        if len(binaries) != 1:
            raise AssertionError("expected one .hpy0 binary, got %r" % binaries)
        verify_binary_boundary(binaries[0])

        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(binaries[0].parent)
        run([
            python, "-c", _runtime_program(False),
        ], cwd=temp, env=runtime_environment)
        debug_environment = runtime_environment.copy()
        debug_environment["HPY"] = "debug"
        run([
            python, "-c", _runtime_program(True),
        ], cwd=temp, env=debug_environment)

        dist = temp / "dist"
        run([
            python,
            str(setup),
            "--hpy-abi=universal",
            "bdist_wheel",
            "--dist-dir", str(dist),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        wheels = list(dist.glob("*.whl"))
        if len(wheels) != 1:
            raise AssertionError("expected one wheel, got %r" % wheels)
        with zipfile.ZipFile(wheels[0]) as archive:
            members = archive.namelist()
            hpy_binaries = [name for name in members if ".hpy0." in name]
            stubs = [name for name in members if name == MODULE_NAME + ".py"]
            wheel_metadata = next(
                name for name in members if name.endswith(".dist-info/WHEEL"))
            metadata = archive.read(wheel_metadata).decode("utf8")
        if len(hpy_binaries) != 1 or len(stubs) != 1:
            raise AssertionError(
                "wheel must contain one .hpy0 binary and loader stub: %r" %
                members)
        tags = sorted(
            line.removeprefix("Tag: ")
            for line in metadata.splitlines() if line.startswith("Tag: "))
        if not tags:
            raise AssertionError("wheel metadata has no compatibility tag")

        installed = temp / "installed"
        run([
            python,
            "-m", "pip", "install",
            "--no-deps",
            "--target", str(installed),
            str(wheels[0]),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        installed_environment = environment.copy()
        installed_environment["PYTHONPATH"] = str(installed)
        run([
            python, "-c", _runtime_program(False),
        ], cwd=temp, env=installed_environment)
        return {"wheel": wheels[0].name, "tags": tags}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    selected = Path(args.python)
    if selected.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    wheel = build_and_run(python)
    print(
        "aHPy setuptools/cythonize Universal integration passed; "
        "wheel=%s tags=%s" % (wheel["wheel"], ",".join(wheel["tags"])))


if __name__ == "__main__":
    main()
