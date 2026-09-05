import sys
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from Cython.Build import Dependencies

import ahpy_hpy_compat


LEGACY_TEMPLATE = """def __bootstrap__():
    from pkg_resources import resource_filename
    ext_filepath = resource_filename(__name__, {ext_file!r})
"""


class HPyCompatTest(unittest.TestCase):
    def test_minimal_setup_is_import_safe_without_hpy(self):
        root = Path(ahpy_hpy_compat.__file__).resolve().parent
        setup_path = root / "tests" / "ahpy" / "setup_minimal.py"
        program = (
            "import runpy, sys\n"
            "sys.path.insert(0, %r)\n"
            "sys.modules['hpy'] = None\n"
            "sys.modules['hpy.devel'] = None\n"
            "runpy.run_path(%r, run_name='ahpy_setup_fixture')\n"
        ) % (str(root), str(setup_path))
        subprocess.run(
            [sys.executable, "-I", "-c", program],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_default_hpy_module_is_loaded_and_repaired(self):
        hpy_module = ModuleType("hpy")
        hpy_module.__path__ = []
        devel_module = ModuleType("hpy.devel")
        devel_module._HPY_UNIVERSAL_MODULE_STUB_TEMPLATE = LEGACY_TEMPLATE
        hpy_module.devel = devel_module
        with mock.patch.dict(
                sys.modules,
                {"hpy": hpy_module, "hpy.devel": devel_module},
        ):
            self.assertTrue(
                ahpy_hpy_compat.install_hpy_universal_loader_compat())
            self.assertNotIn(
                "pkg_resources",
                devel_module._HPY_UNIVERSAL_MODULE_STUB_TEMPLATE,
            )

    def test_legacy_loader_template_is_repaired_once(self):
        devel = SimpleNamespace(
            _HPY_UNIVERSAL_MODULE_STUB_TEMPLATE=LEGACY_TEMPLATE)
        self.assertTrue(
            ahpy_hpy_compat.install_hpy_universal_loader_compat(devel))
        template = devel._HPY_UNIVERSAL_MODULE_STUB_TEMPLATE
        self.assertNotIn("pkg_resources", template)
        self.assertIn("from pathlib import Path", template)
        self.assertIn("Path(__file__).resolve().with_name", template)
        self.assertFalse(
            ahpy_hpy_compat.install_hpy_universal_loader_compat(devel))

    def test_partial_or_missing_template_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "partial HPy"):
            ahpy_hpy_compat.install_hpy_universal_loader_compat(
                SimpleNamespace(
                    _HPY_UNIVERSAL_MODULE_STUB_TEMPLATE=
                    ahpy_hpy_compat._LEGACY_IMPORT,
                )
            )
        with self.assertRaisesRegex(RuntimeError, "no Universal loader"):
            ahpy_hpy_compat.install_hpy_universal_loader_compat(
                SimpleNamespace())

    def test_missing_hpy_dependency_is_actionable(self):
        with (
            mock.patch.dict("sys.modules", {"hpy": None, "hpy.devel": None}),
            self.assertRaisesRegex(RuntimeError, "require the hpy package"),
        ):
            ahpy_hpy_compat.install_hpy_universal_loader_compat()

    def test_cythonize_installs_loader_compat_only_for_universal_hpy(self):
        install = mock.Mock()
        with (
            mock.patch.dict(
                Dependencies._runtime_backend_build_hooks,
                {"hpy-universal": install},
                clear=True,
            ),
            mock.patch.object(
                Dependencies, "CompilationOptions",
                side_effect=RuntimeError("stop after compatibility hook"),
            ),
            self.assertRaisesRegex(RuntimeError, "compatibility hook"),
        ):
            Dependencies.cythonize([], runtime_backend="hpy-universal")
        install.assert_called_once_with()

        install = mock.Mock()
        with (
            mock.patch.dict(
                Dependencies._runtime_backend_build_hooks,
                {"hpy-universal": install},
                clear=True,
            ),
            mock.patch.object(
                Dependencies, "CompilationOptions",
                side_effect=RuntimeError("stop before extension discovery"),
            ),
            self.assertRaisesRegex(RuntimeError, "extension discovery"),
        ):
            Dependencies.cythonize([])
        install.assert_not_called()

    def test_neutral_build_hook_registration_is_idempotent_and_fail_closed(self):
        hook = mock.Mock()
        with mock.patch.dict(
                Dependencies._runtime_backend_build_hooks, {}, clear=True):
            self.assertIs(
                Dependencies.register_runtime_backend_build_hook(
                    "hpy-universal", hook),
                hook,
            )
            self.assertIs(
                Dependencies.register_runtime_backend_build_hook(
                    "hpy-universal", hook),
                hook,
            )
            with self.assertRaisesRegex(ValueError, "different build hook"):
                Dependencies.register_runtime_backend_build_hook(
                    "hpy-universal", mock.Mock())
            with self.assertRaisesRegex(TypeError, "must be callable"):
                Dependencies.register_runtime_backend_build_hook(
                    "cpython", None)
            with self.assertRaisesRegex(Exception, "unknown runtime backend"):
                Dependencies.register_runtime_backend_build_hook(
                    "unknown-backend", hook)

    def test_ahpy_helper_is_registered_without_core_import_dependency(self):
        self.assertIs(
            Dependencies._runtime_backend_build_hooks["hpy-universal"],
            ahpy_hpy_compat.install_hpy_universal_loader_compat,
        )
        with open(Dependencies.__file__, encoding="utf8") as dependency_source:
            self.assertNotIn("ahpy_hpy_compat", dependency_source.read())

        root = str(Path(Dependencies.__file__).resolve().parents[2])
        program = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from Cython.Build import (cythonize, "
            "register_runtime_backend_build_hook)\n"
            "assert callable(cythonize)\n"
            "assert callable(register_runtime_backend_build_hook)\n"
            "assert not any(name.startswith('ahpy_') for name in sys.modules)\n"
        ) % root
        subprocess.run(
            [sys.executable, "-I", "-c", program],
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
