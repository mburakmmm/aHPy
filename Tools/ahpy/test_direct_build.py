import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import direct_build
from direct_build import create_build_plan


ROOT = Path(__file__).resolve().parents[2]
DIRECT_BUILD = ROOT / "Tools" / "ahpy" / "direct_build.py"


def _probe(os_name="posix", root=None):
    windows = os_name == "nt"
    if root is None:
        runtime_source = "/hpy/runtime/helpers.c"
        static_library = "/hpy/lib/libhpy-extra-universal.a"
        include_dir = "/hpy/include"
        forbid_python_h = "/hpy/include/hpy/forbid_python_h"
    else:
        runtime_source = str(Path(root) / "helpers.c")
        static_library = str(Path(root) / "hpy-extra.lib" if windows else
                             Path(root) / "libhpy-extra-universal.a")
        Path(runtime_source).write_text("/* HPy runtime */\n", encoding="utf8")
        Path(static_library).touch()
        include_dir = str(Path(root) / "include")
        forbid_python_h = str(Path(root) / "forbid-python-h")
    return {
        "python": "/venv/python",
        "platform": "win32" if windows else "linux",
        "os_name": os_name,
        "machine": "x86_64",
        "hpy_version": "0.9.0",
        "extension_suffix": ".hpy0.pyd" if windows else ".hpy0.so",
        "include_dirs": [include_dir],
        "forbid_python_h": forbid_python_h,
        "runtime_sources": [runtime_source],
        "static_libraries": [static_library],
        "config": {
            "CC": "cl" if windows else "cc",
            "CFLAGS": "",
            "CCSHARED": "",
            "LDSHARED": "cc -shared",
            "LDFLAGS": "",
        },
    }


