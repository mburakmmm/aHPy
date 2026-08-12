"""Discovery hook for the deterministic supported-surface fuzz generator."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

import fuzz_supported_surface as fuzz
from fuzz_supported_surface import SupportedSurfaceFuzzTest


class SupportedSurfaceControlTest(unittest.TestCase):
    def test_runtime_program_selects_semantic_oracle_and_debug_leak_check(self):
        normal = fuzz._runtime_program(
            Path("/tmp/source.pyx"), ["fuzz_000"], False)
        debug = fuzz._runtime_program(
            Path("/tmp/source.pyx"), ["fuzz_000"], True)
        self.assertIn("expected = namespace[name]()", normal)
        self.assertIn("type(actual) is type(expected)", normal)
        self.assertNotIn("LeakDetector", normal)
        self.assertIn("LeakDetector", debug)
        self.assertIn("detector.start()", debug)
        self.assertIn("detector.stop()", debug)

    def test_rejected_corpus_requires_diagnostics_without_internal_crash(self):
        results = [
            SimpleNamespace(
                returncode=1, stdout="", stderr=expected)
            for _name, _source, expected in fuzz.REJECTED_CASES
        ]
        with TemporaryDirectory(prefix="ahpy-fuzz-rejected-") as temp:
            root = Path(temp)
            with mock.patch.object(
                    fuzz.subprocess, "run", side_effect=results) as run:
                fuzz.verify_rejected_corpus(
                    "/tool/python", root, {"PYTHONPATH": "/source"})
            self.assertEqual(run.call_count, len(fuzz.REJECTED_CASES))
            self.assertEqual(
                len(list(root.glob("rejected_*.pyx"))),
                len(fuzz.REJECTED_CASES),
            )
            for call in run.call_args_list:
                self.assertEqual(call.kwargs["cwd"], fuzz.ROOT)
                self.assertTrue(call.kwargs["capture_output"])
                self.assertTrue(call.kwargs["text"])

    def test_rejected_corpus_rejects_compile_diagnostic_and_crash_drift(self):
        first_name, _source, expected = fuzz.REJECTED_CASES[0]
        cases = (
            (
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                "compiled: %s" % first_name,
            ),
            (
                SimpleNamespace(returncode=1, stdout="", stderr="other"),
                "lacked",
            ),
            (
                SimpleNamespace(
                    returncode=1,
                    stdout=expected,
                    stderr="Traceback (most recent call last)",
                ),
                "crashed",
            ),
        )
        for result, message in cases:
            with self.subTest(message=message):
                with TemporaryDirectory(prefix="ahpy-fuzz-rejected-") as temp:
                    with (
                        mock.patch.object(
                            fuzz.subprocess, "run", return_value=result),
                        self.assertRaisesRegex(AssertionError, message),
                    ):
                        fuzz.verify_rejected_corpus(
                            "/tool/python", Path(temp), {})

    def test_build_and_run_audits_generated_binary_and_runtime_modes(self):
        calls = []
        binary_box = {}

        def run(command, **options):
            calls.append((command, options))
            if "--build-base" in command:
                build_root = Path(command[command.index("--build-base") + 1])
                binary = build_root / "lib" / "fuzz_surface.hpy0.so"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"binary")
                binary_box["path"] = binary

        with (
            mock.patch.object(fuzz, "verify_rejected_corpus"),
            mock.patch.object(fuzz, "run", side_effect=run),
            mock.patch.object(fuzz, "verify_source_boundary") as source_audit,
            mock.patch.object(fuzz, "verify_binary_boundary") as binary_audit,
            mock.patch.object(
                fuzz, "require_universal_binary",
                side_effect=lambda _root, _name: binary_box["path"]),
            mock.patch.dict(
                fuzz.os.environ,
                {"PYTHONPATH": "untrusted"},
                clear=True,
            ),
        ):
            fuzz.build_and_run("/tool/python", seed=17, case_count=12)

        self.assertEqual(len(calls), 4)
        source_audit.assert_called_once()
        binary_audit.assert_called_once_with(binary_box["path"])
        compile_environment = calls[0][1]["env"]
        self.assertEqual(compile_environment["PYTHONPATH"], str(fuzz.ROOT))
        runtime_calls = calls[2:]
        self.assertNotIn("HPY", runtime_calls[0][1]["env"])
        self.assertEqual(runtime_calls[1][1]["env"]["HPY"], "debug")
        self.assertIn("LeakDetector", runtime_calls[1][0][-1])

    def test_main_accepts_existing_and_path_interpreters(self):
        with TemporaryDirectory(prefix="ahpy-fuzz-main-") as temp:
            python = Path(temp) / "python"
            python.touch()
            with (
                mock.patch.object(sys, "argv", [
                    "fuzz_supported_surface.py",
                    "--python", str(python),
                    "--seed", "0x11",
                    "--cases", "9",
                ]),
                mock.patch.object(fuzz, "build_and_run") as build,
                mock.patch("builtins.print"),
            ):
                fuzz.main()
            build.assert_called_once_with(
                os.path.abspath(python), 0x11, 9)

        with (
            mock.patch.object(sys, "argv", [
                "fuzz_supported_surface.py",
                "--python", "reviewed-python",
                "--cases", "1",
            ]),
            mock.patch.object(
                fuzz.shutil, "which", return_value="/tool/python"),
            mock.patch.object(fuzz, "build_and_run") as build,
            mock.patch("builtins.print"),
        ):
            fuzz.main()
        build.assert_called_once_with(
            "/tool/python", fuzz.DEFAULT_SEED, 1)

    def test_main_rejects_nonpositive_cases_and_missing_interpreter(self):
        cases = (
            (
                [
                    "fuzz_supported_surface.py",
                    "--python", "reviewed-python",
                    "--cases", "0",
                ],
                "--cases must be positive",
                object(),
            ),
            (
                [
                    "fuzz_supported_surface.py",
                    "--python", "missing-python",
                    "--cases", "1",
                ],
                "Python interpreter not found",
                None,
            ),
        )
        for argv, message, resolved in cases:
            with (
                self.subTest(message=message),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(fuzz.shutil, "which", return_value=resolved),
                mock.patch.object(sys, "stderr"),
                self.assertRaises(SystemExit) as raised,
            ):
                fuzz.main()
            self.assertEqual(raised.exception.code, 2)


__all__ = ["SupportedSurfaceFuzzTest", "SupportedSurfaceControlTest"]
