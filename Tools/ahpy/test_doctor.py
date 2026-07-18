import os
import io
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
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


if __name__ == "__main__":
    unittest.main()
