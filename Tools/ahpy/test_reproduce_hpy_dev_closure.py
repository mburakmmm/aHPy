import signal
import unittest
from types import SimpleNamespace

from reproduce_hpy_dev_closure import require_runtime_success


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


if __name__ == "__main__":
    unittest.main()
