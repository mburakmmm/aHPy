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

from artifact_utils import require_universal_binary
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
        "import errno\n"
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
        "nogil_calls = module.external_nogil_probe()\n"
        "assert nogil_calls >= 1\n"
        "assert module.external_nogil_probe() == nogil_calls + 1\n"
        "nogil_calls = module.external_nogil_advance(3)\n"
        "assert nogil_calls >= 4\n"
        "class BadIndex:\n"
        "    def __index__(self):\n"
        "        raise RuntimeError('nogil conversion failed')\n"
        "try:\n"
        "    module.external_nogil_advance(BadIndex())\n"
        "except RuntimeError as error:\n"
        "    assert str(error) == 'nogil conversion failed'\n"
        "else:\n"
        "    raise AssertionError('missing pre-nogil conversion error')\n"
        "assert module.external_nogil_probe() == nogil_calls + 1\n"
        "ordered_base = module.external_nogil_calls()\n"
        "class OrderedIndex:\n"
        "    def __index__(self):\n"
        "        assert module.external_nogil_calls() == ordered_base + 1\n"
        "        return 3\n"
        "assert module.external_nogil_ordered(OrderedIndex()) == ordered_base + 4\n"
        "result_base = module.external_nogil_calls()\n"
        "assert module.external_nogil_result(5) == result_base + 5\n"
        "assert module.external_nogil_calls() == result_base + 5\n"
        "target_base = module.external_nogil_calls()\n"
        "class Target:\n"
        "    pass\n"
        "target = Target()\n"
        "target.amount = 1\n"
        "class Mapping:\n"
        "    item = 2\n"
        "    slice_item = None\n"
        "    def __getitem__(self, key):\n"
        "        return self.slice_item if isinstance(key, slice) else self.item\n"
        "    def __setitem__(self, key, value):\n"
        "        if isinstance(key, slice):\n"
        "            self.slice_item = value\n"
        "        else:\n"
        "            self.item = value\n"
        "mapping = Mapping()\n"
        "assert module.external_nogil_targets(target, mapping) == (\n"
        "    target_base + 1, target_base + 3, target_base + 6,\n"
        "    target_base + 10, target_base + 10)\n"
        "assert module.nogil_stored_result == target_base + 1\n"
        "assert target.value == target_base + 3\n"
        "assert mapping.item == target_base + 6\n"
        "assert mapping.slice_item == target_base + 10\n"
        "gil_base = module.external_nogil_calls()\n"
        "gil_events = []\n"
        "def gil_callback(before):\n"
        "    gil_events.append(before)\n"
        "    assert module.external_nogil_calls() == gil_base + 1\n"
        "    return 2\n"
        "assert module.external_nogil_with_gil(gil_callback) == (\n"
        "    gil_base + 1, 2, gil_base + 3)\n"
        "assert gil_events == [gil_base + 1]\n"
        "gil_failure_base = module.external_nogil_calls()\n"
        "def failing_gil_callback(before):\n"
        "    assert before == gil_failure_base + 1\n"
        "    assert module.external_nogil_calls() == gil_failure_base + 1\n"
        "    raise ValueError('nested with gil failed')\n"
        "try:\n"
        "    module.external_nogil_with_gil(failing_gil_callback)\n"
        "except ValueError as error:\n"
        "    assert str(error) == 'nested with gil failed'\n"
        "else:\n"
        "    raise AssertionError('missing nested with gil failure')\n"
        "assert module.external_nogil_calls() == gil_failure_base + 1\n"
        "errno_base = module.external_nogil_calls()\n"
        "assert module.external_errno_held(2) == errno_base + 2\n"
        "assert module.external_errno_released(3) == errno_base + 5\n"
        "assert module.external_errno_discarded(4) == errno_base + 9\n"
        "for failing_call in (\n"
        "    module.external_errno_held,\n"
        "    module.external_errno_released,\n"
        "    module.external_errno_discarded,\n"
        "):\n"
        "    try:\n"
        "        failing_call(-1)\n"
        "    except OSError as error:\n"
        "        assert error.errno == errno.EDOM\n"
        "    else:\n"
        "        raise AssertionError('missing external C errno failure')\n"
        "assert module.external_nogil_calls() == errno_base + 9\n"
        "try:\n"
        "    module.external_missing_errno()\n"
        "except RuntimeError as error:\n"
        "    assert str(error) == (\n"
        "        \"external C function 'ahpy_external_missing_errno' returned \"\n"
        "        \"its -1 error sentinel without setting errno\")\n"
        "else:\n"
        "    raise AssertionError('missing unset-errno contract failure')\n"
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
                "HPyThreadState", "HPy_LeavePythonExecution",
                "HPy_ReenterPythonExecution", "ahpy_external_nogil_advance",
                "explicit with gil: Python execution is active",
                "#include <errno.h>", "HPyErr_SetFromErrno",
            ),
        )
        binary = require_universal_binary(build_root, MODULE_NAME)
        verify_binary_boundary(binary)

        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(binary.parent)
        run([
            python, "-c", _runtime_program(False),
        ], cwd=temp, env=runtime_environment)
        trace_environment = runtime_environment.copy()
        trace_environment["HPY"] = "trace"
        run([
            python, "-c", _runtime_program(False),
        ], cwd=temp, env=trace_environment)
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
