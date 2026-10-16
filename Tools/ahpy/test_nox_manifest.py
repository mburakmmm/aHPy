import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import nox_integration_policy
import nox_manifest


class NoxManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = nox_integration_policy.load_policy()
        cls.manifest = nox_manifest.load_manifest()

    def assertInvalid(self, data, message=None):
        context = (self.assertRaisesRegex(nox_manifest.NoxManifestError, message)
                   if message else
                   self.assertRaises(nox_manifest.NoxManifestError))
        with context:
            nox_manifest.validate_manifest(data, policy=self.policy)

    def test_repository_fixture_is_canonical_and_complete(self):
        rendered = nox_manifest.canonical_manifest_bytes(
            self.manifest, policy=self.policy)
        self.assertEqual(
            rendered, nox_manifest.DEFAULT_MANIFEST.read_bytes())
        self.assertTrue(rendered.endswith(b"\n"))
        self.assertIn("example.demo", rendered.decode("utf8"))
        self.assertEqual(
            nox_manifest.validate_manifest(
                copy.deepcopy(self.manifest), policy=self.policy),
            self.manifest)
        workflow = (
            nox_manifest.ROOT / ".github" / "workflows" /
            "ahpy-universal.yml"
        ).read_text(encoding="utf8")
        self.assertIn("Validate canonical NOX package manifest fixture", workflow)
        self.assertIn("Tools/ahpy/nox_manifest.py --check-canonical", workflow)
        self.assertIn("packaging-results/nox-hpy-manifest-v1.json", workflow)

    def test_optional_bytes_and_keyword_capabilities_are_explicit(self):
        data = copy.deepcopy(self.manifest)
        data["host"]["required_capabilities"] = sorted(
            data["host"]["required_capabilities"] +
            ["bytes", "call-keywords"])
        answer = data["exports"][-1]
        answer["parameters"] = [{
            "name": "payload",
            "kind": "bytes",
            "call_kind": "keyword-only",
            "ownership": "borrowed",
        }]
        answer["result"] = {"kind": "bytes", "ownership": "value"}
        self.assertIs(nox_manifest.validate_manifest(
            data, policy=self.policy), data)

    def test_root_package_producer_and_host_fail_closed(self):
        mutations = []
        data = copy.deepcopy(self.manifest)
        data["unknown"] = True
        mutations.append((data, "keys mismatch"))
        data = copy.deepcopy(self.manifest)
        data["schema_version"] = 2
        mutations.append((data, "incompatible schema"))
        for field, value in (("name", "Bad Name"), ("version", "")):
            data = copy.deepcopy(self.manifest)
            data["package"][field] = value
            mutations.append((data, "package"))
        data = copy.deepcopy(self.manifest)
        data["package"] = []
        mutations.append((data, "must be an object"))
        for field, value in (
                ("ahpy_version", ""),
                ("cython_base", "main"),
                ("source_digest", "ABC"),
                ("compiler_options_digest", 42)):
            data = copy.deepcopy(self.manifest)
            data["producer"][field] = value
            mutations.append((data, "producer"))
        for field, value in (
                ("profile", "other"),
                ("hpy_abi", "hybrid"),
                ("hpy_version", "latest")):
            data = copy.deepcopy(self.manifest)
            data["host"][field] = value
            mutations.append((data, "host identity"))
        for data, message in mutations:
            with self.subTest(message=message):
                self.assertInvalid(data, message)

    def test_capability_lists_fail_closed(self):
        mutations = []
        for value, message in (
                ([], "non-empty array"),
                ([1], "contain strings"),
                (["module-open", "module-open"], "sorted and unique"),
                (list(reversed(
                    self.manifest["host"]["required_capabilities"])),
                 "sorted and unique")):
            data = copy.deepcopy(self.manifest)
            data["host"]["required_capabilities"] = value
            mutations.append((data, message))
        data = copy.deepcopy(self.manifest)
        data["host"]["required_capabilities"].remove("module-open")
        mutations.append((data, "omits the v1 minimum"))
        data = copy.deepcopy(self.manifest)
        data["host"]["required_capabilities"].append("unknown")
        data["host"]["required_capabilities"].sort()
        mutations.append((data, "unknown capability"))
        for data, message in mutations:
            with self.subTest(message=message):
                self.assertInvalid(data, message)

    def test_module_and_export_identity_fail_closed(self):
        mutations = []
        for field, value, message in (
                ("name", "bad-name", "dotted identifier"),
                ("name", "", "must be a string"),
                ("init_symbol", "HPyInit_other", "does not match")):
            data = copy.deepcopy(self.manifest)
            data["module"][field] = value
            mutations.append((data, message))
        data = copy.deepcopy(self.manifest)
        data["exports"] = "not-an-array"
        mutations.append((data, "exports must be an array"))
        data = copy.deepcopy(self.manifest)
        data["exports"] = list(reversed(data["exports"]))
        mutations.append((data, "sorted and unique"))
        data = copy.deepcopy(self.manifest)
        data["exports"].append(copy.deepcopy(data["exports"][0]))
        data["exports"].sort(key=lambda item: (item["kind"], item["name"]))
        mutations.append((data, "sorted and unique"))
        for field, value, message in (
                ("kind", "callback", "kind is unsupported"),
                ("name", "bad-name", "dotted identifier"),
                ("name", "", "must be a string"),
                ("parameters", "bad", "parameters must be an array")):
            data = copy.deepcopy(self.manifest)
            data["exports"][-1][field] = value
            mutations.append((data, message))
        data = copy.deepcopy(self.manifest)
        data["exports"][-1]["unknown"] = True
        mutations.append((data, "keys mismatch"))
        for data, message in mutations:
            with self.subTest(message=message):
                self.assertInvalid(data, message)

    def test_parameter_and_result_contracts_fail_closed(self):
        def with_parameter(parameter):
            data = copy.deepcopy(self.manifest)
            data["exports"][-1]["parameters"] = [parameter]
            return data

        valid = {
            "name": "value",
            "kind": "int64",
            "call_kind": "positional-only",
            "ownership": "value",
        }
        mutations = []
        for field, value, message in (
                ("name", "bad-name", "not an identifier"),
                ("name", "", "must be a string"),
                ("kind", "container", "unsupported type"),
                ("kind", "bytes", "bytes capability"),
                ("call_kind", "keyword-only", "unavailable"),
                ("call_kind", "variadic", "unavailable"),
                ("ownership", "unknown", "ownership is invalid")):
            parameter = dict(valid)
            parameter[field] = value
            mutations.append((with_parameter(parameter), message))
        parameter = dict(valid)
        parameter["unknown"] = True
        mutations.append((with_parameter(parameter), "keys mismatch"))
        data = copy.deepcopy(self.manifest)
        data["exports"][-1]["parameters"] = [dict(valid), dict(valid)]
        mutations.append((data, "duplicate parameter"))
        for field, value, message in (
                ("kind", "container", "unsupported type"),
                ("kind", "bytes", "bytes capability"),
                ("ownership", "borrowed", "ownership is invalid")):
            data = copy.deepcopy(self.manifest)
            data["exports"][-1]["result"][field] = value
            mutations.append((data, message))
        data = copy.deepcopy(self.manifest)
        data["exports"][-1]["result"] = {
            "kind": "opaque-object", "ownership": "value"}
        mutations.append((data, "object result must be owned"))
        data = copy.deepcopy(self.manifest)
        data["exports"][-1]["result"] = {
            "kind": "int64", "ownership": "owned"}
        mutations.append((data, "scalar result must use value"))
        data = copy.deepcopy(self.manifest)
        data["exports"][0]["result"] = {
            "kind": "int64", "ownership": "value"}
        mutations.append((data, "constructor must return"))
        data = copy.deepcopy(self.manifest)
        data["exports"][-1]["result"]["unknown"] = True
        mutations.append((data, "keys mismatch"))
        for data, message in mutations:
            with self.subTest(message=message):
                self.assertInvalid(data, message)

    def test_artifact_contracts_fail_closed(self):
        mutations = []
        data = copy.deepcopy(self.manifest)
        data["artifacts"] = []
        mutations.append((data, "non-empty array"))
        data = copy.deepcopy(self.manifest)
        data["artifacts"][0]["unknown"] = True
        mutations.append((data, "keys mismatch"))
        for field, value, message in (
                ("target", "plan9-x86", "not declared"),
                ("path", "/tmp/demo.hpy0", "unsafe"),
                ("path", "../demo.hpy0", "unsafe"),
                ("path", "artifact/demo.so", "wrong suffix"),
                ("path", 42, "must be a string"),
                ("sha256", "BAD", "invalid digest"),
                ("size", 0, "positive integer"),
                ("size", True, "positive integer")):
            data = copy.deepcopy(self.manifest)
            data["artifacts"][0][field] = value
            mutations.append((data, message))
        data = copy.deepcopy(self.manifest)
        data["artifacts"].append(copy.deepcopy(data["artifacts"][0]))
        mutations.append((data, "one entry per target"))
        for data, message in mutations:
            with self.subTest(message=message):
                self.assertInvalid(data, message)

    def test_helpers_loader_and_cli_cover_success_and_errors(self):
        with self.assertRaisesRegex(
                nox_manifest.NoxManifestError, "must be an object"):
            nox_manifest._exact_keys([], {"field"}, "test")
        with self.assertRaisesRegex(
                nox_manifest.NoxManifestError, "must be a string"):
            nox_manifest._nonempty_string(1, "test")
        with self.assertRaisesRegex(
                nox_manifest.NoxManifestError, "unsupported type"):
            nox_manifest._validate_value_kind(
                "unknown", set(), self.policy, "test")

        with TemporaryDirectory(prefix="ahpy-nox-manifest-") as temp_dir:
            root = Path(temp_dir)
            missing = root / "missing.json"
            with self.assertRaisesRegex(
                    nox_manifest.NoxManifestError, "cannot read"):
                nox_manifest.load_manifest(missing)
            broken = root / "broken.json"
            broken.write_text("{bad", encoding="utf8")
            with self.assertRaisesRegex(
                    nox_manifest.NoxManifestError, "cannot read"):
                nox_manifest.load_manifest(broken)

            output = root / "nested" / "manifest.json"
            self.assertEqual(nox_manifest.main([
                "--manifest", str(nox_manifest.DEFAULT_MANIFEST),
                "--check-canonical", "--output", str(output),
            ]), 0)
            self.assertEqual(output.read_bytes(),
                             nox_manifest.DEFAULT_MANIFEST.read_bytes())

            noncanonical = root / "noncanonical.json"
            noncanonical.write_text(
                json.dumps(self.manifest, indent=2), encoding="utf8")
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()):
                nox_manifest.main([
                    "--manifest", str(noncanonical), "--check-canonical",
                ])
            with self.assertRaises(SystemExit), mock.patch.object(
                    sys, "stderr", io.StringIO()):
                nox_manifest.main(["--manifest", str(missing)])

        stdout = mock.Mock()
        stdout.buffer = io.BytesIO()
        with mock.patch.object(sys, "stdout", stdout):
            self.assertEqual(nox_manifest.main([
                "--manifest", str(nox_manifest.DEFAULT_MANIFEST),
            ]), 0)
        self.assertEqual(
            stdout.buffer.getvalue(), nox_manifest.DEFAULT_MANIFEST.read_bytes())


if __name__ == "__main__":
    unittest.main()
