import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import frozenlist_pilot_integration as integration


class FrozenlistPilotIntegrationTest(unittest.TestCase):
    def test_runtime_program_covers_gc_inheritance_failures_and_debug(self):
        normal = integration._runtime_program(False)
        self.assertIn("DerivedFrozenList", normal)
        self.assertIn("weakref.ref(probe)", normal)
        self.assertIn("missing constructor failure", normal)
        self.assertIn("items_hash == tuple_hash", normal)
        self.assertNotIn("LeakDetector", normal)
        debug = integration._runtime_program(True)
        self.assertIn("LeakDetector", debug)
        self.assertTrue(debug.endswith("detector.stop()\n"))
        performance = integration._performance_program()
        self.assertIn("compiled_workload", performance)
        self.assertIn('"mutation-freeze-hash"', performance)
        self.assertIn("compiled_to_python_ratio", performance)

    def test_sha_and_selected_pilot_contract_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-frozen-hash-") as temp:
            source = Path(temp) / "source"
            source.write_bytes(b"frozen")
            self.assertEqual(
                integration._sha256(source),
                "ffb304816a1090313e833215c08dae3d209cfad1ffd1f674f0909a2ae99e1394",
            )
        with self.assertRaisesRegex(AssertionError, "exactly one"):
            integration._selected_pilot(SimpleNamespace(pilots=[]))
        drifted = SimpleNamespace(
            id=integration.PILOT_ID,
            commit="0" * 40,
        )
        with self.assertRaisesRegex(AssertionError, "commit drifted"):
            integration._selected_pilot(SimpleNamespace(pilots=[drifted]))

    def _checkout(self, root):
        checkout = root / "checkout"
        source = checkout / integration.UPSTREAM_SOURCE
        source.parent.mkdir(parents=True)
        source.write_text("upstream frozenlist\n", encoding="utf8")
        (checkout / "LICENSE").write_text("Apache-2.0\n", encoding="utf8")
        return checkout

    def test_build_and_run_records_subset_provenance_and_output(self):
        binary_box = {}

        def fake_run(command, **options):
            performance = options.get("env", {}).get(
                "AHPY_PILOT_PERFORMANCE_OUTPUT")
            if performance:
                Path(performance).write_text(json.dumps({
                    "schema_version": 1,
                    "environment": {
                        "python_implementation": "CPython",
                        "python_version": "3.11.15",
                        "hpy_version": "0.9.0",
                        "platform": "test-platform",
                        "machine": "test-machine",
                    },
                    "workloads": {
                        "mutation-freeze-hash": {
                            "iterations": 10000,
                            "repeats": 7,
                            "compiled_ns_per_call": 30.0,
                            "python_reference_ns_per_call": 15.0,
                            "compiled_to_python_ratio": 2.0,
                        },
                    },
                }), encoding="utf8")
                return
            if "--build-base" not in command:
                return
            project = Path(options["cwd"])
            (project / (integration.MODULE + ".c")).write_text(
                "generated Universal C\n", encoding="utf8")
            build = Path(command[command.index("--build-base") + 1])
            binary = build / "lib" / (integration.MODULE + ".hpy0.so")
            binary.parent.mkdir(parents=True)
            binary.touch()
            binary_box["path"] = binary

        with tempfile.TemporaryDirectory(prefix="ahpy-frozen-test-") as temp:
            root = Path(temp)
            checkout = self._checkout(root)
            output = root / "nested" / "report.json"
            provenance = {
                "head": integration.UPSTREAM_COMMIT,
                "origin": "https://github.com/aio-libs/frozenlist.git",
                "pristine": True,
                "license_file": "LICENSE",
            }
            with mock.patch.object(
                        integration, "verify_checkout",
                        return_value=provenance) as verify, \
                    mock.patch.object(
                        integration, "run", side_effect=fake_run) as run, \
                    mock.patch.object(
                        integration, "verify_source_boundary") as source_audit, \
                    mock.patch.object(
                        integration, "verify_binary_boundary") as binary_audit, \
                    mock.patch.object(
                        integration, "require_universal_binary",
                        side_effect=lambda build, module: binary_box["path"]), \
                    mock.patch.object(
                        integration.time, "monotonic", side_effect=range(12)):
                report = integration.build_and_run(
                    "/venv/bin/python", checkout, output)
            stored = json.loads(output.read_text(encoding="utf8"))

        self.assertEqual(report, stored)
        self.assertEqual(report["pilot"], integration.PILOT_ID)
        self.assertEqual(report["port_contract"]["status"], "supported-subset")
        self.assertTrue(report["port_contract"]["object_field_gc"])
        self.assertTrue(report["port_contract"]["same_module_inheritance"])
        self.assertFalse(
            report["port_contract"]["free_threading_atomic_semantics"])
        self.assertEqual(set(report["gates"].values()), {"pass"})
        self.assertEqual(report["timings_seconds"]["build"], 1)
        self.assertEqual(report["timings_seconds"]["performance"], 1)
        self.assertEqual(report["timings_seconds"]["total"], 11)
        self.assertEqual(run.call_count, 5)
        self.assertEqual(
            report["performance"]["comparison"],
            "supported-subset-to-equivalent-python")
        self.assertFalse(report["performance"]["budget_enforced"])
        source_audit.assert_called_once()
        binary_audit.assert_called_once_with(binary_box["path"])
        verify.assert_called_once()
        self.assertIn(
            integration.UPSTREAM_SOURCE,
            report["provenance"]["source_sha256"])

    def test_cli_resolves_interpreter_prints_and_rejects_missing_python(self):
        report = {"schema_version": 1, "pilot": integration.PILOT_ID}
        stdout = io.StringIO()
        with mock.patch.object(
                    integration, "build_and_run",
                    return_value=report) as build, \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(integration.main([
                "--python", "python3",
                "--checkout", "/tmp/frozenlist",
            ]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertEqual(build.call_args.args[1], Path("/tmp/frozenlist"))
        self.assertIsNone(build.call_args.args[2])

        with mock.patch.object(integration.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit):
                integration.main([
                    "--python", "definitely-missing-ahpy-python",
                    "--checkout", "/tmp/frozenlist",
                ])


if __name__ == "__main__":
    unittest.main()
