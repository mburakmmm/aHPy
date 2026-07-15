from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scan_compatibility import (
    migration_action, parse_diagnostics, scan_sources, static_findings,
)


class CompatibilityScannerTest(unittest.TestCase):
    def test_diagnostic_parser_adds_source_position_and_action(self):
        output = (
            "/work/example.pyx:7:12: aHPy bootstrap backend: "
            "HPy 0.9 lacks a public generic iterator API; generator "
            "expressions cannot drive for-loops\n")
        diagnostics = parse_diagnostics(output)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["line"], 7)
        self.assertEqual(diagnostics[0]["column"], 12)
        self.assertEqual(diagnostics[0]["action"]["id"], "generic-iteration")
        self.assertIn("sequence-index iterable", diagnostics[0]["action"]["text"])

    def test_unknown_diagnostic_has_no_fallback_compilation_advice(self):
        action = migration_action("future unsupported construct")
        self.assertEqual(action["id"], "unsupported-universal-construct")
        self.assertIn("avoid CPython/Hybrid fallback", action["text"])

    def test_static_rules_detect_cpython_cimport_and_python_header(self):
        source = (
            "from cpython.object cimport PyObject\n"
            "cdef extern from \"Python.h\":\n"
            "    pass\n")
        findings = static_findings(Path("sample.pyx"), source)
        self.assertEqual(
            {finding["action"]["id"] for finding in findings},
            {"direct-cpython-cimport", "python-header"},
        )

    def test_static_rules_detect_pyobject_pointers_and_legacy_hpy_conversions(self):
        source = (
            "cdef PyObject *legacy_object\n"
            "cdef cpy_PyObject* compatibility_object\n"
            "value = HPy_FromPyObject(ctx, legacy_object)\n"
            "legacy_object = HPy_AsPyObject(ctx, value)\n"
        )
        findings = static_findings(Path("legacy.pyx"), source)
        action_ids = [finding["action"]["id"] for finding in findings]
        self.assertEqual(action_ids.count("direct-pyobject-pointer"), 2)
        self.assertEqual(action_ids.count("legacy-hpy-conversion"), 2)
        self.assertEqual(
            [(finding["line"], finding["column"]) for finding in findings],
            [(1, 6), (2, 6), (3, 9), (4, 17)],
        )

    def test_static_rules_ignore_comments_and_string_literals(self):
        source = (
            "# cdef PyObject *commented\n"
            "text = 'HPy_AsPyObject(ctx, value)'\n"
            "doc = \"\"\"\n"
            "cdef extern from \"Python.h\":\n"
            "    PyObject *inside_text\n"
            "\"\"\"\n"
            "def answer():\n"
            "    return 42\n"
        )
        self.assertEqual(static_findings(Path("clean.pyx"), source), [])

    def test_real_scan_classifies_supported_and_rejected_sources(self):
        import sys
        root = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            supported = temp / "supported.pyx"
            rejected = temp / "rejected.pyx"
            legacy = temp / "legacy.pyx"
            supported.write_text("def answer():\n    return 42\n", encoding="utf8")
            rejected.write_text("def values():\n    return {1, 2}\n", encoding="utf8")
            legacy.write_text("cdef PyObject *pointer\n", encoding="utf8")
            report = scan_sources(
                sys.executable, [supported, rejected, legacy], root=root)
        self.assertEqual(report["summary"]["compatible"], 1)
        self.assertEqual(report["summary"]["rejected"], 2)
        self.assertEqual(report["summary"]["compiler-error"], 0)
        self.assertEqual(
            report["sources"][1]["diagnostics"][0]["action"]["id"],
            "set-construction",
        )
        self.assertEqual(
            report["sources"][2]["diagnostics"][-1]["action"]["id"],
            "direct-pyobject-pointer",
        )


if __name__ == "__main__":
    unittest.main()
