from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

import direct_build_integration as integration


class DirectBuildIntegrationTest(unittest.TestCase):

    def test_runtime_program_selects_normal_mode(self):
        program = integration._runtime_program(
            Path("/tmp/bootstrap_answer.hpy0"), "normal")
        self.assertIn("universal.MODE_UNIVERSAL", program)
        self.assertIn("assert module.answer() == 42", program)
        self.assertNotIn("LeakDetector", program)

    def test_runtime_program_selects_debug_mode_and_leak_detector(self):
        program = integration._runtime_program(
            Path("/tmp/bootstrap_answer.hpy0"), "debug")
        self.assertIn("universal.MODE_DEBUG", program)
        self.assertIn("detector.start()", program)
        self.assertIn("detector.stop()", program)

    def _run_with_plan(self, os_name="posix", execute_side_effect=None):
        probe = {"python": "/tool/python", "os_name": os_name}
        plan_box = {}

        def create_plan(
                _probe, module_name, generated, artifact_dir, object_dir,
                **options):
            plan_box.update({
                "module_name": module_name,
                "generated": generated,
                "artifact_dir": artifact_dir,
                "object_dir": object_dir,
                "options": options,
            })
            return {
                "artifact": str(artifact_dir / "bootstrap_answer.hpy0"),
            }

        if execute_side_effect is None:
            execute_side_effect = [
                {"abi": "universal", "runtime_mode": "helper"},
                RuntimeError("refusing to overwrite existing artifact"),
            ]
        with (
            mock.patch.object(
                integration, "probe_toolchain", return_value=probe),
            mock.patch.object(
                integration, "create_build_plan", side_effect=create_plan),
            mock.patch.object(
                integration, "execute_build_plan",
                side_effect=execute_side_effect),
            mock.patch.object(integration.subprocess, "run") as run,
        ):
            result = integration.build_and_run("python")
        return result, plan_box, run

    def test_build_and_run_audits_normal_and_debug_modes(self):
        result, plan, run = self._run_with_plan()
        self.assertEqual(result, ("bootstrap_answer.hpy0", "helper"))
        self.assertEqual(plan["module_name"], "bootstrap_answer")
        self.assertEqual(plan["options"]["runtime"], "auto")
        self.assertEqual(plan["options"]["cflags"], ("-O0",))
        self.assertEqual(run.call_count, 3)
        runtime_commands = [call.args[0] for call in run.call_args_list[1:]]
        self.assertTrue(all(command[:2] == ["/tool/python", "-c"]
                            for command in runtime_commands))
        self.assertIn("MODE_UNIVERSAL", runtime_commands[0][2])
        self.assertIn("MODE_DEBUG", runtime_commands[1][2])

    def test_build_and_run_uses_msvc_debug_optimization_flag(self):
        result, plan, _run = self._run_with_plan(os_name="nt")
        self.assertEqual(result[1], "helper")
        self.assertEqual(plan["options"]["cflags"], ("/Od",))

    def test_build_and_run_reraises_unexpected_rebuild_failure(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected failure"):
            self._run_with_plan(execute_side_effect=[
                {"abi": "universal", "runtime_mode": "helper"},
                RuntimeError("unexpected failure"),
            ])

    def test_build_and_run_rejects_overwriting_an_existing_artifact(self):
        manifest = {"abi": "universal", "runtime_mode": "helper"}
        with self.assertRaisesRegex(AssertionError, "overwrote"):
            self._run_with_plan(execute_side_effect=[manifest, manifest])

    def test_build_and_run_rejects_non_universal_manifest(self):
        with self.assertRaisesRegex(AssertionError, "changed ABI"):
            self._run_with_plan(execute_side_effect=[
                {"abi": "cpython", "runtime_mode": "helper"},
                RuntimeError("refusing to overwrite existing artifact"),
            ])

    def test_main_reports_artifact_and_runtime(self):
        argv = ["direct_build_integration.py", "--python", "python"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(
                integration,
                "build_and_run",
                return_value=("bootstrap_answer.hpy0", "helper"),
            ) as build,
            mock.patch("builtins.print") as printed,
        ):
            integration.main()
        build.assert_called_once_with("python")
        printed.assert_called_once_with(
            "aHPy direct Universal build passed: "
            "bootstrap_answer.hpy0 runtime=helper")


if __name__ == "__main__":
    unittest.main()
