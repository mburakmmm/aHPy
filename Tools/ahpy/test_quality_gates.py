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
RELEASE_CONTRACT = ROOT / "tests" / "ahpy" / "release-contract.toml"
ADVANCED_SURFACE = ROOT / "tests" / "ahpy" / "advanced-surface.toml"
GRAAL_EXCLUSIONS = ROOT / "tests" / "graal_bugs.txt"


class QualityGateTest(unittest.TestCase):
    def test_graalpy_excludes_only_executable_hpy_runtime_fixtures(self):
        patterns = [
            re.compile(line)
            for line in GRAAL_EXCLUSIONS.read_text(encoding="utf8").splitlines()
            if line and not line.startswith("#")
        ]

        def is_excluded(test_name):
            return any(pattern.search(test_name) for pattern in patterns)

        for fixture in (
            "ahpy.bootstrap_answer",
            "ahpy.bootstrap_types",
            "ahpy.fault_injection",
        ):
            self.assertTrue(is_excluded(fixture), fixture)
        for compile_only_fixture in (
            "ahpy.benchmark_generated",
            "ahpy.retry_case",
        ):
            self.assertFalse(is_excluded(compile_only_fixture),
                             compile_only_fixture)

    def test_ci_bounds_parallel_shared_utility_test_trees(self):
        script = (ROOT / "Tools" / "ci-run.sh").read_text(encoding="utf8")
        self.assertIn(
            'if [[ $OSTYPE == "msys" || $OSTYPE == "cygwin" ]]; then\n'
            "  # Several end-to-end tests launch their own multi-extension "
            "MSVC builds.\n",
            script,
        )
        self.assertIn("  TEST_PARALLELISM=-j4\n", script)
        self.assertIn(
            '  WINDOWS_SHARED_UTILITY_EXCLUDE="-x tag:shared_utility"\n',
            script,
        )
        self.assertEqual(script.count("$WINDOWS_SHARED_UTILITY_EXCLUDE"), 2)
        self.assertIn("    -j1 \\\n    tag:shared_utility || EXIT_CODE=1\n", script)
        self.assertIn('elif [[ $PYTHON_VERSION == "graalpy"* ]]; then', script)
        self.assertIn("  TEST_PARALLELISM=-j2\n", script)
        self.assertIn(
            "elif [[ $SHARED_UTILITY ]]; then\n"
            "  # Shared-utility mode recompiles the complete selected corpus "
            "with larger\n",
            script,
        )
        self.assertEqual(script.count("  TEST_PARALLELISM=-j4\n"), 2)

        workflow = (ROOT / ".github" / "workflows" / "ci-job.yml").read_text(
            encoding="utf8")
        self.assertIn(
            "timeout-minutes: ${{ startsWith(inputs.python-version, "
            "'graalpy') && 150 || inputs.shared_utility && 120 || 80 }}",
            workflow,
        )

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

    def test_preview_release_contract_matches_code_ci_and_docs(self):
        contract = tomllib.loads(RELEASE_CONTRACT.read_text(encoding="utf8"))
        versions = {}
        exec(
            (ROOT / "ahpy_version.py").read_text(encoding="utf8"),
            versions,
        )
        hpy_versions = tomllib.loads(
            VERSION_MANIFEST.read_text(encoding="utf8"))

        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["product_level"], "preview")
        self.assertEqual(contract["publication_status"], "unpublished")
        self.assertFalse(contract["general_cython_compatibility"])
        self.assertEqual(
            contract["distribution"], versions["AHPY_DISTRIBUTION"])
        self.assertEqual(
            contract["distribution_version"], versions["AHPY_VERSION"])
        self.assertEqual(
            contract["cython"]["version"], versions["CYTHON_BASE_VERSION"])
        self.assertEqual(
            contract["cython"]["base_commit"],
            versions["CYTHON_BASE_COMMIT"],
        )
        self.assertEqual(
            contract["hpy"]["supported_versions"],
            [hpy_versions["stable"]["version"]],
        )
        self.assertEqual(
            contract["hpy"]["supported_versions"],
            [versions["AHPY_HPY_SUPPORTED_VERSION"]],
        )
        self.assertEqual(
            contract["hpy"]["setuptools_version"],
            versions["AHPY_SETUPTOOLS_VERSION"],
        )
        self.assertEqual(
            contract["hpy"]["development_commit"],
            hpy_versions["development"]["commit"],
        )
        self.assertEqual(
            contract["hpy"]["development_status"], "early-warning")
        self.assertEqual(
            contract["python"]["supported_implementation"], "CPython")
        self.assertEqual(contract["python"]["supported_versions"], ["3.11"])
        self.assertEqual(
            set(contract["python"]["unsupported_implementations"]),
            {"PyPy", "GraalPy"},
        )

        platforms = {entry["id"]: entry for entry in contract["platforms"]}
        self.assertEqual(
            set(platforms),
            {
                "linux-x64-gcc",
                "linux-x64-clang",
                "linux-arm64-gcc",
                "macos-intel-clang",
                "macos-arm64-clang",
                "windows-x64-msvc",
            },
        )
        self.assertEqual(
            {entry["status"] for entry in platforms.values()},
            {"supported"},
        )
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        for platform in platforms.values():
            self.assertIn("name: " + platform["id"], workflow)
            self.assertIn("os: " + platform["runner"], workflow)

        frontends = {
            entry["id"]: entry["status"]
            for entry in contract["frontends"]
        }
        self.assertEqual(
            frontends,
            {
                "compiler-cli": "supported",
                "direct-build": "partial",
                "setuptools-cythonize": "partial",
                "pep517": "partial",
                "cmake": "partial",
                "meson": "partial",
                "scikit-build-core": "partial",
            },
        )

        release_contract = (
            ROOT / "docs" / "ahpy" / "release-contract.md"
        ).read_text(encoding="utf8")
        known_limitations = (
            ROOT / "docs" / "ahpy" / "known-limitations.md"
        ).read_text(encoding="utf8")
        readme = (ROOT / "README.rst").read_text(encoding="utf8")
        support_matrix = (
            ROOT / "docs" / "ahpy" / "support-matrix.md"
        ).read_text(encoding="utf8")
        handle_model = (
            ROOT / "docs" / "ahpy" / "handle-model.md"
        ).read_text(encoding="utf8")
        module_state = (
            ROOT / "docs" / "ahpy" / "module-state.md"
        ).read_text(encoding="utf8")
        for exact_value in (
            contract["distribution_version"],
            contract["cython"]["version"],
            contract["cython"]["base_commit"],
            contract["hpy"]["supported_versions"][0],
            contract["hpy"]["development_commit"],
        ):
            self.assertIn(exact_value, release_contract)
        self.assertIn("preview", readme.lower())
        self.assertIn("release-contract.md", support_matrix)
        self.assertIn("known-limitations.md", support_matrix)
        self.assertIn("General Cython compatibility is not claimed",
                      known_limitations)
        for stale_claim in (
            "generated cleanup are still gated work",
            "cleanup blocks are not yet connected",
            "backend remains gated",
            "effectful default evaluation is not yet implemented",
        ):
            self.assertNotIn(stale_claim, handle_model + module_state)

    def test_advanced_surface_contract_is_complete_and_fail_closed(self):
        manifest = tomllib.loads(
            ADVANCED_SURFACE.read_text(encoding="utf8"))
        self.assertEqual(manifest["schema_version"], 1)
        families = {entry["id"]: entry for entry in manifest["families"]}
        self.assertEqual(
            set(families),
            {
                "generic-iteration",
                "generators",
                "async",
                "buffer-producer",
                "buffer-consumer-memoryview",
                "fused-types",
                "nogil-reentry",
                "parallel-openmp-free-threading",
                "python-state-callbacks",
                "capsules-cross-module-api",
                "cxx-raii",
                "instrumentation-tracebacks",
                "pickling-signatures-code-objects",
                "embedding",
                "third-party-cpython-capi",
                "sets",
                "exception-state",
                "method-function-introspection",
            },
        )
        self.assertEqual(
            {entry["status"] for entry in families.values()},
            {"blocked", "partial", "rejected"},
        )
        for family in families.values():
            with self.subTest(family=family["id"]):
                self.assertTrue(family["migration"].strip())
                self.assertTrue((ROOT / family["evidence"]).is_file())

        closure = (
            ROOT / "docs" / "ahpy" / "audits" /
            "prd4-advanced-surface.md"
        ).read_text(encoding="utf8")
        module_node = (
            ROOT / "Cython" / "Compiler" / "ModuleNode.py"
        ).read_text(encoding="utf8")
        self.assertIn("No row below authorizes CPython, Hybrid, or private HPy",
                      closure)
        for directive in ("profile", "linetrace", "embedsignature"):
            self.assertIn('"%s"' % directive, module_node)
        self.assertIn("C++ output is not implemented", module_node)
        self.assertIn("generated C-line ", module_node)
        self.assertIn("traceback instrumentation; disable", module_node)

    def test_prd5_portability_scope_and_minimal_reproducer_are_locked(self):
        release = tomllib.loads(
            RELEASE_CONTRACT.read_text(encoding="utf8"))
        versions = tomllib.loads(
            VERSION_MANIFEST.read_text(encoding="utf8"))
        self.assertEqual(
            release["python"]["supported_implementation"],
            "CPython",
        )
        self.assertEqual(release["python"]["supported_versions"], ["3.11"])
        self.assertEqual(
            set(release["python"]["unsupported_implementations"]),
            {"PyPy", "GraalPy"},
        )

        failures = versions["development"]["known_failures"]
        self.assertEqual({entry["python"] for entry in failures}, {"3.14.6"})
        for failure in failures:
            with self.subTest(platform=failure["platform"]):
                self.assertTrue((ROOT / failure["reproducer"]).is_file())
                self.assertTrue(
                    (ROOT / failure["reproducer_source"]).is_file())
                self.assertTrue(
                    (
                        ROOT / failure["handwritten_reproducer_source"]
                    ).is_file()
                )
                self.assertIn("not filed", failure["upstream_status"])

        workflow = (
            ROOT / ".github" / "workflows" / "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        development = workflow.split("  development-revision:", 1)[1]
        development = development.split("\n  sanitizers:", 1)[0]
        self.assertLess(
            development.index(
                "Classify minimal HPy heap-type compatibility"),
            development.index("Build, audit, and run Universal module"),
        )
        self.assertIn("reproduce_hpy_dev_closure.py", development)

        audit = (
            ROOT / "docs" / "ahpy" / "audits" /
            "prd5-portability-native-memory.md"
        ).read_text(encoding="utf8")
        self.assertIn("Only one PRD-5 blocker remains", audit)
        self.assertIn("Windows AppVerifier", audit)
        self.assertIn("job 90509136349", audit)
        self.assertIn("exact upstream crash report", audit)

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
            "native-memory-windows:",
            "run_appverifier_hpy.py",
            "ahpy-appverifier-${{ github.run_id }}-${{ github.run_attempt }}",
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

    def test_benchmark_workflows_fetch_upstream_and_fail_closed(self):
        workflows = {
            name: (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf8")
            for name in ("benchmarks.yml", "benchmarks-weekly.yml")
        }
        for name, workflow in workflows.items():
            with self.subTest(workflow=name):
                self.assertIn(
                    "- name: Fetch upstream benchmark revisions", workflow)
                self.assertIn(
                    "git remote add upstream "
                    "https://github.com/cython/cython.git",
                    workflow,
                )
                self.assertIn("git fetch --force --tags upstream", workflow)
                self.assertIn("upstream/master", workflow)
                self.assertNotRegex(
                    workflow, r'COMMITS=\([^\n]*"origin/')
                self.assertIn("set -o pipefail", workflow)
                self.assertIn(
                    "timing_files=(benchmark_results_*.csv)", workflow)
                self.assertIn(
                    "size_files=(benchmark_sizes_*.csv)", workflow)
                self.assertIn(
                    '${#timing_files[@]} == 0 || '
                    '${#size_files[@]} == 0',
                    workflow,
                )
                self.assertIn(
                    '"${timing_files[@]}"', workflow)
                self.assertIn(
                    '"${size_files[@]}"', workflow)
                self.assertIn("if-no-files-found: error", workflow)
                self.assertNotIn("path: benchmark_results_csv", workflow)

        pull_request_triggers = workflows["benchmarks.yml"].split(
            "\nconcurrency:", 1)[0]
        self.assertIn("pull_request:", pull_request_triggers)
        self.assertNotIn("\n    paths:", pull_request_triggers)
        self.assertIn(
            "- name: Select benchmark-relevant changes",
            workflows["benchmarks.yml"],
        )
        self.assertIn(
            "name: benchmark required checks", workflows["benchmarks.yml"])
        self.assertIn("timeout-minutes: 90", workflows["benchmarks.yml"])
        self.assertIn("max-parallel: 5", workflows["benchmarks.yml"])
        for python_name in ("3.14", "3.13", "3.14t", "3.12", "3.10"):
            self.assertIn(f'- name: "{python_name}"', workflows["benchmarks.yml"])
        self.assertNotIn("for PYTHON in", workflows["benchmarks.yml"])
        self.assertIn(
            'free_threaded: true', workflows["benchmarks.yml"])
        self.assertIn(
            'limited_api: "--with-limited"', workflows["benchmarks.yml"])
        self.assertIn(
            "ccache-benchmarks-${{ matrix.name }}", workflows["benchmarks.yml"])
        self.assertIn(
            "benchmark-csv-${{ matrix.name }}-", workflows["benchmarks.yml"])
        self.assertNotIn(
            "startsWith(github.ref, '/refs/pull/')",
            workflows["benchmarks.yml"],
        )
        self.assertNotIn("production-todo.md", workflows["benchmarks.yml"])
        self.assertNotIn('"docs/**"', workflows["benchmarks.yml"])

    def test_expensive_workflows_do_not_duplicate_topic_branch_pushes(self):
        workflow_names = (
            "ahpy-universal.yml",
            "benchmarks.yml",
            "ci.yml",
            "coverage.yml",
            "sanitizers.yml",
            "wheels.yml",
        )
        branch_policy = re.compile(
            r"(?m)^  push:\n"
            r"\s+branches:\n"
            r"\s+- main\n"
            r'\s+- "ahpy/\*\*"$'
        )
        for name in workflow_names:
            workflow = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf8")
            with self.subTest(workflow=name):
                self.assertRegex(workflow, branch_policy)
                self.assertIn("pull_request:", workflow)

        weekly = (ROOT / ".github" / "workflows" /
                  "benchmarks-weekly.yml").read_text(encoding="utf8")
        self.assertRegex(
            weekly,
            re.compile(
                r"(?m)^  push:\n"
                r"\s+branches:\n"
                r"\s+- main$"
            ),
        )
        self.assertNotIn('"ahpy/**"', weekly)

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
            self.assertIn(
                "- name: Build, audit, and run Universal module\n"
                "        timeout-minutes: 30\n",
                job,
            )
            self.assertIn("CFLAGS: -O0", job)
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
        self.assertIn("Manual run 29906185775", validation_matrix)
        self.assertIn("3.15.0-beta.4", validation_matrix)
        self.assertIn("bounded rerun", validation_matrix)
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

    def test_valgrind_lane_is_promoted_and_enforces_real_corpus(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        job = workflow.split("  native-memory-valgrind:\n", 1)[1].split(
            "  native-memory-windows:\n", 1)[0]
        self.assertNotIn("continue-on-error: true", job)
        self.assertIn("native memory gate (Linux Valgrind definite leaks)", job)
        self.assertIn("github.event_name == 'schedule'", job)
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("valgrind", job)
        self.assertIn("run_lsan_hpy.py", job)
        self.assertNotIn("--positive-control-only", job)
        self.assertIn("if: always()", job)
        self.assertIn("valgrind-evidence", job)

    def test_focused_coverage_floors_preserve_complete_backend_coverage(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        self.assertIn("--fail-under backend=100", workflow)
        self.assertIn("--fail-under frontend_seam=45", workflow)
        self.assertIn("--fail-under quality_tools=41", workflow)

    def test_windows_native_memory_lane_is_promoted_and_fail_closed(self):
        workflow = (ROOT / ".github" / "workflows" /
                    "ahpy-universal.yml").read_text(encoding="utf8")
        job = workflow.split("  native-memory-windows:\n", 1)[1].split(
            "  build-portability-artifact:\n", 1)[0]
        self.assertNotIn("continue-on-error: true", job)
        self.assertIn(
            "native memory gate (Windows AppVerifier full page heap)", job)
        self.assertIn("windows-2025", job)
        self.assertIn("github.event_name == 'schedule'", job)
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("run_appverifier_hpy.py", job)
        self.assertIn("appverifier-evidence", job)
        self.assertIn("if: always()", job)
        self.assertNotIn("positive-control-only", job)


if __name__ == "__main__":
    unittest.main()
