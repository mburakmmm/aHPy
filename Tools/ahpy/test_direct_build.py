import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from direct_build import create_build_plan


ROOT = Path(__file__).resolve().parents[2]
DIRECT_BUILD = ROOT / "Tools" / "ahpy" / "direct_build.py"


def _probe(os_name="posix", root=None):
    windows = os_name == "nt"
    if root is None:
        runtime_source = "/hpy/runtime/helpers.c"
        static_library = "/hpy/lib/libhpy-extra-universal.a"
        include_dir = "/hpy/include"
        forbid_python_h = "/hpy/include/hpy/forbid_python_h"
    else:
        runtime_source = str(Path(root) / "helpers.c")
        static_library = str(Path(root) / "hpy-extra.lib" if windows else
                             Path(root) / "libhpy-extra-universal.a")
        Path(runtime_source).write_text("/* HPy runtime */\n", encoding="utf8")
        Path(static_library).touch()
        include_dir = str(Path(root) / "include")
        forbid_python_h = str(Path(root) / "forbid-python-h")
    return {
        "python": "/venv/python",
        "platform": "win32" if windows else "linux",
        "os_name": os_name,
        "machine": "x86_64",
        "hpy_version": "0.9.0",
        "extension_suffix": ".hpy0.pyd" if windows else ".hpy0.so",
        "include_dirs": [include_dir],
        "forbid_python_h": forbid_python_h,
        "runtime_sources": [runtime_source],
        "static_libraries": [static_library],
        "config": {
            "CC": "cl" if windows else "cc",
            "CFLAGS": "",
            "CCSHARED": "",
            "LDSHARED": "cc -shared",
            "LDFLAGS": "",
        },
    }


class DirectBuildTest(unittest.TestCase):
    def _source(self, temp):
        source = Path(temp) / "demo.c"
        source.write_text(
            "#include <hpy.h>\nHPy_MODINIT(demo, module)\n",
            encoding="utf8")
        return source

    def test_posix_static_plan_has_exact_universal_boundary(self):
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            probe = _probe(root=temp)
            plan = create_build_plan(
                probe, "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="static")
        command = plan["compile_commands"][0]
        self.assertEqual(plan["abi"], "universal")
        self.assertTrue(plan["artifact"].endswith("demo.hpy0.so"))
        self.assertIn("-DHPY", command)
        self.assertIn("-DHPY_ABI_UNIVERSAL", command)
        self.assertLess(
            command.index("-I" + probe["forbid_python_h"]),
            command.index("-I" + probe["include_dirs"][0]),
        )
        self.assertIn(
            str(Path(temp) / "libhpy-extra-universal.a"),
            plan["link_command"])

    def test_windows_plan_exports_hpy_initializer(self):
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            plan = create_build_plan(
                _probe("nt", temp), "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="static")
        self.assertTrue(plan["artifact"].endswith("demo.hpy0.pyd"))
        self.assertIn("/DHPY_ABI_UNIVERSAL", plan["compile_commands"][0])
        self.assertIn("/EXPORT:HPyInit_demo", plan["link_command"])

    def test_invalid_module_and_missing_static_runtime_fail_closed(self):
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            with self.assertRaisesRegex(ValueError, "plain C identifier"):
                create_build_plan(
                    _probe(root=temp), "bad.name", source, Path(temp) / "out",
                    Path(temp) / "build")
            probe = _probe(root=temp)
            probe["static_libraries"] = []
            with self.assertRaisesRegex(RuntimeError, "exactly one library"):
                create_build_plan(
                    probe, "demo", source, Path(temp) / "out",
                    Path(temp) / "build", runtime="static")
            helper = Path(temp) / "helper.c"
            helper.write_text("int helper(void) { return 0; }\n", encoding="utf8")
            probe["runtime_sources"] = [str(helper)]
            plan = create_build_plan(
                probe, "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="auto")
            self.assertEqual(plan["runtime_mode"], "sources")
            self.assertEqual(plan["runtime_inputs"], [str(helper)])

    def test_cli_imports_repository_modules_from_clean_working_directory(self):
        with TemporaryDirectory() as temp:
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, str(DIRECT_BUILD), "--help"],
                cwd=temp,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--plan-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
