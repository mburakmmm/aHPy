import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import cypack_pilot_integration
from pilot_performance import validate_performance


class CypackPilotIntegrationTest(unittest.TestCase):
    def test_runtime_program_covers_selected_upstream_semantics_and_debug(self):
        normal = cypack_pilot_integration._runtime_program(False)
        self.assertIn("assert the_answer() == 42", normal)
        self.assertIn("assert fib(7) == 13", normal)
        self.assertIn(cypack_pilot_integration.EXPECTED_ZEN_MD5, normal)
        self.assertNotIn("LeakDetector", normal)

        debug = cypack_pilot_integration._runtime_program(True)
        self.assertIn("LeakDetector", debug)
        self.assertIn("detector.start()", debug)
        self.assertTrue(debug.endswith("detector.stop()\n"))

    def test_build_root_requires_package_layout(self):
        self.assertEqual(
            cypack_pilot_integration._build_root(
                Path("/build/lib/cypack/answer.hpy0.so")),
            Path("/build/lib"),
        )
        with self.assertRaisesRegex(AssertionError, "unexpected cypack"):
            cypack_pilot_integration._build_root(
                Path("/build/lib/other/answer.hpy0.so"))

    def test_only_wheel_fails_closed_on_missing_or_ambiguous_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-cypack-wheels-") as temp:
            dist = Path(temp)
            with self.assertRaisesRegex(AssertionError, "exactly one"):
                cypack_pilot_integration._only_wheel(dist)
            (dist / "one.whl").touch()
            self.assertEqual(
                cypack_pilot_integration._only_wheel(dist),
                dist / "one.whl")
            (dist / "two.whl").touch()
            with self.assertRaisesRegex(AssertionError, "exactly one"):
                cypack_pilot_integration._only_wheel(dist)

    def test_performance_report_validation_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, "must be an object"):
            validate_performance([])
        with tempfile.TemporaryDirectory(prefix="ahpy-cypack-performance-") as temp:
            path = Path(temp) / "performance.json"
            path.write_text("{}", encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "schema_version"):
                cypack_pilot_integration._read_performance(path)
            path.write_text(json.dumps({
                "schema_version": 1,
                "environment": {
                    name: "value" for name in (
                        "python_implementation", "python_version",
                        "hpy_version", "platform", "machine")
                },
                "workloads": {
                    "axpy": {},
                    "fibonacci": {},
                },
            }), encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "sampling contract"):
                cypack_pilot_integration._read_performance(path)

    def test_performance_report_rejects_malformed_provenance_and_values(self):
        valid_workload = {
            "iterations": 100,
            "repeats": 7,
            "compiled_ns_per_call": 10.0,
            "python_reference_ns_per_call": 20.0,
            "compiled_to_python_ratio": 0.5,
        }
        environment = {
            name: "value" for name in (
                "python_implementation", "python_version", "hpy_version",
                "platform", "machine")
        }
        with tempfile.TemporaryDirectory(prefix="ahpy-cypack-performance-") as temp:
            path = Path(temp) / "performance.json"
            path.write_text("{", encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "invalid pilot"):
                cypack_pilot_integration._read_performance(path)
            path.write_text(json.dumps({
                "schema_version": 1,
                "environment": {},
                "workloads": {},
            }), encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "environment"):
                cypack_pilot_integration._read_performance(path)
            path.write_text(json.dumps({
                "schema_version": 1,
                "environment": environment,
                "workloads": {"axpy": valid_workload},
            }), encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "workloads"):
                cypack_pilot_integration._read_performance(path)
            path.write_text(json.dumps({
                "schema_version": 1,
                "environment": environment,
                "workloads": {
                    "axpy": [],
                    "fibonacci": valid_workload,
                },
            }), encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "performance workload"):
                cypack_pilot_integration._read_performance(path)
            invalid = dict(valid_workload, compiled_ns_per_call=float("inf"))
            path.write_text(json.dumps({
                "schema_version": 1,
                "environment": environment,
                "workloads": {
                    "axpy": invalid,
                    "fibonacci": valid_workload,
                },
            }), encoding="utf8")
            with self.assertRaisesRegex(AssertionError, "performance field"):
                cypack_pilot_integration._read_performance(path)

    def test_wheel_audit_rejects_incomplete_contents_and_metadata(self):
        def write_wheel(path, *, binaries=3, stubs=3, data=True,
                        metadata=True, tag=True):
            with zipfile.ZipFile(path, "w") as archive:
                modules = ("utils", "answer", "fibonacci")
                for module in modules[:binaries]:
                    archive.writestr(f"cypack/{module}.hpy0.so", b"binary")
                for module in modules[:stubs]:
                    archive.writestr(f"cypack/{module}.py", "# loader\n")
                if data:
                    archive.writestr("cypack/data/zen.txt", "Zen\n")
                if metadata:
                    contents = "Wheel-Version: 1.0\n"
                    if tag:
                        contents += "Tag: py3-none-any\n"
                    archive.writestr(
                        "ahpy_cypack_pilot-0.1.7.dist-info/WHEEL", contents)

        with tempfile.TemporaryDirectory(prefix="ahpy-cypack-wheel-audit-") as temp:
            wheel = Path(temp) / "pilot.whl"
            cases = (
                ({"metadata": False}, "one WHEEL"),
                ({"binaries": 2}, "three .hpy0"),
                ({"data": False}, "missing cypack/data"),
                ({"tag": False}, "no compatibility tag"),
            )
            for options, message in cases:
                with self.subTest(message=message):
                    write_wheel(wheel, **options)
                    with self.assertRaisesRegex(AssertionError, message):
                        cypack_pilot_integration._audit_wheel(wheel)

    def _binary(self, build, module):
        binary = Path(build) / "lib" / "cypack" / (
            module.rsplit(".", 1)[-1] + ".hpy0.so")
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.touch()
        return binary

    def test_build_and_run_records_all_gates_and_optional_output(self):
        def fake_run(command, **options):
            performance = options.get("env", {}).get(
                "AHPY_PILOT_PERFORMANCE_OUTPUT")
            if performance:
                Path(performance).write_text(json.dumps({
                    "schema_version": 1,
                    "environment": {
                        name: "value" for name in (
                            "python_implementation", "python_version",
                            "hpy_version", "platform", "machine")
                    },
                    "workloads": {
                        name: {
                            "iterations": 100,
                            "repeats": 7,
                            "compiled_ns_per_call": 10.0,
                            "python_reference_ns_per_call": 20.0,
                            "compiled_to_python_ratio": 0.5,
                        }
                        for name in ("axpy", "fibonacci")
                    },
                }), encoding="utf8")
            if "bdist_wheel" not in command:
                return
            dist = Path(command[command.index("--dist-dir") + 1])
            dist.mkdir(parents=True)
            wheel = dist / "ahpy_cypack_pilot-0.1.7-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for module in ("utils", "answer", "fibonacci"):
                    archive.writestr(
                        f"cypack/{module}.hpy0.so", b"binary")
                    archive.writestr(f"cypack/{module}.py", "# loader\n")
                archive.writestr("cypack/data/zen.txt", "Zen\n")
                archive.writestr(
                    "ahpy_cypack_pilot-0.1.7.dist-info/WHEEL",
                    "Wheel-Version: 1.0\nTag: py3-none-any\n")

        with tempfile.TemporaryDirectory(prefix="ahpy-cypack-test-") as temp:
            output = Path(temp) / "nested" / "report.json"
            with mock.patch.object(
                        cypack_pilot_integration, "run",
                        side_effect=fake_run) as run, \
                    mock.patch.object(
                        cypack_pilot_integration,
                        "verify_source_boundary") as source_audit, \
                    mock.patch.object(
                        cypack_pilot_integration,
                        "verify_binary_boundary") as binary_audit, \
                    mock.patch.object(
                        cypack_pilot_integration,
                        "require_universal_binary",
                        side_effect=self._binary), \
                    mock.patch.object(
                        cypack_pilot_integration.time,
                        "monotonic",
                        side_effect=range(22)):
                report = cypack_pilot_integration.build_and_run(
                    "/venv/bin/python", output)
            stored = json.loads(output.read_text(encoding="utf8"))

        self.assertEqual(report["pilot"], "cypack-pure-cython")
        self.assertEqual(report["upstream_commit"],
                         cypack_pilot_integration.UPSTREAM_COMMIT)
        self.assertEqual(set(report["gates"].values()), {"pass"})
        self.assertEqual(report["timings_seconds"]["build"], 1)
        self.assertEqual(report["timings_seconds"]["wheel_build"], 1)
        self.assertEqual(report["timings_seconds"]["wheel_install"], 1)
        self.assertEqual(report["timings_seconds"]["performance"], 1)
        self.assertEqual(report["timings_seconds"]["total"], 21)
        self.assertEqual(stored["artifacts"]["binaries"], [
            "utils.hpy0.so", "answer.hpy0.so", "fibonacci.hpy0.so"])
        self.assertEqual(
            stored["artifacts"]["wheel"],
            "ahpy_cypack_pilot-0.1.7-py3-none-any.whl")
        self.assertEqual(stored["artifacts"]["wheel_tags"], ["py3-none-any"])
        self.assertEqual(
            report["performance"]["comparison"],
            "compiled-port-to-equivalent-python")
        self.assertFalse(report["performance"]["budget_enforced"])
        self.assertEqual(run.call_count, 10)
        self.assertEqual(source_audit.call_count, 3)
        self.assertEqual(binary_audit.call_count, 3)

    def test_build_rejects_binaries_spread_across_roots(self):
        def binary(build, module):
            name = module.rsplit(".", 1)[-1]
            return Path(build) / name / "cypack" / (name + ".hpy0.so")

        with mock.patch.object(cypack_pilot_integration, "run"), \
                mock.patch.object(
                    cypack_pilot_integration, "verify_source_boundary"), \
                mock.patch.object(
                    cypack_pilot_integration, "verify_binary_boundary"), \
                mock.patch.object(
                    cypack_pilot_integration,
                    "require_universal_binary",
                    side_effect=binary):
            with self.assertRaisesRegex(AssertionError, "span build roots"):
                cypack_pilot_integration.build_and_run("/venv/bin/python")

    def test_cli_resolves_interpreter_prints_report_and_fails_when_missing(self):
        report = {"schema_version": 1, "pilot": "cypack-pure-cython"}
        stdout = io.StringIO()
        with mock.patch.object(
                cypack_pilot_integration,
                "build_and_run",
                return_value=report) as build, \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(cypack_pilot_integration.main([
                "--python", "python3"]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertIsNone(build.call_args.args[1])

        with mock.patch.object(
                cypack_pilot_integration.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit):
                cypack_pilot_integration.main([
                    "--python", "definitely-missing-ahpy-python"])


if __name__ == "__main__":
    unittest.main()
