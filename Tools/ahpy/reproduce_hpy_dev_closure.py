"""Run handwritten and generated HPy-development heap-type reproducers."""

import argparse
import os
from pathlib import Path
import signal
import shutil
import subprocess
from tempfile import TemporaryDirectory

from artifact_utils import require_universal_binary
from test_generated_hpy import verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests" / "ahpy" / "hpy_dev_closure_reproducer.pyx"
MODULE_NAME = "hpy_dev_closure_reproducer"
HANDWRITTEN_SOURCE = ROOT / "tests" / "ahpy" / "hpy_dev_type_reproducer.c"
HANDWRITTEN_MODULE_NAME = "hpy_dev_type_reproducer"


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def require_runtime_success(
        result, mode, subject="minimal generated closure"):
    if result.returncode == 0:
        return
    if result.returncode == -signal.SIGSEGV:
        raise AssertionError(
            "%s crashed with SIGSEGV in HPy %s mode" % (subject, mode)
        )
    raise AssertionError(
        "%s failed in HPy %s mode with exit status %d" %
        (subject, mode, result.returncode)
    )


def build_and_run(python):
    resolved_python = shutil.which(str(python))
    if resolved_python is None:
        raise FileNotFoundError("Python interpreter not found: %s" % python)
    python = str(Path(resolved_python).absolute())
    with TemporaryDirectory(prefix="ahpy-hpy-dev-closure-") as temp_dir:
        temp = Path(temp_dir)
        generated = temp / (MODULE_NAME + ".c")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        run([
            python,
            "-m", "cython",
            "--runtime-backend=hpy-universal",
            "-3",
            "-o", str(generated),
            str(SOURCE),
        ], cwd=ROOT, env=environment)
        verify_source_boundary(
            generated,
            required=(
                "#include <hpy.h>",
                "HPy_New",
                "HPyDef_METH",
                "HPyType_FromSpec",
                "HPy_mod_exec",
                "HPy_MODINIT",
            ),
        )
        verify_source_boundary(
            HANDWRITTEN_SOURCE,
            required=(
                "#include <hpy.h>",
                "HPy_New",
                "HPyType_FromSpec",
                "HPy_mod_exec",
                "HPy_MODINIT",
            ),
        )

        setup = temp / "setup.py"
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "from ahpy_hpy_compat import install_hpy_universal_loader_compat\n"
            "install_hpy_universal_loader_compat()\n"
            "setup(name='ahpy-hpy-dev-closure-reproducer', version='0.0.0', "
            "packages=[], py_modules=[], hpy_ext_modules=[Extension("
            "'hpy_dev_closure_reproducer', "
            "['hpy_dev_closure_reproducer.c']), Extension("
            "'hpy_dev_type_reproducer', [%r])])\n" %
            str(HANDWRITTEN_SOURCE),
            encoding="utf8",
        )
        build_root = temp / "build"
        run([
            python,
            str(setup),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)

        binary = require_universal_binary(build_root, MODULE_NAME)
        verify_binary_boundary(binary)
        handwritten_binary = require_universal_binary(
            build_root, HANDWRITTEN_MODULE_NAME)
        verify_binary_boundary(handwritten_binary)
        build_lib = binary.parent
        for module_name in (MODULE_NAME, HANDWRITTEN_MODULE_NAME):
            if not build_lib.joinpath(module_name + ".py").is_file():
                raise AssertionError(
                    "HPy Universal loader stub was not generated for %s" %
                    module_name
                )

        runtime_cases = (
            (
                "import hpy_dev_type_reproducer as module; "
                "marker = object(); instance = module.Reproducer(marker); "
                "assert instance.identity() is marker",
                "minimal handwritten HPy heap type",
            ),
            (
                "import hpy_dev_closure_reproducer as module; "
                "marker = object(); "
                "assert module.closure_roundtrip(marker) is marker",
                "minimal generated closure",
            ),
        )
        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(build_lib)
        for semantic_check, subject in runtime_cases:
            for mode in ("normal", "trace", "debug"):
                if mode == "normal":
                    runtime_environment.pop("HPY", None)
                else:
                    runtime_environment["HPY"] = mode
                result = subprocess.run(
                    [python, "-c", semantic_check],
                    cwd=temp,
                    env=runtime_environment,
                )
                require_runtime_success(result, mode, subject)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=str(ROOT / ".venv-hpy09/bin/python"))
    args = parser.parse_args()
    build_and_run(args.python)
    print(
        "minimal handwritten HPy type and generated closure: "
        "normal, Trace, and Debug passed"
    )


if __name__ == "__main__":
    main()