class DirectBuildTest(unittest.TestCase):
    def _source(self, temp):
        source = Path(temp) / "demo.c"
        source.write_text(
            "#include <hpy.h>\nHPy_MODINIT(demo, module)\n",
            encoding="utf8")
        return source

    def test_posix_static_plan_has_exact_universal_boundary(self):
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            probe = _probe(root=temp)
            plan = create_build_plan(
                probe, "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="static")
        command = plan["compile_commands"][0]
        self.assertEqual(plan["abi"], "universal")
        self.assertTrue(plan["artifact"].endswith("demo.hpy0.so"))
        self.assertIn("-DHPY", command)
        self.assertIn("-DHPY_ABI_UNIVERSAL", command)
        self.assertLess(
            command.index("-I" + probe["forbid_python_h"]),
            command.index("-I" + probe["include_dirs"][0]),
        )
        self.assertIn(
            str(Path(temp) / "libhpy-extra-universal.a"),
            plan["link_command"])

    def test_windows_plan_exports_hpy_initializer(self):
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            plan = create_build_plan(
                _probe("nt", temp), "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="static")
        self.assertTrue(plan["artifact"].endswith("demo.hpy0.pyd"))
        self.assertIn("/DHPY_ABI_UNIVERSAL", plan["compile_commands"][0])
        self.assertIn("/EXPORT:HPyInit_demo", plan["link_command"])

    @mock.patch.object(direct_build.shutil, "which")
    @mock.patch.object(direct_build.subprocess, "run")
    def test_msvc_environment_uses_vswhere_and_vcvarsall(self, run, which):
        with TemporaryDirectory() as temp:
            program_files = Path(temp) / "Program Files (x86)"
            vswhere = (
                program_files / "Microsoft Visual Studio" /
                "Installer" / "vswhere.exe"
            )
            vswhere.parent.mkdir(parents=True)
            vswhere.touch()
            installation = Path(temp) / "Visual Studio"
            vcvarsall = (
                installation / "VC" / "Auxiliary" / "Build" /
                "vcvarsall.bat"
            )
            vcvarsall.parent.mkdir(parents=True)
            vcvarsall.touch()
            run.side_effect = (
                mock.Mock(stdout=str(installation) + "\n"),
                mock.Mock(stdout="Path=C:\\msvc\\bin\nINCLUDE=C:\\msvc\\include\n"),
            )
            which.side_effect = (None, None, "C:\\msvc\\bin\\cl.exe")

            environment = direct_build.discover_msvc_environment(
                "AMD64",
                {
                    "PATH": "C:\\Windows",
                    "ProgramFiles(x86)": str(program_files),
                    "COMSPEC": "C:\\Windows\\cmd.exe",
                },
            )

        self.assertEqual(environment["Path"], "C:\\msvc\\bin")
        self.assertEqual(environment["INCLUDE"], "C:\\msvc\\include")
        self.assertEqual(run.call_args_list[0].args[0][0], str(vswhere))
        vcvars_command = run.call_args_list[1].args[0]
        self.assertEqual(vcvars_command[1:3], ["/d", "/c"])
        self.assertTrue(vcvars_command[-1].endswith("activate.cmd"))
        activation_source = direct_build._msvc_activation_script(
            vcvarsall, "x64")
        self.assertIn('call "%s" x64' % vcvarsall, activation_source)
        self.assertIn("if errorlevel 1 exit /b 1", activation_source)

    @mock.patch.object(
        direct_build.shutil, "which", return_value="C:\\tools\\cl.exe")
    def test_msvc_environment_preserves_an_active_toolchain(self, _which):
        environment = {"PATH": "C:\\tools", "MARKER": "preserved"}
        self.assertEqual(
            direct_build.discover_msvc_environment("x86_64", environment),
            environment,
        )

    def test_environment_helpers_and_missing_msvc_tools_fail_closed(self):
        environment = {"Path": "first", "PATH": "second", "OTHER": "ok"}
        self.assertEqual(
            direct_build._environment_value(environment, "path"), "first")
        self.assertIsNone(
            direct_build._environment_value(environment, "missing"))
        direct_build._replace_environment_value(environment, "PATH", "new")
        self.assertEqual(environment, {"OTHER": "ok", "PATH": "new"})

        with mock.patch.object(direct_build.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "does not expose cl.exe"):
                direct_build._resolve_msvc_executable(environment)
            with self.assertRaisesRegex(RuntimeError, "cannot locate vswhere"):
                direct_build.discover_msvc_environment(
                    "x86_64", {"PATH": "empty"})
        with mock.patch.object(
            direct_build.shutil, "which", return_value="C:\\msvc\\cl.exe"
        ):
            self.assertEqual(
                direct_build._resolve_msvc_executable(environment),
                "C:\\msvc\\cl.exe",
            )

    def test_msvc_discovery_rejects_incomplete_installations(self):
        with TemporaryDirectory() as temp:
            installation = Path(temp) / "Visual Studio"
            base_environment = {"PATH": "tools"}

            with (
                mock.patch.object(
                    direct_build.shutil, "which",
                    side_effect=(None, "vswhere.exe"),
                ),
                mock.patch.object(
                    direct_build.subprocess, "run",
                    return_value=mock.Mock(stdout=""),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "found no Visual"):
                    direct_build.discover_msvc_environment(
                        "x86_64", base_environment)

            with (
                mock.patch.object(
                    direct_build.shutil, "which",
                    side_effect=(None, "vswhere.exe"),
                ),
                mock.patch.object(
                    direct_build.subprocess, "run",
                    return_value=mock.Mock(stdout=str(installation)),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "vcvarsall.bat"):
                    direct_build.discover_msvc_environment(
                        "x86_64", base_environment)

            vcvarsall = (
                installation / "VC" / "Auxiliary" / "Build" /
                "vcvarsall.bat"
            )
            vcvarsall.parent.mkdir(parents=True)
            vcvarsall.touch()
            with (
                mock.patch.object(
                    direct_build.shutil, "which",
                    side_effect=(None, "vswhere.exe"),
                ),
                mock.patch.object(
                    direct_build.subprocess, "run",
                    return_value=mock.Mock(stdout=str(installation)),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "unsupported Visual"):
                    direct_build.discover_msvc_environment(
                        "sparc", base_environment)

            with (
                mock.patch.object(
                    direct_build.shutil, "which",
                    side_effect=(None, "vswhere.exe", None),
                ),
                mock.patch.object(
                    direct_build.subprocess,
                    "run",
                    side_effect=(
                        mock.Mock(stdout=str(installation)),
                        mock.Mock(stdout="PATH=C:\\tools\n"),
                    ),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "did not expose cl"):
                    direct_build.discover_msvc_environment(
                        "arm64", base_environment)

    def test_msvc_execution_uses_the_resolved_executable(self):
        resolved = "C:\\msvc\\bin\\cl.exe"
        commands = []
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            plan = create_build_plan(
                _probe("nt", temp), "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="static")

            def execute(command, **_kwargs):
                commands.append(command)
                if "/link" in command:
                    Path(plan["artifact"]).write_bytes(b"portable binary")
                return mock.Mock(returncode=0)

            with (
                mock.patch.object(
                    direct_build, "discover_msvc_environment",
                    return_value={"Path": "C:\\msvc\\bin"},
                ),
                mock.patch.object(
                    direct_build, "_resolve_msvc_executable",
                    return_value=resolved,
                ),
                mock.patch.object(
                    direct_build.subprocess, "run", side_effect=execute),
                mock.patch.object(direct_build, "verify_source_boundary"),
                mock.patch.object(direct_build, "verify_binary_boundary"),
            ):
                manifest = direct_build.execute_build_plan(plan)

        self.assertEqual(manifest["abi"], "universal")
        self.assertTrue(commands)
        self.assertTrue(all(command[0] == resolved for command in commands))

    def test_invalid_module_and_missing_static_runtime_fail_closed(self):
        with TemporaryDirectory() as temp:
            source = self._source(temp)
            with self.assertRaisesRegex(ValueError, "plain C identifier"):
                create_build_plan(
                    _probe(root=temp), "bad.name", source, Path(temp) / "out",
                    Path(temp) / "build")
            probe = _probe(root=temp)
            probe["static_libraries"] = []
            with self.assertRaisesRegex(RuntimeError, "exactly one library"):
                create_build_plan(
                    probe, "demo", source, Path(temp) / "out",
                    Path(temp) / "build", runtime="static")
            helper = Path(temp) / "helper.c"
            helper.write_text("int helper(void) { return 0; }\n", encoding="utf8")
            probe["runtime_sources"] = [str(helper)]
            plan = create_build_plan(
                probe, "demo", source, Path(temp) / "out",
                Path(temp) / "build", runtime="auto")
            self.assertEqual(plan["runtime_mode"], "sources")
            self.assertEqual(plan["runtime_inputs"], [str(helper)])

    def test_input_and_compiler_plan_validation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(temp)
            probe = _probe(root=temp)
            shared = root / "shared"
            with self.assertRaisesRegex(ValueError, "existing .c file"):
                create_build_plan(
                    probe, "demo", root / "missing.pyx", root / "out",
                    root / "build")
            with self.assertRaisesRegex(ValueError, "must differ"):
                create_build_plan(
                    probe, "demo", source, shared, shared)
            with self.assertRaisesRegex(ValueError, "source does not exist"):
                create_build_plan(
                    probe, "demo", source, root / "out", root / "build",
                    extra_sources=[root / "missing.c"])

            probe["config"]["CC"] = ""
            probe["config"]["LDSHARED"] = ""
            fallback = create_build_plan(
                probe, "demo", source, root / "out", root / "build")
            self.assertEqual(fallback["compile_commands"][0][0], "cc")
            self.assertEqual(fallback["link_command"][:2], ["cc", "-shared"])

            probe["config"]["LDSHARED"] = "system-cc -bundle"
            overridden = create_build_plan(
                probe, "demo", source, root / "out2", root / "build2",
                compiler="clang -arch arm64")
            self.assertEqual(
                overridden["link_command"][:4],
                ["clang", "-arch", "arm64", "-bundle"],
            )

    def test_execution_rejects_dirty_paths_and_missing_link_output(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            plan = create_build_plan(
                _probe(root=temp), "demo", self._source(temp), root / "out",
                root / "build", runtime="static")
            artifact = Path(plan["artifact"])
            artifact.parent.mkdir(parents=True)
            artifact.touch()
            with mock.patch.object(direct_build, "verify_source_boundary"):
                with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                    direct_build.execute_build_plan(plan)

            artifact.unlink()
            build_dir = Path(plan["build_dir"])
            build_dir.mkdir(parents=True)
            (build_dir / "dirty.o").touch()
            with mock.patch.object(direct_build, "verify_source_boundary"):
                with self.assertRaisesRegex(RuntimeError, "is not empty"):
                    direct_build.execute_build_plan(plan)

            (build_dir / "dirty.o").unlink()
            with (
                mock.patch.object(direct_build, "verify_source_boundary"),
                mock.patch.object(direct_build.subprocess, "run"),
            ):
                with self.assertRaisesRegex(RuntimeError, "did not create"):
                    direct_build.execute_build_plan(plan)

    def test_main_supports_plan_files_stdout_and_build_reporting(self):
        plan = {
            "artifact": "/dist/demo.hpy0.so",
            "module_name": "demo",
        }
        base_argv = [
            "direct_build.py", "--module", "demo", "--source", "demo.c",
            "--output-dir", "dist", "--build-dir", "build",
        ]
        stdout = io.StringIO()
        with (
            mock.patch("sys.argv", base_argv + ["--plan-only"]),
            mock.patch.object(
                direct_build, "probe_toolchain", return_value={"probe": True}
            ) as probe,
            mock.patch.object(
                direct_build, "create_build_plan", return_value=plan
            ) as create,
            mock.patch.object(direct_build.sys, "stdout", stdout),
        ):
            self.assertEqual(direct_build.main(), 0)
        self.assertEqual(json.loads(stdout.getvalue()), plan)
        probe.assert_called_once_with(sys.executable)
        self.assertEqual(create.call_args.kwargs["runtime"], "auto")

        with TemporaryDirectory() as temp:
            output = Path(temp) / "nested" / "plan.json"
            with (
                mock.patch(
                    "sys.argv",
                    base_argv + ["--plan-only", "--json-output", str(output)],
                ),
                mock.patch.object(
                    direct_build, "probe_toolchain", return_value={}
                ),
                mock.patch.object(
                    direct_build, "create_build_plan", return_value=plan
                ),
            ):
                self.assertEqual(direct_build.main(), 0)
            self.assertEqual(json.loads(output.read_text()), plan)

        stdout = io.StringIO()
        with (
            mock.patch("sys.argv", base_argv),
            mock.patch.object(direct_build, "probe_toolchain", return_value={}),
            mock.patch.object(
                direct_build, "create_build_plan", return_value=plan
            ),
            mock.patch.object(
                direct_build, "execute_build_plan",
                return_value={"sha256": "abc123"},
            ) as execute,
            mock.patch.object(direct_build.sys, "stdout", stdout),
        ):
            self.assertEqual(direct_build.main(), 0)
        execute.assert_called_once_with(plan)
        self.assertIn("abc123", stdout.getvalue())

    def test_cli_imports_repository_modules_from_clean_working_directory(self):
        with TemporaryDirectory() as temp:
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, str(DIRECT_BUILD), "--help"],
                cwd=temp,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--plan-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
