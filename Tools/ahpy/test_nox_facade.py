import copy
import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import nox_facade
import nox_manifest


class NoxFacadeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = nox_facade.nox_manifest.ROOT
        cls.manifest_path = (
            cls.root / "tests" / "ahpy" / "nox-facade-manifest-v1.json")
        cls.golden_path = (
            cls.root / "tests" / "ahpy" / "nox-facade-v1.nox")
        cls.manifest = nox_manifest.load_manifest(cls.manifest_path)

    def export(self, manifest, kind, name):
        return next(
            item for item in manifest["exports"]
            if item["kind"] == kind and item["name"] == name)

    def resort(self, manifest):
        manifest["exports"].sort(key=lambda item: (item["kind"], item["name"]))

    def test_repository_golden_is_reproduced_byte_for_byte(self):
        rendered = nox_facade.generate_facade(copy.deepcopy(self.manifest))
        self.assertEqual(rendered, self.golden_path.read_bytes())
        self.assertTrue(rendered.endswith(b"\n"))
        workflow = (
            self.root / ".github" / "workflows" / "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Generate deterministic typed NOX facade", workflow)
        self.assertIn("nox-facade-v1.nox", workflow)

    def test_facade_maps_host_v1_types_calls_errors_and_lifetimes(self):
        source = nox_facade.generate_facade(self.manifest).decode("utf8")
        for declaration in (
            "payload: list[int]", "value: float", "value: int",
            "value: str", ") -> bool:", ") -> Box:",
        ):
            self.assertIn(declaration, source)
        for call in (
            "call_bool", "call_bytes", "call_float", "call_float_arg",
            "call_int", "call_int_arg", "call_int_keyword", "call_str",
            "call_str_arg", "construct",
        ):
            self.assertIn(".%s(" % call, source)
        self.assertIn("value=positional-only", source)
        self.assertIn("value=positional-or-keyword", source)
        self.assertIn("value=keyword-only", source)
        self.assertIn("except HPyError as error", source)
        self.assertIn('raise _export_error("Box.add", error)', source)
        self.assertIn("def __enter__", source)
        self.assertIn("def __exit__", source)
        self.assertIn("def close", source)
        self.assertNotIn("hpy_package_", source)
        self.assertNotIn(": ptr", source)

    def test_name_collisions_and_orphan_methods_fail_closed(self):
        cases = []

        manifest = copy.deepcopy(self.manifest)
        manifest["package"]["name"] = "answer"
        cases.append((manifest, "package name"))

        manifest = copy.deepcopy(self.manifest)
        self.export(manifest, "module-function", "answer")["name"] = "class"
        self.resort(manifest)
        cases.append((manifest, "NOX facade names"))

        manifest = copy.deepcopy(self.manifest)
        self.export(manifest, "module-function", "answer")["name"] = "CON"
        self.resort(manifest)
        cases.append((manifest, "NOX facade names"))

        manifest = copy.deepcopy(self.manifest)
        self.export(manifest, "module-function", "echo_int")["parameters"][0][
            "name"] = "self"
        cases.append((manifest, "parameter"))

        manifest = copy.deepcopy(self.manifest)
        self.export(manifest, "method", "Box.add")["name"] = "Missing.add"
        self.resort(manifest)
        cases.append((manifest, "no constructor"))

        for manifest, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                    nox_facade.NoxFacadeError, message):
                nox_facade.generate_facade(manifest)

    def test_malformed_class_method_identities_are_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        constructor = self.export(manifest, "constructor", "Box")
        constructor["name"] = "Outer.Box"
        self.resort(manifest)
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "class identifier"):
            nox_facade.generate_facade(manifest)

        manifest = copy.deepcopy(self.manifest)
        constructor = self.export(manifest, "constructor", "Box")
        constructor["name"] = "example_facade"
        self.resort(manifest)
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "class collides with package name"):
            nox_facade.generate_facade(manifest)

        manifest = copy.deepcopy(self.manifest)
        method = self.export(manifest, "method", "Box.add")
        method["name"] = "Box.deep.add"
        self.resort(manifest)
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "Class.method identity"):
            nox_facade.generate_facade(manifest)

    def test_unavailable_call_and_nominal_object_shapes_are_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        constructor = self.export(manifest, "constructor", "Box")
        constructor["parameters"][0]["kind"] = "float64"
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "AHPY_NOX007.*constructor"):
            nox_facade.generate_facade(manifest)

        manifest = copy.deepcopy(self.manifest)
        method = self.export(manifest, "method", "Box.add")
        method["result"] = {"kind": "float64", "ownership": "value"}
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "AHPY_NOX007.*method"):
            nox_facade.generate_facade(manifest)

        manifest = copy.deepcopy(self.manifest)
        answer = self.export(manifest, "module-function", "answer")
        answer["result"] = {"kind": "opaque-object", "ownership": "owned"}
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "AHPY_NOX008.*nominal"):
            nox_facade.generate_facade(manifest)

        manifest = copy.deepcopy(self.manifest)
        answer = self.export(manifest, "module-function", "answer")
        answer["result"] = {"kind": "void", "ownership": "value"}
        with self.assertRaisesRegex(
                nox_facade.NoxFacadeError, "AHPY_NOX007.*call primitive"):
            nox_facade.generate_facade(manifest)

    def test_invalid_manifest_and_generation_failure_leave_output_untouched(self):
        with TemporaryDirectory(prefix="ahpy-nox-facade-test-") as directory:
            output = Path(directory) / "facade.nox"
            output.write_bytes(b"sentinel\n")
            invalid = copy.deepcopy(self.manifest)
            invalid["schema_version"] = 2
            with self.assertRaisesRegex(
                    nox_facade.NoxFacadeError, "schema version"):
                nox_facade.write_facade(invalid, output)
            self.assertEqual(output.read_bytes(), b"sentinel\n")

            unsupported = copy.deepcopy(self.manifest)
            self.export(unsupported, "module-function", "answer")["result"] = {
                "kind": "void", "ownership": "value",
            }
            with self.assertRaises(nox_facade.NoxFacadeError):
                nox_facade.write_facade(unsupported, output)
            self.assertEqual(output.read_bytes(), b"sentinel\n")

            for name in ("CON.nox", "facade. "):
                with self.subTest(name=name), self.assertRaisesRegex(
                        nox_facade.NoxFacadeError, "platform-reserved"):
                    nox_facade.write_facade(
                        self.manifest, Path(directory) / name)

    def test_write_check_and_cli_paths_are_byte_exact(self):
        with TemporaryDirectory(prefix="ahpy-nox-facade-test-") as directory:
            output = Path(directory) / "nested" / "facade.nox"
            rendered = nox_facade.write_facade(self.manifest, output)
            self.assertEqual(output.read_bytes(), rendered)
            self.assertEqual(
                nox_facade.write_facade(self.manifest, output, check=True),
                rendered,
            )
            output.write_bytes(b"stale\n")
            with self.assertRaisesRegex(
                    nox_facade.NoxFacadeError, "stale or non-canonical"):
                nox_facade.write_facade(self.manifest, output, check=True)
            with self.assertRaisesRegex(
                    nox_facade.NoxFacadeError, "cannot read facade"):
                nox_facade.write_facade(
                    self.manifest, Path(directory) / "missing.nox", check=True)

            stdout = mock.Mock()
            stdout.buffer = io.BytesIO()
            with mock.patch.object(sys, "stdout", stdout):
                self.assertEqual(nox_facade.main([
                    "--manifest", str(self.manifest_path),
                ]), 0)
            self.assertEqual(stdout.buffer.getvalue(), self.golden_path.read_bytes())
            self.assertEqual(nox_facade.main([
                "--manifest", str(self.manifest_path),
                "--output", str(output),
            ]), 0)
            self.assertEqual(nox_facade.main([
                "--manifest", str(self.manifest_path),
                "--output", str(output), "--check",
            ]), 0)
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()):
                nox_facade.main([
                    "--manifest", str(self.manifest_path), "--check",
                ])
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()), mock.patch.object(
                        nox_facade.nox_manifest, "load_manifest",
                        side_effect=nox_manifest.NoxManifestError("invalid")):
                nox_facade.main(["--manifest", str(self.manifest_path)])


if __name__ == "__main__":
    unittest.main()
