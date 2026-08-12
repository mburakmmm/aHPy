import sys
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
        with (
            mock.patch.object(
                ahpy_hpy_compat,
                "install_hpy_universal_loader_compat",
            ) as install,
            mock.patch.object(
                Dependencies, "CompilationOptions",
                side_effect=RuntimeError("stop after compatibility hook"),
            ),
            self.assertRaisesRegex(RuntimeError, "compatibility hook"),
        ):
            Dependencies.cythonize([], runtime_backend="hpy-universal")
        install.assert_called_once_with()

        with (
            mock.patch.object(
                ahpy_hpy_compat,
                "install_hpy_universal_loader_compat",
            ) as install,
            mock.patch.object(
                Dependencies, "CompilationOptions",
                side_effect=RuntimeError("stop before extension discovery"),
            ),
            self.assertRaisesRegex(RuntimeError, "extension discovery"),
        ):
            Dependencies.cythonize([])
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
