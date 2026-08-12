import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import murmurhash_pilot_integration as integration


class MurmurhashPilotIntegrationTest(unittest.TestCase):
    def test_runtime_program_covers_reference_failures_and_debug(self):
        normal = integration._runtime_program(False)
        self.assertIn("def murmur3_u64", normal)
        self.assertIn("module.hash_u64_nogil", normal)
        self.assertIn("missing unsigned conversion failure", normal)
        self.assertNotIn("LeakDetector", normal)
        debug = integration._runtime_program(True)
        self.assertIn("LeakDetector", debug)
        self.assertTrue(debug.endswith("detector.stop()\n"))

    def test_sha_and_selected_pilot_contract_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-murmur-hash-") as temp:
            source = Path(temp) / "source"
            source.write_bytes(b"murmur")
            self.assertEqual(
                integration._sha256(source),
                "6200f53485b683973d0c8cb0da433414326ca268363546ece184689555b06568",
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
        for source_name in integration.UPSTREAM_FILES:
            source = checkout / source_name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(source_name + "\n", encoding="utf8")
        return checkout

    def test_build_and_run_records_provenance_gates_and_output(self):
        binary_box = {}

        def fake_run(command, **options):
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

        with tempfile.TemporaryDirectory(prefix="ahpy-murmur-test-") as temp:
            root = Path(temp)
            checkout = self._checkout(root)
            output = root / "nested" / "report.json"
            provenance = {
                "head": integration.UPSTREAM_COMMIT,
                "origin": "https://github.com/explosion/murmurhash.git",
                "pristine": True,
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
                        integration.time, "monotonic", side_effect=range(10)):
                report = integration.build_and_run(
                    "/venv/bin/python", checkout, output)
            stored = json.loads(output.read_text(encoding="utf8"))

        self.assertEqual(report, stored)
        self.assertEqual(report["pilot"], integration.PILOT_ID)
        self.assertEqual(report["port_contract"]["status"],
                         "partial-scalar-adapter")
        self.assertFalse(
            report["port_contract"]["upstream_python_bytes_api_supported"])
        self.assertEqual(set(report["gates"].values()), {"pass"})
        self.assertEqual(report["timings_seconds"]["build"], 1)
        self.assertEqual(report["timings_seconds"]["total"], 9)
        self.assertEqual(run.call_count, 4)
        source_audit.assert_called_once()
        binary_audit.assert_called_once_with(binary_box["path"])
        verify.assert_called_once()
        self.assertEqual(
            set(report["provenance"]["source_sha256"]),
            set(integration.UPSTREAM_FILES))

    def test_cli_resolves_interpreter_prints_and_rejects_missing_python(self):
        report = {"schema_version": 1, "pilot": integration.PILOT_ID}
        stdout = io.StringIO()
        with mock.patch.object(
                    integration, "build_and_run",
                    return_value=report) as build, \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(integration.main([
                "--python", "python3",
                "--checkout", "/tmp/murmurhash",
            ]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertEqual(build.call_args.args[1], Path("/tmp/murmurhash"))
        self.assertIsNone(build.call_args.args[2])

        with mock.patch.object(integration.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit):
                integration.main([
                    "--python", "definitely-missing-ahpy-python",
                    "--checkout", "/tmp/murmurhash",
                ])


if __name__ == "__main__":
    unittest.main()
