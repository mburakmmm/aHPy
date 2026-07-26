import unittest

from setuptools_integration import EXTERNAL_HEADER, EXTERNAL_SOURCE, SETUP, SOURCE


class SetuptoolsIntegrationDefinitionTest(unittest.TestCase):
    def test_example_selects_backend_and_hpy_extension_lane(self):
        self.assertIn('runtime_backend="hpy-universal"', SETUP)
        self.assertIn("hpy_ext_modules=extensions", SETUP)
        self.assertIn("cdef class Box", SOURCE)
        self.assertIn('cdef extern from "ahpy_external.h"', SOURCE)
        self.assertIn("ahpy_external_nogil_probe() noexcept nogil", SOURCE)
        self.assertIn(
            "ahpy_external_nogil_advance(long long amount) noexcept nogil",
            SOURCE,
        )
        self.assertIn("def external_nogil_ordered(amount, /)", SOURCE)
        self.assertIn("def external_nogil_result(amount, /)", SOURCE)
        self.assertIn("def external_nogil_targets(obj, mapping, /)", SOURCE)
        self.assertIn("nogil_stored_result = 0", SOURCE)
        self.assertIn("mapping[1:2] = ahpy_external_nogil_advance(4)", SOURCE)
        self.assertIn("ahpy_external_nogil_probe_calls()", SOURCE)
        self.assertIn("ahpy_external_nogil_probe(void)", EXTERNAL_SOURCE)
        self.assertIn(
            "ahpy_external_nogil_advance(long long amount)",
            EXTERNAL_SOURCE,
        )
        self.assertIn("ahpy_external.c", SETUP)
        self.assertNotIn("Python.h", EXTERNAL_HEADER + EXTERNAL_SOURCE)
        compile(SETUP, "<ahpy-setuptools-setup>", "exec")


if __name__ == "__main__":
    unittest.main()
