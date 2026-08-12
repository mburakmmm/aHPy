import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest import mock

import run_conformance as conformance


class ConformanceRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.suite_path, cls.suite = conformance.load_manifest()

    def make_modules(self):
        modules = {}

        module_functions = types.ModuleType("conf_module_functions")
        module_functions.add_ints = lambda left, right: left + right
        module_functions.echo = lambda value: value
        module_functions.keyword_mix = (
            lambda first, second=2, *, third=3: (first, second, third))
        modules["module-functions"] = module_functions

        containers = types.ModuleType("conf_containers")
        containers.build_containers = lambda first, second: (
            [first, second], (first, second),
            {"first": first, "second": second}, {first, second})

        def mutate_containers(value):
            items = [value]
            items.append(value + 1)
            mapping = {"value": value}
            mapping["value"] = items[1]
            return items, mapping, items[0]

        containers.mutate_containers = mutate_containers
        modules["containers"] = containers

        exceptions = types.ModuleType("conf_exceptions")

        def divide_or_none(numerator, denominator):
            try:
                return numerator // denominator
            except ZeroDivisionError:
                return None

        def raise_with_payload(value):
            raise ValueError([value])

        def chained_error(value):
            try:
                raise ValueError(value)
            except ValueError as error:
                raise RuntimeError("converted") from error

        exceptions.divide_or_none = divide_or_none
        exceptions.raise_with_payload = raise_with_payload
        exceptions.chained_error = chained_error
        modules["exceptions"] = exceptions

        imports_globals = types.ModuleType("conf_imports_globals")
        imports_globals.use_import = lambda value: value ** 0.5
        imports_globals.read_global = lambda increment: ("aHPy", 40 + increment)
        imports_globals.builtin_lookup = lambda values: (len(values), sum(values))
        modules["imports-globals"] = imports_globals

        cleanup = types.ModuleType("conf_cleanup")

        def consume_or_raise(value, fail):
            temporary = [value]
            if fail:
                raise RuntimeError(temporary)
            return temporary.pop()

        def nested_early_return(flag, value):
            first = [value]
            second = {"first": first}
            if flag:
                return second["first"][0]
            return None

        def loop_cleanup(values, stop):
            for value in values:
                temporary = (value, [value])
                if value == stop:
                    return temporary[0]
            return None

        cleanup.consume_or_raise = consume_or_raise
        cleanup.nested_early_return = nested_early_return
        cleanup.loop_cleanup = loop_cleanup
        modules["cleanup"] = cleanup
        return modules

    def install_modules(self, modules):
        names = {}
        installed = {}
        for surface, module in modules.items():
            names[surface] = module.__name__
            installed[module.__name__] = module
        return names, mock.patch.dict(sys.modules, installed)

    def one_case(self, case_id):
        suite = copy.deepcopy(self.suite)
        suite["cases"] = [
            case for case in suite["cases"] if case["id"] == case_id]
        self.assertEqual(len(suite["cases"]), 1)
        return suite

    def test_manifest_and_suite_are_frontend_neutral_and_pinned(self):
        surfaces = conformance.validate_suite(self.suite)
        self.assertEqual(len(self.suite["cases"]), 21)
        self.assertEqual(surfaces, {
            "module-functions", "containers", "exceptions",
            "imports-globals", "cleanup"})
        manifest_text = conformance.DEFAULT_MANIFEST.read_text(encoding="utf8")
        runner_text = Path(conformance.__file__).read_text(encoding="utf8")
        self.assertNotIn(".pyx", manifest_text)
        self.assertNotIn("tests/run", manifest_text)
        self.assertNotIn("import Cython", runner_text)
        self.assertFalse(self.manifest["frontend_sources_required"])

    def test_full_reference_contract_passes_all_modes(self):
        names, installed = self.install_modules(self.make_modules())
        with installed:
            for mode in ("normal", "trace", "debug"):
                report = conformance.run_suite(
                    self.suite, names, mode, "2026-08-03T16:00:00+00:00")
                self.assertEqual(report["passed"], 21)
                self.assertEqual(report["failed"], 0)
                self.assertEqual(report["mode"], mode)
                self.assertEqual(report["generated_at"], "2026-08-03T16:00:00+00:00")
                self.assertTrue(all(item["status"] == "pass" for item in report["cases"]))

    def test_runner_reports_semantic_and_implementation_failures(self):
        modules = self.make_modules()
        names, installed = self.install_modules(modules)
        with installed:
            modules["module-functions"].add_ints = lambda left, right: 0
            report = conformance.run_suite(
                self.one_case("module.add-positive"),
                {"module-functions": names["module-functions"]})
            self.assertIn("return expectation failed", report["cases"][0]["detail"])

            modules["module-functions"].echo = lambda value: object()
            report = conformance.run_suite(
                self.one_case("module.identity"),
                {"module-functions": names["module-functions"]})
            self.assertIn("identity expectation failed", report["cases"][0]["detail"])

            modules["exceptions"].raise_with_payload = lambda value: value
            report = conformance.run_suite(
                self.one_case("exceptions.payload"),
                {"exceptions": names["exceptions"]})
            self.assertIn("expected builtins.ValueError", report["cases"][0]["detail"])

            def wrong_exception(value):
                raise TypeError(value)

            modules["exceptions"].raise_with_payload = wrong_exception
            report = conformance.run_suite(
                self.one_case("exceptions.payload"),
                {"exceptions": names["exceptions"]})
            self.assertIn("unexpected exception builtins.TypeError", report["cases"][0]["detail"])

            del modules["containers"].mutate_containers
            report = conformance.run_suite(
                self.one_case("containers.mutate"),
                {"containers": names["containers"]})
            self.assertIn("implementation contract error", report["cases"][0]["detail"])

    def test_suite_validation_rejects_malformed_contracts(self):
        invalid = []
        invalid.append({})

        suite = copy.deepcopy(self.suite)
        suite["fixtures"] = []
        invalid.append(suite)

        suite = copy.deepcopy(self.suite)
        suite["fixtures"]["Bad Name"] = {"kind": "fresh-object"}
        invalid.append(suite)

        suite = copy.deepcopy(self.suite)
        suite["cases"] = []
        invalid.append(suite)

        suite = self.one_case("module.add-positive")
        suite["cases"][0].pop("kwargs")
        invalid.append(suite)

        suite = copy.deepcopy(self.suite)
        suite["cases"][1]["id"] = suite["cases"][0]["id"]
        invalid.append(suite)

        for field, value in (("surface", "Bad Surface"), ("callable", "bad.name")):
            suite = self.one_case("module.add-positive")
            suite["cases"][0][field] = value
            invalid.append(suite)

        suite = self.one_case("module.add-positive")
        suite["cases"][0]["args"] = {}
        invalid.append(suite)

        suite = self.one_case("module.add-positive")
        suite["cases"][0]["kwargs"] = {1: 2}
        invalid.append(suite)

        bad_values = [[], {"unknown": []}, {"$ref": "missing"},
                      {"$list": "bad"}, {"$dict": [[1]]}]
        for value in bad_values:
            suite = self.one_case("module.add-positive")
            suite["cases"][0]["args"] = [value]
            invalid.append(suite)

        suite = self.one_case("module.add-positive")
        suite["cases"][0]["expect"] = {}
        invalid.append(suite)

        suite = self.one_case("module.identity")
        suite["cases"][0]["expect"] = {"identity": "missing"}
        invalid.append(suite)

        for raises in ({"type": "builtins.ValueError", "args": {"$tuple": []}, "bad": 1},
                       {"type": "custom.Error", "args": {"$tuple": []}},
                       {"type": "builtins.ValueError"}):
            suite = self.one_case("exceptions.payload")
            suite["cases"][0]["expect"] = {"raises": raises}
            invalid.append(suite)

        suite = self.one_case("module.add-positive")
        suite["cases"][0]["expect"] = {"unknown": 42}
        invalid.append(suite)

        for suite in invalid:
            with self.subTest(suite=suite):
                with self.assertRaises(conformance.ConformanceError):
                    conformance.validate_suite(suite)

    def test_module_maps_and_run_contract_fail_closed(self):
        surfaces = conformance.validate_suite(self.suite)
        values = [f"{surface}=one_module" for surface in sorted(surfaces)]
        self.assertEqual(set(conformance.parse_module_map(values, surfaces)), surfaces)
        for mappings in (
                values[:-1], values + [values[0]], ["bad"], ["unknown=module"]):
            with self.subTest(mappings=mappings):
                with self.assertRaises(conformance.ConformanceError):
                    conformance.parse_module_map(mappings, surfaces)
        with self.assertRaises(conformance.ConformanceError):
            conformance.run_suite(self.suite, {})
        names, installed = self.install_modules(self.make_modules())
        with installed, self.assertRaises(conformance.ConformanceError):
            conformance.run_suite(self.suite, names, "hybrid")

    def test_tag_decoding_matching_and_exception_helpers(self):
        marker = object()
        fixtures = {"marker": marker}
        self.assertIs(conformance._decode({"$ref": "marker"}, fixtures), marker)
        self.assertEqual(conformance._decode({"$tuple": [1]}, fixtures), (1,))
        self.assertEqual(conformance._decode({"$dict": [["a", 1]]}, fixtures), {"a": 1})
        self.assertTrue(conformance._matches(marker, {"$ref": "marker"}, fixtures))
        self.assertTrue(conformance._matches([1], {"$list": [1]}, fixtures))
        self.assertTrue(conformance._matches((1,), {"$tuple": [1]}, fixtures))
        self.assertTrue(conformance._matches({1}, {"$set": [1]}, fixtures))
        self.assertTrue(conformance._matches({"a": 1}, {"$dict": [["a", 1]]}, fixtures))
        self.assertFalse(conformance._matches(True, 1, fixtures))
        self.assertFalse(conformance._matches({1}, {"$set": [{"$list": [1]}]}, fixtures))
        with self.assertRaises(AssertionError):
            conformance._decode({"$unknown": []}, fixtures)
        error = ValueError("bad")
        self.assertEqual(conformance._exception_name(error), "builtins.ValueError")
        self.assertFalse(conformance._match_exception(
            error, {"type": "builtins.TypeError", "args": {"$tuple": ["bad"]}}, fixtures))

    def _write_manifest(self, root, **overrides):
        suite_path = root / "suite.json"
        suite_path.write_text(json.dumps(self.suite), encoding="utf8")
        digest = conformance.hashlib.sha256(suite_path.read_bytes()).hexdigest()
        values = {
            "schema_version": "2",
            "protocol": f'"{conformance.PROTOCOL}"',
            "suite": '"suite.json"',
            "suite_sha256": f'"{digest}"',
            "runner": '"Tools/ahpy/run_conformance.py"',
            "module_contract": '"python-callable-surface-map"',
            "frontend_sources_required": "false",
        }
        values.update(overrides)
        lines = [f"{key} = {value}" for key, value in values.items()]
        lines.extend(["", "[required_gates]"])
        lines.extend(f"{gate} = true" for gate in sorted(conformance.REQUIRED_GATES))
        path = root / "manifest.toml"
        path.write_text("\n".join(lines) + "\n", encoding="utf8")
        return path, suite_path

    def test_manifest_loader_rejects_invalid_metadata_paths_and_content(self):
        with TemporaryDirectory(prefix="ahpy-conformance-manifest-") as temp_dir:
            root = Path(temp_dir)
            path, _ = self._write_manifest(root)
            self.assertEqual(conformance.load_manifest(path)[0]["schema_version"], 2)

            cases = [
                {"schema_version": "1"},
                {"module_contract": '"other"'},
                {"runner": '"other.py"'},
                {"frontend_sources_required": "true"},
                {"suite": "42"},
                {"suite": '"../suite.json"'},
                {"suite_sha256": '"bad"'},
            ]
            for overrides in cases:
                path, _ = self._write_manifest(root, **overrides)
                with self.subTest(overrides=overrides):
                    with self.assertRaises(conformance.ConformanceError):
                        conformance.load_manifest(path)

            path, suite_path = self._write_manifest(root)
            suite_path.write_text("{}", encoding="utf8")
            with self.assertRaisesRegex(conformance.ConformanceError, "SHA-256 mismatch"):
                conformance.load_manifest(path)

            path, _ = self._write_manifest(root)
            text = path.read_text(encoding="utf8").replace("fault_injection = true", "")
            path.write_text(text, encoding="utf8")
            with self.assertRaisesRegex(conformance.ConformanceError, "required_gates"):
                conformance.load_manifest(path)

            with self.assertRaisesRegex(conformance.ConformanceError, "cannot read conformance manifest"):
                conformance.load_manifest(root / "missing.toml")
            broken = root / "broken.toml"
            broken.write_text("not = [valid", encoding="utf8")
            with self.assertRaisesRegex(conformance.ConformanceError, "cannot read conformance manifest"):
                conformance.load_manifest(broken)

            path, suite_path = self._write_manifest(root)
            original_digest = conformance.hashlib.sha256(
                suite_path.read_bytes()).hexdigest()
            suite_path.write_text("not-json", encoding="utf8")
            invalid_digest = conformance.hashlib.sha256(
                suite_path.read_bytes()).hexdigest()
            path.write_text(path.read_text(encoding="utf8").replace(
                original_digest, invalid_digest),
                encoding="utf8")
            with self.assertRaisesRegex(
                    conformance.ConformanceError, "cannot read conformance suite"):
                conformance.load_manifest(path)

    def test_cli_validate_execute_and_failure_exit(self):
        with TemporaryDirectory(prefix="ahpy-conformance-cli-") as temp_dir:
            output = Path(temp_dir) / "nested" / "validation.json"
            self.assertEqual(conformance.main([
                "--validate-only", "--output", str(output)]), 0)
            validation = json.loads(output.read_text(encoding="utf8"))
            self.assertEqual(validation["status"], "valid")
            self.assertEqual(validation["cases"], 21)

            with self.assertRaises(SystemExit):
                conformance.main(["--validate-only", "--module", "cleanup=x"])

            modules = self.make_modules()
            names, installed = self.install_modules(modules)
            arguments = []
            for surface, name in names.items():
                arguments.extend(["--module", f"{surface}={name}"])
            with installed:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(conformance.main(arguments), 0)
                self.assertEqual(json.loads(stdout.getvalue())["passed"], 21)

                modules["module-functions"].add_ints = lambda left, right: 0
                self.assertEqual(conformance.main([
                    "--module", f"module-functions={names['module-functions']}",
                    "--manifest", str(conformance.DEFAULT_MANIFEST),
                    "--output", str(Path(temp_dir) / "failed.json"),
                    *sum((["--module", f"{surface}={name}"]
                          for surface, name in names.items()
                          if surface != "module-functions"), []),
                ]), 1)

    def test_timestamp_and_import_errors_fail_closed(self):
        self.assertRegex(conformance._validated_timestamp(None), r"\+00:00$")
        self.assertEqual(
            conformance._validated_timestamp("2026-08-03T16:00:00Z"),
            "2026-08-03T16:00:00Z")
        for value in (None, "not-a-time", "2026-08-03T16:00:00"):
            if value is None:
                value = 42
            with self.subTest(value=value):
                with self.assertRaises(conformance.ConformanceError):
                    conformance._validated_timestamp(value)
        suite = self.one_case("module.add-positive")
        with self.assertRaisesRegex(conformance.ConformanceError, "cannot import"):
            conformance.run_suite(
                suite, {"module-functions": "definitely_missing_ahpy_module"})


if __name__ == "__main__":
    unittest.main()
