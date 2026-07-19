from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

import build_portability_artifact
import run_sanitized_hpy
import test_generated_hpy


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests" / "ahpy" / "bootstrap_answer.pyx"
VERSION_MANIFEST = ROOT / "tests" / "ahpy" / "hpy-versions.toml"


class QualityGateTest(unittest.TestCase):
    def test_runtime_check_is_written_to_a_script(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = "assert 'x' * 40000\n"
            path = test_generated_hpy.write_runtime_check(
                directory, "semantic_check.py", source)

            self.assertEqual(path, directory / "semantic_check.py")
            self.assertEqual(path.read_text(encoding="utf8"), source)

    def test_binary_import_parser_rejects_cpython_symbols_and_dll(self):
        output = (
            "                 U _PyLong_FromLong\n"
            "PyExc_TypeError\n"
            "    python314.dll\n"
            "                 U HPyLong_FromLong\n"
        )
        self.assertEqual(
            test_generated_hpy._forbidden_binary_imports(output),
            ["PyExc_TypeError", "_PyLong_FromLong", "python314.dll"],
        )

    @mock.patch.object(run_sanitized_hpy.sys, "platform", "linux")
    @mock.patch.object(run_sanitized_hpy.subprocess, "run")
    def test_sanitizer_environment_preloads_reported_runtime(self, run):
        run.return_value.stdout = "/usr/lib/libasan.so\n"
        with mock.patch.object(Path, "is_file", return_value=True):
            environment = run_sanitized_hpy.sanitizer_environment(
                "gcc", "address,undefined")
        self.assertEqual(environment["LD_PRELOAD"].split(":")[0],
                         "/usr/lib/libasan.so")
        self.assertIn("-O0", environment["CFLAGS"])
        self.assertIn("-fsanitize=address,undefined", environment["CFLAGS"])
        self.assertIn("halt_on_error=1", environment["UBSAN_OPTIONS"])

    @mock.patch.object(
        run_sanitized_hpy.platform, "machine", return_value="arm64")
    @mock.patch.object(run_sanitized_hpy.sys, "platform", "darwin")
    @mock.patch.object(run_sanitized_hpy.subprocess, "run")
    def test_sanitizer_environment_preloads_apple_runtime(
        self, run, _machine,
    ):
        run.return_value.stdout = "/toolchain/libclang_rt.asan_osx_dynamic.dylib\n"
        with mock.patch.object(Path, "is_file", return_value=True):
            environment = run_sanitized_hpy.sanitizer_environment(
                "clang", "address,undefined")
        self.assertEqual(
            environment["AHPY_ASAN_RUNTIME"],
            "/toolchain/libclang_rt.asan_osx_dynamic.dylib",
        )
        self.assertNotIn("DYLD_INSERT_LIBRARIES", environment)
        self.assertEqual(environment["ARCHFLAGS"], "-arch arm64")

    def test_apple_launcher_replaces_program_name_before_python_init(self):
        source = run_sanitized_hpy.APPLE_SANITIZER_LAUNCHER
        self.assertIn('getenv("AHPY_REAL_PYTHON")', source)
        self.assertIn("argv[0] = (char *)selected_python", source)
        self.assertIn("Py_BytesMain(argc, argv)", source)

    @mock.patch.object(
        run_sanitized_hpy.shutil, "which", return_value="/usr/bin/otool")
    @mock.patch.object(run_sanitized_hpy.subprocess, "run")
    def test_macos_launcher_strips_universal2_arches_and_links_asan(
        self, run, _which,
    ):
        runtime = "/toolchain/libclang_rt.asan_osx_dynamic.dylib"
        with tempfile.TemporaryDirectory() as temp:
            bindir = Path(temp)
            python_config = bindir / "python3.11-config"
            python_config.touch()
            run.side_effect = (
                mock.Mock(stdout=json.dumps({
                    "bindir": str(bindir), "version": "3.11"})),
                mock.Mock(stdout=(
                    "-I/include -arch x86_64 -arch arm64 "
                    "-L/lib -lpython3.11")),
                mock.Mock(stdout=""),
                mock.Mock(stdout="launcher:\n\t%s\n" % runtime),
            )
            environment = {
                "ARCHFLAGS": "-arch arm64",
                "AHPY_ASAN_RUNTIME": runtime,
            }
            with run_sanitized_hpy.macos_sanitizer_python(
                "/selected/python", "clang", "address,undefined",
                environment,
            ) as launcher:
                self.assertTrue(launcher.endswith("asan-python"))

        compile_command = run.call_args_list[2].args[0]
        self.assertNotIn("x86_64", compile_command)
        self.assertEqual(
            compile_command[compile_command.index("-arch") + 1], "arm64")
        self.assertIn("-fsanitize=address,undefined", compile_command)
        self.assertEqual(environment["AHPY_REAL_PYTHON"], "/selected/python")

    @mock.patch.object(run_sanitized_hpy.subprocess, "run")
    def test_macos_preload_probe_requires_selected_runtime(self, run):
        run.return_value = mock.Mock(returncode=0, stdout="preloaded\n", stderr="")
        environment = {
            "AHPY_ASAN_RUNTIME": "/toolchain/libclang_rt.asan.dylib",
            "ARCHFLAGS": "-arch arm64",
        }
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                run_sanitized_hpy.verify_macos_preload(
                    "/tmp/asan-python", environment),
                environment["AHPY_ASAN_RUNTIME"],
            )
        self.assertEqual(run.call_args.kwargs["env"], environment)

    def test_hpy_revisions_are_exactly_pinned(self):
        manifest = tomllib.loads(VERSION_MANIFEST.read_text(encoding="utf8"))
        stable_requirements = ROOT / manifest["stable"]["requirements"]
        dev_requirements = ROOT / manifest["development"]["requirements"]
        stable_text = stable_requirements.read_text(encoding="utf8")
        dev_text = dev_requirements.read_text(encoding="utf8")
        self.assertIn("hpy==%s" % manifest["stable"]["version"], stable_text)
        commit = manifest["development"]["commit"]
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertIn("@" + commit, dev_text)
        self.assertNotIn("@master", dev_text)

    def test_generated_source_is_deterministic(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        with tempfile.TemporaryDirectory(prefix="ahpy-determinism-") as temp:
            outputs = [Path(temp) / name / "bootstrap_answer.c"
                       for name in ("first", "second")]
            for output in outputs:
                output.parent.mkdir()
                subprocess.run(
                    [
                        sys.executable, "-m", "cython",
                        "--runtime-backend=hpy-universal", "-3",
                        "-o", str(output), str(SOURCE),
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())

    def test_workflow_declares_all_initial_platform_compiler_lanes(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        for required in (
            "ubuntu-24.04",
            "ubuntu-24.04-arm",
            "macos-15-intel",
            "macos-15",
            "windows-2025",
            "cc: gcc",
            "cc: clang",
            "cc: cl",
            "run_sanitized_hpy.py",
            "native-memory-valgrind:",
            "run_lsan_hpy.py",
            "ahpy-valgrind-${{ github.run_id }}-${{ github.run_attempt }}",
            "requirements-hpy-dev.txt",
            "pypy3.11-v7.3.23",
            "graalpy-25.1.3",
            "build_portability_artifact.py",
            "verify_reproducible_artifact.py",
            "benchmark_hpy.py",
            "ahpy-performance-${{ github.run_id }}-${{ github.run_attempt }}",
            "stress_parallel_hpy.py",
            "ahpy-parallel-stress-${{ github.run_id }}-${{ github.run_attempt }}",
            "id: parallel_stress",
            "steps.parallel_stress.outcome != 'skipped'",
            "nightly-interpreter:",
            "nightly-hpy:",
            "report_nightly_environment.py",
            "requirements-hpy-nightly.txt",
            "3.15-dev",
            "--require-hpy-vcs",
        ):
            self.assertIn(required, workflow)

    def test_workflow_external_actions_use_full_commit_shas(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        actions = re.findall(r"^\s*uses:\s+([^\s#]+)", workflow, re.MULTILINE)
        self.assertTrue(actions)
        for action in actions:
            if action.startswith("./"):
                continue
            self.assertRegex(
                action,
                r"^[^@]+@[0-9a-f]{40}$",
                "external workflow action must use a full commit SHA: %s" %
                action,
            )

    def test_nightlies_are_isolated_allowed_failure_early_warnings(self):
        manifest = tomllib.loads(VERSION_MANIFEST.read_text(encoding="utf8"))
        nightly = manifest["nightly"]
        self.assertEqual(nightly["interpreter"]["setup_python"], "3.15-dev")
        self.assertEqual(nightly["hpy"]["ref"], "master")
        self.assertEqual(
            {nightly[name]["status"] for name in ("interpreter", "hpy")},
            {"allowed-failure-early-warning"},
        )
        nightly_requirements = ROOT / nightly["hpy"]["requirements"]
        requirements = nightly_requirements.read_text(encoding="utf8")
        self.assertIn(
            "hpy @ git+https://github.com/hpyproject/hpy.git@master",
            requirements,
        )
        self.assertNotRegex(requirements, r"@[0-9a-f]{40}\b")

        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        interpreter_job, rest = workflow.split("  nightly-interpreter:\n", 1)[1].split(
            "  nightly-hpy:\n", 1)
        hpy_job = rest
        schedule_guard = (
            "github.event_name == 'schedule' || "
            "github.event_name == 'workflow_dispatch'")
        for job in (interpreter_job, hpy_job):
            self.assertIn(schedule_guard, job)
            self.assertIn("continue-on-error: true", job)
            self.assertIn("if: always()", job)
            self.assertIn("nightly-evidence", job)
        self.assertIn("requirements-hpy09.txt", interpreter_job)
        self.assertNotIn("requirements-hpy-nightly.txt", interpreter_job)
        self.assertIn("requirements-hpy-nightly.txt", hpy_job)
        self.assertIn("--require-hpy-vcs", hpy_job)
        self.assertIn("--expected-hpy-ref master", hpy_job)

    def test_cross_interpreter_targets_are_machine_readable_and_pinned(self):
        manifest = tomllib.loads((
            ROOT / "tests" / "ahpy" / "interpreters.toml"
        ).read_text(encoding="utf8"))
        targets = {target["name"]: target for target in manifest["targets"]}
        self.assertEqual(
            targets["PyPy"]["setup_python"], "pypy3.11-v7.3.23")
        self.assertEqual(
            targets["GraalPy"]["setup_python"], "graalpy-25.1.3")
        self.assertEqual(
            {target["status"] for target in targets.values()},
            {"allowed-failure-early-warning"},
        )
        self.assertEqual(targets["PyPy"]["evidence_run"], 29685285138)
        self.assertEqual(targets["PyPy"]["evidence_job"], 88188460273)
        self.assertEqual(targets["GraalPy"]["evidence_run"], 29685285138)
        self.assertEqual(targets["GraalPy"]["evidence_job"], 88188460282)

        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        job = workflow.split("  cross-interpreter:\n", 1)[1].split(
            "  nightly-interpreter:\n", 1)[0]
        self.assertIn("portability_smoke.py", job)
        self.assertIn("Execute staged unchanged Universal binaries", job)
        self.assertNotIn("import platform, hpy.universal", job)
        self.assertIn("continue-on-error: true", job)

    def test_reproducible_flag_append_preserves_existing_flags(self):
        environment = {"CFLAGS": "-O2"}
        build_portability_artifact._append_flag(
            environment, "CFLAGS", "-ffile-prefix-map=/tmp=/build")
        self.assertEqual(
            environment["CFLAGS"],
            "-O2 -ffile-prefix-map=/tmp=/build",
        )

    def test_manifest_status_set_allows_declared_release_states(self):
        manifest = tomllib.loads(VERSION_MANIFEST.read_text(encoding="utf8"))
        allowed = {
            "required",
            "early-warning",
            "allowed-failure-early-warning",
            "hosted-run-pending",
        }
        statuses = {manifest["stable"]["status"], manifest["development"]["status"]}
        statuses.update(
            manifest["nightly"][name]["status"]
            for name in ("interpreter", "hpy")
        )
        statuses.update(
            target["status"]
            for target in tomllib.loads(
                (ROOT / "tests" / "ahpy" / "interpreters.toml").read_text(
                    encoding="utf8")
            )["targets"]
        )
        self.assertTrue(statuses.issubset(allowed))

    def test_stable_matrix_jobs_are_not_nightly_required_claims(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        foundation, rest = workflow.split("  stable-universal:\n", 1)
        stable_universal, after_stable = rest.split(
            "  development-revision:\n", 1)
        self.assertNotIn("continue-on-error: true", foundation)
        self.assertNotIn("continue-on-error: true", stable_universal)
        self.assertNotIn("requirements-hpy-nightly.txt", foundation)
        self.assertIn("requirements-hpy09.txt", foundation)
        self.assertEqual(stable_universal.count("cflags: -O0"), 5)
        self.assertEqual(stable_universal.count("cflags: /Od"), 1)
        self.assertIn("CFLAGS: ${{ matrix.cflags }}", stable_universal)
        development = after_stable.split("  sanitizers:\n", 1)[0]
        self.assertIn("CFLAGS: -O0", development)
        portability = after_stable.split(
            "  build-portability-artifact:\n", 1
        )[1].split("  cross-interpreter:\n", 1)[0]
        self.assertIn("CFLAGS: -O0", portability)
        nightly_section = after_stable.split("  nightly-interpreter:\n", 1)[1]
        self.assertIn("continue-on-error: true", nightly_section)
        self.assertIn("requirements-hpy-nightly.txt", nightly_section)

    def test_docs_do_not_claim_unsupported_early_warning_interpreters(self):
        validation_matrix = (
            ROOT / "docs" / "ahpy" / "validation-matrix.md"
        ).read_text(encoding="utf8")
        interpreters = tomllib.loads(
            (ROOT / "tests" / "ahpy" / "interpreters.toml").read_text(
                encoding="utf8")
        )
        for target in interpreters["targets"]:
            if target["status"] != "required":
                self.assertNotRegex(
                    validation_matrix,
                    r"%s[^\n]{0,120}\bsupported\b" % target["name"],
                )
        self.assertIn("First hosted executions are still pending", validation_matrix)
        self.assertIn("allowed-failure early warnings", validation_matrix)
        self.assertIn("continue-on-error", validation_matrix)

    def test_nightly_jobs_keep_hpy_vcs_requirement_on_hpy_lane_only(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        interpreter_job, rest = workflow.split("  nightly-interpreter:\n", 1)[1].split(
            "  nightly-hpy:\n", 1)
        hpy_job = rest.split("\n\n", 1)[0]
        for job_name, job in (("interpreter", interpreter_job),
                              ("hpy", hpy_job)):
            self.assertIn("nightly-evidence", job, job_name)
            self.assertIn("report_nightly_environment.py", job, job_name)
        self.assertNotIn("--require-hpy-vcs", interpreter_job)
        self.assertIn("--require-hpy-vcs", hpy_job)
        self.assertIn("--expected-hpy-ref master", hpy_job)

    def test_sanitizer_lane_disables_asan_leak_detection(self):
        environment = run_sanitized_hpy.sanitizer_environment("gcc", "address")
        self.assertIn("detect_leaks=0", environment["ASAN_OPTIONS"])
        readme = (ROOT / "Tools" / "ahpy" / "README.md").read_text(
            encoding="utf8")
        validation_matrix = (
            ROOT / "docs" / "ahpy" / "validation-matrix.md"
        ).read_text(encoding="utf8")
        for text in (readme, validation_matrix):
            self.assertIn("detect_leaks=0", text)
            self.assertIn("LeakSanitizer", text)
        self.assertRegex(readme, r"handle-leak gate|leak detector")
        self.assertIn("leak detector", validation_matrix)

    def test_valgrind_lane_is_hosted_pending_and_enforces_real_corpus(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        job = workflow.split("  native-memory-valgrind:\n", 1)[1].split(
            "  build-portability-artifact:\n", 1)[0]
        self.assertIn("continue-on-error: true", job)
        self.assertIn("github.event_name == 'schedule'", job)
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("valgrind", job)
        self.assertIn("run_lsan_hpy.py", job)
        self.assertNotIn("--positive-control-only", job)
        self.assertIn("if: always()", job)
        self.assertIn("valgrind-evidence", job)


if __name__ == "__main__":
    unittest.main()
