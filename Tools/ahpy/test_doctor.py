import os
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

import doctor
from doctor import evaluate_probe, render_text


VERSIONS = {
    "stable": {"version": "0.9.0", "python": ["3.11"]},
    "development": {
        "version_observed": "0.9.1.dev100+gb57a33c1c",
        "python_validated": ["3.11"],
    },
}


def fake_which(name):
    return "/tools/" + name if name in {"clang", "nm"} else None


class DoctorTest(unittest.TestCase):
    def _probe(self, **updates):
        probe = {
            "executable": "/venv/bin/python",
            "implementation": "CPython",
            "python_version": "3.11.9",
            "python_minor": "3.11",
            "hpy_version": "0.9.0",
            "hpy_header": "/venv/include/hpy.h",
            "hpy_header_exists": True,
        }
        probe.update(updates)
        return probe

    def test_python_probe_reports_process_and_json_failures(self):
        with mock.patch.object(
                doctor.subprocess, "run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(self._probe()),
                    stderr="")):
            probe, error = doctor.probe_python("/tool/python")
        self.assertEqual(probe["hpy_version"], "0.9.0")
        self.assertIsNone(error)

        cases = (
            (
                SimpleNamespace(
                    returncode=7, stdout="", stderr="probe failed\n"),
                "failed with exit 7: probe failed",
            ),
            (
                SimpleNamespace(
                    returncode=0, stdout="not-json", stderr=""),
                "invalid probe JSON",
            ),
        )
        for result, message in cases:
            with (
                self.subTest(message=message),
                mock.patch.object(
                    doctor.subprocess, "run", return_value=result),
            ):
                probe, error = doctor.probe_python("/tool/python")
            self.assertIsNone(probe)
            self.assertIn(message, error)

    def test_stable_validated_probe_is_healthy(self):
        probe = {
            "executable": "/venv/bin/python",
            "implementation": "CPython",
            "python_version": "3.11.9",
            "python_minor": "3.11",
            "hpy_version": "0.9.0",
            "hpy_header": "/venv/include/hpy.h",
            "hpy_header_exists": True,
        }
        checks = evaluate_probe(probe, VERSIONS, which=fake_which)
        self.assertFalse(any(check["status"] == "fail" for check in checks))
        self.assertEqual(
            next(check for check in checks if check["id"] == "validated-pin")["status"],
            "pass",
        )

    def test_unknown_pin_and_missing_tools_fail(self):
        probe = {
            "executable": "/venv/bin/python",
            "implementation": "CPython",
            "python_version": "3.14.0",
            "python_minor": "3.14",
            "hpy_version": "1.0.0",
            "hpy_header": "/missing/hpy.h",
            "hpy_header_exists": False,
        }
        checks = evaluate_probe(probe, VERSIONS, which=lambda name: None)
        failures = {check["id"] for check in checks if check["status"] == "fail"}
        self.assertEqual(
            failures,
            {"hpy-header", "validated-pin", "c-compiler", "binary-symbol-reader"},
        )

    def test_missing_probe_import_and_unvalidated_matrix_fail(self):
        checks = evaluate_probe(None, VERSIONS, which=fake_which)
        self.assertEqual(checks, [{
            "id": "python-probe",
            "status": "fail",
            "message": "Python probe did not run",
        }])

        checks = evaluate_probe(
            self._probe(hpy_error="ImportError: missing hpy"),
            VERSIONS,
            which=fake_which,
        )
        self.assertEqual(
            next(check for check in checks if check["id"] == "hpy-import"),
            {"id": "hpy-import", "status": "fail",
             "message": "ImportError: missing hpy"},
        )

        for version, minor in (
                ("0.9.0", "3.14"),
                ("0.9.1.dev100+gb57a33c1c", "3.14")):
            with self.subTest(version=version):
                checks = evaluate_probe(
                    self._probe(hpy_version=version, python_minor=minor),
                    VERSIONS,
                    which=fake_which,
                )
                pin = next(
                    check for check in checks
                    if check["id"] == "validated-pin")
                self.assertEqual(pin["status"], "fail")

    def test_development_pin_is_explicit_warning(self):
        probe = {
            "executable": "/venv/bin/python",
            "implementation": "CPython",
            "python_version": "3.11.9",
            "python_minor": "3.11",
            "hpy_version": "0.9.1.dev100+gb57a33c1c",
            "hpy_header": "/venv/include/hpy.h",
            "hpy_header_exists": True,
        }
        checks = evaluate_probe(probe, VERSIONS, which=fake_which)
        pin = next(check for check in checks if check["id"] == "validated-pin")
        self.assertEqual(pin["status"], "warn")

    def test_text_output_exposes_every_status(self):
        report = {
            "healthy": True,
            "platform": {"system": "TestOS", "release": "1", "machine": "x"},
            "checks": [
                {"id": "ok", "status": "pass", "message": "ready"},
                {"id": "early", "status": "warn", "message": "watch"},
            ],
        }
        output = render_text(report)
        self.assertIn("aHPy doctor: healthy", output)
        self.assertIn("[PASS] ok: ready", output)
        self.assertIn("[WARN] early: watch", output)

    def test_build_report_includes_probe_error_and_health(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            versions = root / "tests" / "ahpy"
            versions.mkdir(parents=True)
            versions.joinpath("hpy-versions.toml").write_text(
                "[stable]\nversion='0.9.0'\npython=['3.11']\n"
                "[development]\nversion_observed='dev'\n"
                "python_validated=['3.11']\n",
                encoding="utf8",
            )
            with mock.patch.object(
                    doctor, "probe_python",
                    return_value=(None, "probe failed")):
                report = doctor.build_report("/tool/python", root)
        self.assertFalse(report["healthy"])
        self.assertEqual(report["selected_python"], "/tool/python")
        self.assertEqual(report["checks"][0]["message"], "probe failed")
        self.assertEqual(report["checks"][1]["id"], "python-probe")

    def test_main_preserves_virtualenv_symlink_path(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "python-target"
            target.touch()
            python = Path(temp) / "python"
            python.symlink_to(target.name)
            with (
                mock.patch.object(
                    doctor, "build_report",
                    return_value={
                        "healthy": True,
                        "platform": {
                            "system": "TestOS", "release": "1", "machine": "x"},
                        "checks": [],
                    },
                ) as build_report,
                mock.patch("sys.argv", ["doctor", "--python", str(python)]),
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(doctor.main(), 0)
            selected = build_report.call_args.args[0]
            self.assertEqual(selected, os.path.abspath(python))
            self.assertEqual(os.path.realpath(python), str(target.resolve()))
            self.assertNotEqual(selected, os.path.realpath(python))

    def test_main_resolves_path_reports_json_and_enforces_status(self):
        reports = (
            ({"healthy": True, "checks": [], "platform": {}}, [], 0),
            ({
                "healthy": True,
                "checks": [{"id": "early", "status": "warn", "message": "x"}],
                "platform": {},
            }, ["--strict"], 1),
            ({
                "healthy": False,
                "checks": [{"id": "bad", "status": "fail", "message": "x"}],
                "platform": {},
            }, [], 1),
        )
        for report, flags, expected in reports:
            argv = [
                "doctor.py", "--python", "reviewed-python", "--json", *flags,
            ]
            with (
                self.subTest(flags=flags, healthy=report["healthy"]),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    doctor.shutil, "which", return_value="/tool/python"),
                mock.patch.object(
                    doctor, "build_report", return_value=report) as build,
                mock.patch("builtins.print") as printed,
            ):
                self.assertEqual(doctor.main(), expected)
            build.assert_called_once_with("/tool/python", doctor.ROOT)
            self.assertEqual(json.loads(printed.call_args.args[0]), report)

        with (
            mock.patch.object(sys, "argv", [
                "doctor.py", "--python", "missing-python"]),
            mock.patch.object(doctor.shutil, "which", return_value=None),
            mock.patch.object(sys, "stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            doctor.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
