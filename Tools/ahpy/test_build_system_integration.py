from pathlib import Path
import unittest

from build_system_integration import EXAMPLES


class BuildSystemIntegrationDefinitionTest(unittest.TestCase):
    def test_cmake_example_consumes_only_generated_universal_contract(self):
        source = (EXAMPLES["cmake"][0] / "CMakeLists.txt").read_text(
            encoding="utf8")
        self.assertIn('include("${AHPY_CONFIG}")', source)
        self.assertIn('AHPY_ABI STREQUAL "universal"', source)
        self.assertIn("${AHPY_RUNTIME_SOURCES}", source)
        self.assertIn("${AHPY_RUNTIME_LIBRARY}", source)
        self.assertIn('SUFFIX "${AHPY_EXTENSION_SUFFIX}"', source)
        self.assertIn('"/EXPORT:${AHPY_INITIALIZER}"', source)

    def test_meson_example_consumes_only_generated_universal_contract(self):
        source = (EXAMPLES["meson"][0] / "meson.build").read_text(
            encoding="utf8")
        self.assertIn("subdir('ahpy_config')", source)
        self.assertIn("ahpy_abi != 'universal'", source)
        self.assertIn("ahpy_runtime_sources", source)
        self.assertIn("ahpy_runtime_library", source)
        self.assertIn("'vs_module_defs': files('exports.def')", source)

    def test_examples_do_not_commit_generated_contract_or_c(self):
        for example, module in EXAMPLES.values():
            self.assertFalse((example / (module + ".c")).exists())
            self.assertFalse((example / "ahpy_config").exists())


if __name__ == "__main__":
    unittest.main()
