import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

import scan_compatibility
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
        action = migration_action(
            "external C calls inside with nogil must be argumentless")
        self.assertEqual(action["id"], "nogil-transition")
        self.assertIn("ADR 0010", action["text"])
        action = migration_action(
            "prange/parallel requires a public HPy worker-thread attach")
        self.assertEqual(action["id"], "parallel-worker-contract")
        self.assertIn("ADR 0011", action["text"])
        action = migration_action(
            "module-level FromCImportStatNode is not implemented by the emitter")
        self.assertEqual(action["id"], "cython-module-cimport")
        self.assertIn("ordinary Python boundary", action["text"])
        action = migration_action(
            "module-level CFuncDefNode is not implemented by the emitter")
        self.assertEqual(action["id"], "compiled-entry-point")
        self.assertIn("entry point as def", action["text"])
        action = migration_action(
            "cpython.* cimports expose the CPython C API and are unavailable")
        self.assertEqual(action["id"], "direct-cpython-cimport")

    def test_static_rule_detects_relative_cython_module_cimport_only(self):
        source = (
            "from .utils cimport axpy\n"
            "from ..shared.math cimport scale\n"
            "from libc.stdint cimport uint64_t\n"
            "import local_python_module\n"
        )
        findings = static_findings(Path("module_boundary.pyx"), source)
        self.assertEqual(
            [finding["action"]["id"] for finding in findings],
            ["cython-module-cimport", "cython-module-cimport"],
        )
        self.assertEqual(
            [(finding["line"], finding["column"]) for finding in findings],
            [(1, 1), (2, 1)],
        )

    def test_static_rule_detects_cpp_runtime_cimports(self):
        source = (
            "from libcpp.atomic cimport atomic\n"
            "cimport libcpp.vector\n"
            "import libcpp_at_python_level\n"
        )
        findings = static_findings(Path("cpp_boundary.pyx"), source)
        self.assertEqual(
            [finding["action"]["id"] for finding in findings],
            ["cpp-runtime-boundary", "cpp-runtime-boundary"],
        )
        self.assertTrue(all(
            "C-compatible shim" in finding["action"]["text"]
            for finding in findings))

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

    def test_static_rules_detect_numpy_c_api_cimports_only(self):
        source = (
            "import numpy as np\n"
            "from numpy cimport ndarray as ndarray_t\n"
            "cimport numpy.random\n"
        )
        findings = static_findings(Path("numpy_boundary.pyx"), source)
        self.assertEqual(
            [finding["action"]["id"] for finding in findings],
            ["numpy-c-api", "numpy-c-api"],
        )
        self.assertEqual(
            [(finding["line"], finding["column"]) for finding in findings],
            [(2, 1), (3, 1)],
        )
        self.assertTrue(all(
            "ordinary Python object boundary" in finding["action"]["text"]
            for finding in findings
        ))

    def test_static_rule_detects_native_void_pointer_boundary(self):
        source = (
            'cdef extern from "native.h":\n'
            '    int consume(const void *data, void* output) noexcept\n'
        )
        findings = static_findings(Path("pointer.pyx"), source)
        self.assertEqual(
            [finding["action"]["id"] for finding in findings],
            ["native-pointer-boundary", "native-pointer-boundary"],
        )
        self.assertEqual(
            [(finding["line"], finding["column"]) for finding in findings],
            [(2, 23), (2, 35)],
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

    def test_masking_tolerates_malformed_token_stream(self):
        source = "text = '''unterminated\ncdef PyObject *hidden\n"
        masked = scan_compatibility._mask_comments_and_strings(source)
        self.assertEqual(len(masked), len(source))
        self.assertEqual(masked.count("\n"), source.count("\n"))

    def _scan_with_result(
            self, root, source_text, result, generated_text=None):
        source = root / "sample.pyx"
        source.write_text(source_text, encoding="utf8")

        def run(command, **options):
            if generated_text is not None:
                output = Path(command[command.index("-o") + 1])
                output.write_text(generated_text, encoding="utf8")
            return result

        with mock.patch.object(
                scan_compatibility.subprocess, "run",
                side_effect=run):
            return scan_compatibility.scan_source(
                "/tool/python", source, root / "generated", root=root)

    def test_scan_source_classifies_success_rejection_and_compiler_errors(self):
        with TemporaryDirectory(prefix="ahpy-compat-scan-") as temp:
            root = Path(temp)
            generated = root / "generated"
            generated.mkdir()
            success = SimpleNamespace(returncode=0, stdout="", stderr="")
            report = self._scan_with_result(
                root,
                "def answer():\n    return 42\n",
                success,
                "#include <hpy.h>\n",
            )
            self.assertEqual(report["status"], "compatible")
            self.assertEqual(report["diagnostics"], [])

            report = self._scan_with_result(
                root,
                "cdef PyObject *pointer\n",
                success,
            )
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(
                report["diagnostics"][0]["action"]["id"],
                "direct-pyobject-pointer",
            )

            compiler_failure = SimpleNamespace(
                returncode=1, stdout="", stderr="plain compiler failure")
            report = self._scan_with_result(
                root,
                "def answer():\n    return 42\n",
                compiler_failure,
            )
            self.assertEqual(report["status"], "compiler-error")
            self.assertEqual(
                report["diagnostics"][0]["action"]["id"], "compiler-error")
            self.assertEqual(
                report["diagnostics"][0]["message"],
                "plain compiler failure",
            )

            diagnostic_failure = SimpleNamespace(
                returncode=1,
                stdout="",
                stderr=(
                    "%s:1:1: aHPy bootstrap backend: "
                    "set construction is unavailable\n" % (root / "sample.pyx")
                ),
            )
            report = self._scan_with_result(
                root,
                "def answer():\n    return 42\n",
                diagnostic_failure,
            )
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(
                report["diagnostics"][0]["action"]["id"],
                "set-construction",
            )

    def test_scan_source_rejects_generated_header_boundary_drift(self):
        with TemporaryDirectory(prefix="ahpy-compat-scan-") as temp:
            root = Path(temp)
            (root / "generated").mkdir()
            result = SimpleNamespace(returncode=0, stdout="", stderr="")
            for generated in (
                    "#include <Python.h>\n",
                    "/* missing HPy header */\n"):
                with self.subTest(generated=generated):
                    report = self._scan_with_result(
                        root,
                        "def answer():\n    return 42\n",
                        result,
                        generated,
                    )
                    self.assertEqual(report["status"], "compiler-error")
                    self.assertEqual(
                        report["diagnostics"][0]["action"]["id"],
                        "report-backend-boundary-bug",
                    )

    def test_scan_sources_aggregates_all_statuses(self):
        reports = [
            {"path": "a.pyx", "status": "compatible", "diagnostics": []},
            {"path": "b.pyx", "status": "rejected", "diagnostics": []},
            {"path": "c.pyx", "status": "compiler-error", "diagnostics": []},
        ]
        with mock.patch.object(
                scan_compatibility, "scan_source",
                side_effect=reports) as scan:
            report = scan_sources(
                "/tool/python", ["a.pyx", "b.pyx", "c.pyx"])
        self.assertEqual(scan.call_count, 3)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["backend"], "hpy-universal")
        self.assertEqual(report["summary"], {
            "total": 3,
            "compatible": 1,
            "rejected": 1,
            "compiler-error": 1,
        })

    def test_text_report_renders_positions_and_actions(self):
        report = {
            "summary": {
                "compatible": 0,
                "rejected": 1,
                "compiler-error": 0,
            },
            "sources": [{
                "path": "sample.pyx",
                "status": "rejected",
                "diagnostics": [{
                    "path": "sample.pyx",
                    "line": 7,
                    "column": 12,
                    "message": "unsupported",
                    "action": {"id": "port", "text": "rewrite"},
                }, {
                    "path": "sample.pyx",
                    "line": None,
                    "column": None,
                    "message": "compiler detail",
                    "action": {"id": "report", "text": "preserve"},
                }],
            }],
        }
        text = scan_compatibility.render_text(report)
        self.assertIn("[REJECTED] sample.pyx", text)
        self.assertIn("sample.pyx:7:12: unsupported", text)
        self.assertIn("action port: rewrite", text)
        self.assertIn("sample.pyx: compiler detail", text)

    def test_main_reports_json_text_and_exit_statuses(self):
        reports = (
            ({
                "summary": {
                    "compatible": 1, "rejected": 0, "compiler-error": 0},
                "sources": [],
            }, [], 0),
            ({
                "summary": {
                    "compatible": 0, "rejected": 1, "compiler-error": 0},
                "sources": [],
            }, [], 1),
            ({
                "summary": {
                    "compatible": 0, "rejected": 1, "compiler-error": 0},
                "sources": [],
            }, ["--allow-rejected"], 0),
            ({
                "summary": {
                    "compatible": 0, "rejected": 0, "compiler-error": 1},
                "sources": [],
            }, ["--json"], 2),
        )
        with TemporaryDirectory(prefix="ahpy-compat-main-") as temp:
            root = Path(temp)
            python = root / "python"
            source = root / "source.pyx"
            python.touch()
            source.touch()
            for report, flags, expected in reports:
                with (
                    self.subTest(flags=flags),
                    mock.patch.object(sys, "argv", [
                        "scan_compatibility.py",
                        "--python", str(python),
                        *flags,
                        str(source),
                    ]),
                    mock.patch.object(
                        scan_compatibility, "scan_sources",
                        return_value=report) as scan,
                    mock.patch("builtins.print") as printed,
                ):
                    self.assertEqual(scan_compatibility.main(), expected)
                scan.assert_called_once_with(
                    os.path.abspath(python), [str(source)],
                    root=scan_compatibility.ROOT)
                self.assertEqual(printed.call_count, 1)
                if "--json" in flags:
                    json.loads(printed.call_args.args[0])

    def test_main_resolves_path_and_rejects_missing_inputs(self):
        with TemporaryDirectory(prefix="ahpy-compat-main-") as temp:
            source = Path(temp) / "source.pyx"
            source.touch()
            report = {
                "summary": {
                    "compatible": 1, "rejected": 0, "compiler-error": 0},
                "sources": [],
            }
            with (
                mock.patch.object(sys, "argv", [
                    "scan_compatibility.py",
                    "--python", "reviewed-python",
                    str(source),
                ]),
                mock.patch.object(
                    scan_compatibility.shutil, "which",
                    return_value="/tool/python"),
                mock.patch.object(
                    scan_compatibility, "scan_sources",
                    return_value=report) as scan,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(scan_compatibility.main(), 0)
            scan.assert_called_once_with(
                "/tool/python", [str(source)], root=scan_compatibility.ROOT)

        cases = (
            (
                [
                    "scan_compatibility.py",
                    "--python", "missing-python",
                    "source.pyx",
                ],
                None,
            ),
            (
                [
                    "scan_compatibility.py",
                    "--python", sys.executable,
                    "missing.pyx",
                ],
                sys.executable,
            ),
        )
        for argv, resolved in cases:
            with (
                self.subTest(argv=argv),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    scan_compatibility.shutil, "which",
                    return_value=resolved),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                scan_compatibility.main()
            self.assertEqual(raised.exception.code, 2)

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
