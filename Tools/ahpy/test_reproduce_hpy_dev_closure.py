from pathlib import Path
import signal
import unittest
from unittest import mock
from types import SimpleNamespace

import reproduce_hpy_dev_closure as reproducer


require_runtime_success = reproducer.require_runtime_success


class HPyDevelopmentClosureReproducerTest(unittest.TestCase):
    def test_success_is_accepted(self):
        require_runtime_success(SimpleNamespace(returncode=0), "normal")

    def test_sigsegv_is_classified(self):
        with self.assertRaisesRegex(
            AssertionError,
            "minimal generated closure crashed with SIGSEGV in HPy trace mode",
        ):
            require_runtime_success(
                SimpleNamespace(returncode=-signal.SIGSEGV),
                "trace",
            )

    def test_other_failure_keeps_exit_status(self):
        with self.assertRaisesRegex(
            AssertionError,
            "HPy debug mode with exit status 7",
        ):
            require_runtime_success(SimpleNamespace(returncode=7), "debug")

    def test_subject_is_preserved(self):
        with self.assertRaisesRegex(
            AssertionError,
            "minimal handwritten HPy heap type crashed with SIGSEGV",
        ):
            require_runtime_success(
                SimpleNamespace(returncode=-signal.SIGSEGV),
                "normal",
                "minimal handwritten HPy heap type",
            )

    def test_run_delegates_to_checked_subprocess(self):
        with mock.patch.object(reproducer.subprocess, "run") as run:
            reproducer.run(["python", "-V"], cwd=Path("/tmp"))
        run.assert_called_once_with(
            ["python", "-V"], check=True, cwd=Path("/tmp"))

    def test_build_and_run_audits_both_modules_in_all_runtime_modes(self):
        binaries = {}
        runtime_environments = []

        def fake_build_run(command, **options):
            if "--runtime-backend=hpy-universal" in command:
                Path(command[command.index("-o") + 1]).write_text(
                    "generated Universal C\n")
                return
            build_root = Path(command[command.index("--build-base") + 1])
            build_lib = build_root / "lib"
            build_lib.mkdir(parents=True)
            for module_name in (
                    reproducer.MODULE_NAME,
                    reproducer.HANDWRITTEN_MODULE_NAME):
                binary = build_lib / (module_name + ".hpy0.so")
                binary.write_bytes(b"binary")
                (build_lib / (module_name + ".py")).write_text("# loader\n")
                binaries[module_name] = binary

        def require_binary(_root, module_name):
            return binaries[module_name]

        def runtime_run(_command, **options):
            runtime_environments.append(options["env"].copy())
            return SimpleNamespace(returncode=0)

        with (
            mock.patch.object(
                reproducer.shutil, "which", return_value="/tool/python"),
            mock.patch.object(reproducer, "run", side_effect=fake_build_run),
            mock.patch.object(reproducer, "verify_source_boundary"),
            mock.patch.object(reproducer, "verify_binary_boundary"),
            mock.patch.object(
                reproducer, "require_universal_binary",
                side_effect=require_binary,
            ),
            mock.patch.object(
                reproducer.subprocess, "run", side_effect=runtime_run),
        ):
            reproducer.build_and_run("python")

        self.assertEqual(len(runtime_environments), 6)
        self.assertNotIn("HPY", runtime_environments[0])
        self.assertEqual(runtime_environments[1]["HPY"], "trace")
        self.assertEqual(runtime_environments[2]["HPY"], "debug")
        self.assertNotIn("HPY", runtime_environments[3])
        self.assertEqual(runtime_environments[4]["HPY"], "trace")
        self.assertEqual(runtime_environments[5]["HPY"], "debug")

    def test_build_and_run_rejects_missing_interpreter(self):
        with (
            mock.patch.object(reproducer.shutil, "which", return_value=None),
            self.assertRaisesRegex(FileNotFoundError, "interpreter not found"),
        ):
            reproducer.build_and_run("missing-python")

    def test_build_and_run_requires_loader_stubs_for_both_modules(self):
        binaries = {}

        def fake_run(command, **options):
            if "--runtime-backend=hpy-universal" in command:
                Path(command[command.index("-o") + 1]).touch()
                return
            build_root = Path(command[command.index("--build-base") + 1])
            build_lib = build_root / "lib"
            build_lib.mkdir(parents=True)
            for module_name in (
                reproducer.MODULE_NAME,
                reproducer.HANDWRITTEN_MODULE_NAME,
            ):
                binary = build_lib / (module_name + ".hpy0.so")
                binary.touch()
                binaries[module_name] = binary

        with (
            mock.patch.object(
                reproducer.shutil, "which", return_value="/tool/python"
            ),
            mock.patch.object(reproducer, "run", side_effect=fake_run),
            mock.patch.object(reproducer, "verify_source_boundary"),
            mock.patch.object(reproducer, "verify_binary_boundary"),
            mock.patch.object(
                reproducer, "require_universal_binary",
                side_effect=lambda root, name: binaries[name],
            ),
            self.assertRaisesRegex(AssertionError, "loader stub was not generated"),
        ):
            reproducer.build_and_run("python")

    def test_main_runs_selected_interpreter(self):
        argv = ["reproduce_hpy_dev_closure.py", "--python", "python"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(reproducer, "build_and_run") as build,
            mock.patch("builtins.print"),
        ):
            reproducer.main()
        build.assert_called_once_with("python")


if __name__ == "__main__":
    unittest.main()
