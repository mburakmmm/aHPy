from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_system_config import create_contract, render_cmake, render_meson
from test_direct_build import _probe


class BuildSystemConfigTest(unittest.TestCase):
    def test_static_contract_and_renderers_preserve_universal_boundary(self):
        with TemporaryDirectory() as temp:
            probe = _probe(root=temp)
            Path(probe["forbid_python_h"]).mkdir(parents=True)
            Path(probe["include_dirs"][0]).mkdir(parents=True)
            contract = create_contract(probe, "demo", "static")
        self.assertEqual(contract["abi"], "universal")
        self.assertEqual(contract["initializer"], "HPyInit_demo")
        self.assertEqual(contract["definitions"], ["HPY", "HPY_ABI_UNIVERSAL"])
        self.assertEqual(contract["runtime_mode"], "static")
        self.assertLess(
            contract["include_dirs"].index(probe["forbid_python_h"]),
            contract["include_dirs"].index(probe["include_dirs"][0]))
        cmake = render_cmake(contract)
        meson = render_meson(contract)
        self.assertIn('set(AHPY_ABI "universal")', cmake)
        self.assertIn('set(AHPY_EXTENSION_SUFFIX ".hpy0.so")', cmake)
        self.assertIn("ahpy_abi = 'universal'", meson)
        self.assertIn("ahpy_name_suffix = 'hpy0.so'", meson)

    def test_windows_and_source_runtime_contracts(self):
        with TemporaryDirectory() as temp:
            probe = _probe("nt", temp)
            Path(probe["forbid_python_h"]).mkdir(parents=True)
            Path(probe["include_dirs"][0]).mkdir(parents=True)
            contract = create_contract(probe, "demo", "sources")
        self.assertTrue(contract["is_windows"])
        self.assertEqual(contract["name_suffix"], "hpy0.pyd")
        self.assertEqual(contract["runtime_library"], "")
        self.assertEqual(contract["runtime_sources"], probe["runtime_sources"])
        self.assertIn("ahpy_windows = true", render_meson(contract))

    def test_invalid_module_fails_before_rendering(self):
        with TemporaryDirectory() as temp:
            probe = _probe(root=temp)
            with self.assertRaisesRegex(ValueError, "plain C identifier"):
                create_contract(probe, "bad.name")


if __name__ == "__main__":
    unittest.main()
