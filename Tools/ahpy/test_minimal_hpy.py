"""Build and execute the handwritten Universal HPy reference module."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from artifact_utils import require_universal_binary


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "tests" / "ahpy" / "setup_minimal.py"
SOURCE = ROOT / "tests" / "ahpy" / "minimal_universal.c"


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def verify_source_boundary():
    source = SOURCE.read_text(encoding="utf8")
    forbidden = (
        "#include <Python.h>",
        "PyObject *",
        "struct PyMethodDef",
        "struct PyModuleDef",
    )
    found = [name for name in forbidden if name in source]
    if found:
        raise AssertionError("legacy C API spellings found: %s" % ", ".join(found))
    required = (
        "#include <hpy.h>",
        "HPy_MODINIT",
        "HPyDef_METH",
        "HPyFunc_KEYWORDS",
        "HPy_Length",
        "HPyImport_ImportModule",
        "HPy_Call",
    )
    missing = [name for name in required if name not in source]
    if missing:
        raise AssertionError("required HPy spellings missing: %s" % ", ".join(missing))


def build_and_run(python):
    verify_source_boundary()
    with TemporaryDirectory(prefix="ahpy-hpy09-") as temp_dir:
        temp = Path(temp_dir)
        build_root = temp / "build"
        run([
            python,
            str(SETUP),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build_root),
        ], cwd=SETUP.parent)

        binary = require_universal_binary(build_root, "ahpy_minimal")
        build_lib = binary.parent
        if not build_lib.joinpath("ahpy_minimal.py").exists():
            raise AssertionError("HPy universal loader stub was not generated")

        semantic_check = (
            "import ahpy_minimal; "
            "assert ahpy_minimal.answer() == 42; "
            "assert ahpy_minimal.return_none() is None; "
            "assert ahpy_minimal.make_pair() == [1, 2]; "
            "assert ahpy_minimal.keyword_count(42) == 0; "
            "assert ahpy_minimal.keyword_count(value=42) == 1; "
            "assert ahpy_minimal.range_length(0) == 0; "
            "assert ahpy_minimal.range_length(3) == 3"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(build_lib)
        run([python, "-c", semantic_check], cwd=temp, env=env)
        env["HPY"] = "debug"
        debug_check = (
            "from hpy.debug import LeakDetector; "
            "import ahpy_minimal; "
            "detector = LeakDetector(); detector.start(); "
            "assert ahpy_minimal.answer() == 42; "
            "assert ahpy_minimal.return_none() is None; "
            "assert ahpy_minimal.make_pair() == [1, 2]; "
            "assert ahpy_minimal.keyword_count(42) == 0; "
            "assert ahpy_minimal.keyword_count(value=42) == 1; "
            "assert ahpy_minimal.range_length(0) == 0; "
            "assert ahpy_minimal.range_length(3) == 3; "
            "detector.stop()"
        )
        run([python, "-c", debug_check], cwd=temp, env=env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python",
        default=str(ROOT / ".venv-hpy09" / "bin" / "python"),
        help="Python interpreter containing HPy 0.9.0",
    )
    args = parser.parse_args()
    build_and_run(args.python)
    print("Universal HPy reference module: normal and debug modes passed")


if __name__ == "__main__":
    main()
