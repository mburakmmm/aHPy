from pathlib import Path
import unittest

from ahpy_version import AHPY_DISTRIBUTION, AHPY_VERSION
from scikit_build_integration import EXAMPLE


class ScikitBuildDefinitionTest(unittest.TestCase):
    def test_isolated_project_pins_frontend_and_universal_generation(self):
        pyproject = (EXAMPLE / "pyproject.toml").read_text(encoding="utf8")
        cmake = (EXAMPLE / "CMakeLists.txt").read_text(encoding="utf8")
        self.assertIn(
            '"%s==%s"' % (AHPY_DISTRIBUTION, AHPY_VERSION), pyproject)
        self.assertIn('"scikit-build-core==1.0.3"', pyproject)
        self.assertIn('"cmake==4.3.4"', pyproject)
        self.assertIn('"ninja==1.13.0"', pyproject)
        self.assertIn("--runtime-backend=hpy-universal", cmake)
        self.assertIn("configure_ahpy.py", cmake)
        self.assertIn("${AHPY_EXTENSION_SUFFIX}", cmake)
        self.assertNotIn('"Cython', pyproject)
        integration = Path(__file__).with_name(
            "scikit_build_integration.py").read_text(encoding="utf8")
        self.assertIn('"setuptools==80.9.0"', integration)
        self.assertIn('isolated["PIP_NO_INDEX"] = "1"', integration)
        dependency_materialization = integration.split(
            '"hpy==0.9.0"', 1)[0].rsplit("[", 1)[-1]
        self.assertNotIn("--no-build-isolation", dependency_materialization)

    def test_loader_uses_public_hpy_load_and_runtime_mode(self):
        loader = (EXAMPLE / "ahpy_scikit_build_example.py").read_text(
            encoding="utf8")
        self.assertIn("_universal.load", loader)
        self.assertIn("MODE_DEBUG", loader)
        self.assertNotIn("_load_bootstrap", loader)


if __name__ == "__main__":
    unittest.main()
