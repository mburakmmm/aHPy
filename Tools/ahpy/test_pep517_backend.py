from importlib import metadata
from unittest import mock
import unittest

import ahpy_build_backend
from ahpy_version import AHPY_DISTRIBUTION, AHPY_VERSION


class Pep517BackendTest(unittest.TestCase):
    def test_frontend_identity_requires_exact_ahpy_distribution(self):
        requested = []
        def exact(name):
            requested.append(name)
            return AHPY_VERSION
        self.assertEqual(
            ahpy_build_backend.assert_ahpy_frontend(exact),
            AHPY_VERSION,
        )
        self.assertEqual(requested, [AHPY_DISTRIBUTION])
        with self.assertRaisesRegex(RuntimeError, "frontend mismatch"):
            ahpy_build_backend.assert_ahpy_frontend(lambda name: "0.0.0")
        def missing(name):
            raise metadata.PackageNotFoundError(name)
        with self.assertRaisesRegex(RuntimeError, "upstream Cython or"):
            ahpy_build_backend.assert_ahpy_frontend(missing)

    def test_config_forces_universal_and_rejects_other_abis(self):
        settings = ahpy_build_backend.universal_config_settings(
            {"--global-option": ["--quiet"]})
        self.assertEqual(
            settings["--global-option"],
            ["--quiet", "--hpy-abi=universal"],
        )
        settings = ahpy_build_backend.universal_config_settings({
            "--global-option": "--hpy-abi=universal",
        })
        self.assertEqual(
            settings["--global-option"].count("--hpy-abi=universal"), 1)
        with self.assertRaisesRegex(RuntimeError, "permits only"):
            ahpy_build_backend.universal_config_settings({
                "--global-option": "--hpy-abi=cpython",
            })

    def test_wheel_hook_checks_identity_and_delegates_with_universal(self):
        with (
            mock.patch.object(
                ahpy_build_backend, "assert_ahpy_frontend",
                return_value=AHPY_VERSION,
            ),
            mock.patch.object(
                ahpy_build_backend._backend, "build_wheel",
                return_value="example.whl",
            ) as build_wheel,
        ):
            result = ahpy_build_backend.build_wheel("dist", {"verbose": "1"})
        self.assertEqual(result, "example.whl")
        settings = build_wheel.call_args.args[1]
        self.assertEqual(
            settings["--global-option"], ["--hpy-abi=universal"])


if __name__ == "__main__":
    unittest.main()
