import os
from pathlib import Path
import random
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

import coverage_guided_fuzz as guided
from coverage_guided_fuzz import generate_candidates, greedy_select


class CoverageGuidedFuzzTest(unittest.TestCase):
    def test_candidates_are_deterministic_valid_python(self):
        first = generate_candidates(17, 32)
        second = generate_candidates(17, 32)
        changed = generate_candidates(18, 32)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertEqual(len({candidate["name"] for candidate in first}), 32)
        self.assertEqual(len({candidate["family"] for candidate in first}), 16)
        for candidate in first:
            compile(candidate["source"], candidate["name"], "exec")

    def test_greedy_selection_keeps_new_lines_or_families(self):
        candidates = [
            ({"id": 0, "family": "a", "source": "", "name": "a0"}, {1, 2}),
            ({"id": 1, "family": "a", "source": "", "name": "a1"}, {2}),
            ({"id": 2, "family": "b", "source": "", "name": "b0"}, {2}),
            ({"id": 3, "family": "a", "source": "", "name": "a2"}, {2, 3}),
        ]
        selected, covered = greedy_select(candidates)
        self.assertEqual([candidate["id"] for candidate in selected], [0, 2, 3])
        self.assertEqual(covered, {1, 2, 3})
        self.assertEqual(selected[-1]["new_coverage_lines"], 1)

    def test_candidate_rng_does_not_change_global_random_state(self):
        random.seed(123)
        before = random.getstate()
        generate_candidates(99, 8)
        self.assertEqual(random.getstate(), before)

    def test_guided_hits_filters_unexecuted_and_unmeasured_lines(self):
        measured = guided.GUIDED_FILES[0]
        counts = {
            (measured, 10): 1,
            (measured, 11): 0,
            ("/tmp/unmeasured.py", 12): 1,
        }
        self.assertEqual(
            guided._guided_hits(counts),
            {(str(Path(measured).resolve()), 10)},
        )

    def test_compile_with_trace_returns_guided_hits_and_rejects_errors(self):
        class FakeTracer:
            def __init__(self, errors):
                self.errors = errors

            def runfunc(self, function, *arguments):
                self.function = function
                self.arguments = arguments
                return SimpleNamespace(num_errors=self.errors)

            def results(self):
                return SimpleNamespace(
                    counts={(guided.GUIDED_FILES[0], 10): 1})

        with TemporaryDirectory(prefix="ahpy-guided-compile-") as temp:
            root = Path(temp)
            source = root / "candidate.pyx"
            source.write_text("def candidate():\n    return 1\n", encoding="utf8")
            output = root / "candidate.c"
            tracer = FakeTracer(0)
            hits = guided._compile_with_trace(tracer, source, output)
            self.assertEqual(
                hits, {(str(Path(guided.GUIDED_FILES[0]).resolve()), 10)})
            self.assertIs(tracer.function, guided.Main.compile)
            options = tracer.arguments[1]
            self.assertEqual(options.output_file, str(output))
            self.assertEqual(
                options.runtime_backend, guided.HPY_UNIVERSAL_BACKEND)

            with self.assertRaisesRegex(
                    AssertionError, "guided candidate failed compilation"):
                guided._compile_with_trace(FakeTracer(1), source, output)

    def test_candidate_selection_warms_up_and_tracks_incremental_hits(self):
        candidates = generate_candidates(17, 2)
        cumulative = (
            {("writer.py", 1)},
            {("writer.py", 1), ("writer.py", 2)},
        )
        with TemporaryDirectory(prefix="ahpy-guided-select-") as temp:
            root = Path(temp)
            with (
                mock.patch.object(guided.Main, "compile") as compile,
                mock.patch.object(
                    guided, "_compile_with_trace",
                    side_effect=cumulative) as compile_traced,
            ):
                selected, covered = guided.select_candidates_by_coverage(
                    candidates, root)
            self.assertEqual(compile.call_count, 1)
            self.assertEqual(compile_traced.call_count, 2)
            self.assertTrue((root / "guided_warmup.pyx").is_file())
            self.assertTrue((root / "candidate_000.pyx").is_file())
            self.assertEqual(
                [candidate["id"] for candidate in selected], [0, 1])
            self.assertEqual(
                covered, {("writer.py", 1), ("writer.py", 2)})

    def test_runtime_program_selects_semantic_oracle_and_debug_leak_check(self):
        normal = guided._runtime_program(
            Path("/tmp/source.pyx"), ["guided_000"], False)
        debug = guided._runtime_program(
            Path("/tmp/source.pyx"), ["guided_000"], True)
        self.assertIn("expected = namespace[name]()", normal)
        self.assertNotIn("LeakDetector", normal)
        self.assertIn("LeakDetector", debug)
        self.assertIn("detector.start()", debug)
        self.assertIn("detector.stop()", debug)

    def test_build_and_run_audits_selected_binary_and_runtime_modes(self):
        selected = generate_candidates(17, 3)
        covered = {(guided.GUIDED_FILES[0], 10)}
        calls = []
        binary_box = {}

        def run(command, **options):
            calls.append((command, options))
            if "--build-base" in command:
                build_root = Path(command[command.index("--build-base") + 1])
                binary = build_root / "lib" / "guided_surface.hpy0.so"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"binary")
                binary_box["path"] = binary

        with (
            mock.patch.object(
                guided, "select_candidates_by_coverage",
                return_value=(selected, covered)),
            mock.patch.object(guided, "run", side_effect=run),
            mock.patch.object(guided, "verify_source_boundary") as source_audit,
            mock.patch.object(guided, "verify_binary_boundary") as binary_audit,
            mock.patch.object(
                guided, "require_universal_binary",
                side_effect=lambda _root, _name: binary_box["path"]),
            mock.patch.dict(guided.os.environ, {}, clear=True),
        ):
            result = guided.build_and_run(
                "/tool/python", seed=17, candidate_count=3)

        self.assertEqual(result, (selected, covered))
        self.assertEqual(len(calls), 4)
        source_audit.assert_called_once()
        binary_audit.assert_called_once_with(binary_box["path"])
        self.assertEqual(
            calls[0][1]["env"]["PYTHONPATH"], str(guided.ROOT))
        self.assertNotIn("HPY", calls[2][1]["env"])
        self.assertEqual(calls[3][1]["env"]["HPY"], "debug")
        self.assertIn("LeakDetector", calls[3][0][-1])

    def test_build_and_run_rejects_empty_coverage_selection(self):
        with (
            mock.patch.object(
                guided, "select_candidates_by_coverage",
                return_value=([], set())),
            self.assertRaisesRegex(
                AssertionError, "selected no candidates"),
        ):
            guided.build_and_run("/tool/python", candidate_count=1)

    def test_main_accepts_existing_and_path_interpreters(self):
        selected = [{"family": "arithmetic"}]
        covered = {("writer.py", 1)}
        with TemporaryDirectory(prefix="ahpy-guided-main-") as temp:
            python = Path(temp) / "python"
            python.touch()
            with (
                mock.patch.object(sys, "argv", [
                    "coverage_guided_fuzz.py",
                    "--python", str(python),
                    "--seed", "0x11",
                    "--candidates", "9",
                ]),
                mock.patch.object(
                    guided, "build_and_run",
                    return_value=(selected, covered)) as build,
                mock.patch("builtins.print"),
            ):
                guided.main()
            build.assert_called_once_with(
                os.path.abspath(python), 0x11, 9)

        with (
            mock.patch.object(sys, "argv", [
                "coverage_guided_fuzz.py",
                "--python", "reviewed-python",
                "--candidates", "1",
            ]),
            mock.patch.object(
                guided.shutil, "which", return_value="/tool/python"),
            mock.patch.object(
                guided, "build_and_run",
                return_value=(selected, covered)) as build,
            mock.patch("builtins.print"),
        ):
            guided.main()
        build.assert_called_once_with(
            "/tool/python", guided.DEFAULT_SEED, 1)

    def test_main_rejects_nonpositive_candidates_and_missing_interpreter(self):
        cases = (
            (
                [
                    "coverage_guided_fuzz.py",
                    "--python", "reviewed-python",
                    "--candidates", "0",
                ],
                object(),
            ),
            (
                [
                    "coverage_guided_fuzz.py",
                    "--python", "missing-python",
                    "--candidates", "1",
                ],
                None,
            ),
        )
        for argv, resolved in cases:
            with (
                self.subTest(argv=argv),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    guided.shutil, "which", return_value=resolved),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                guided.main()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
