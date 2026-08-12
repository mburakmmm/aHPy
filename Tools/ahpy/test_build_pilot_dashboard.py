import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import build_pilot_dashboard
from build_pilot_dashboard import DashboardError
from pilot_matrix import load_manifest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "tests" / "ahpy" / "pilots.toml"


class PilotDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest(MANIFEST_PATH)

    def _evidence(self, generated_at="2026-08-02T12:00:00+00:00"):
        return {
            "schema_version": 1,
            "generated_at": generated_at,
            "backend": "hpy-universal",
            "pilots": [
                {
                    "id": pilot.id,
                    "category": pilot.category,
                    "provenance": {
                        "head": pilot.commit,
                        "origin": pilot.repository,
                        "pristine": True,
                    },
                    "initial_scan": {
                        "expectation_met": True,
                        "observed": {"status": pilot.expected_initial_status},
                    },
                }
                for pilot in self.manifest.pilots
            ],
        }

    def _write(self, root, data, name="evidence.json"):
        path = root / name
        path.write_text(json.dumps(data), encoding="utf8")
        return path

    def _integration(self, pilot, generated_at="2026-08-03T13:00:00+00:00",
                     contract="selected-source-port", performance="pass"):
        gates = {
            gate: "pass"
            for gate in build_pilot_dashboard.GATES
            if gate not in {"checkout", "initial-scan", "performance"}
        }
        if performance is not None:
            gates["performance"] = performance
        return {
            "schema_version": 1,
            "generated_at": generated_at,
            "backend": "hpy-universal",
            "pilot": pilot.id,
            "upstream_commit": pilot.commit,
            "provenance": {
                "head": pilot.commit,
                "origin": pilot.repository,
                "pristine": True,
            },
            "port_contract": {"status": contract},
            "gates": gates,
        }

    def test_manifest_only_dashboard_never_infers_evidence(self):
        dashboard = build_pilot_dashboard.build_rows(self.manifest)
        self.assertIsNone(dashboard["generated_at"])
        self.assertTrue(all(row["overall"] == "not-run"
                            for row in dashboard["rows"]))
        self.assertTrue(all(
            set(row["gates"].values()) == {"not-run"}
            for row in dashboard["rows"]
        ))
        self.assertEqual(dashboard["evidence_artifacts"], [])

    def test_evidence_marks_expected_rejections_blocked_not_pass(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            path = self._write(Path(temp), self._evidence())
            dashboard = build_pilot_dashboard.build_rows(self.manifest, [path])
        self.assertTrue(all(row["overall"] == "blocked"
                            for row in dashboard["rows"]))
        self.assertTrue(all(row["gates"]["initial-scan"] == "pass"
                            for row in dashboard["rows"]))

    def test_latest_evidence_wins_and_full_gates_can_pass(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            older = self._write(root, self._evidence(), "older.json")
            newer_data = self._evidence("2026-08-03T12:00:00Z")
            for item in newer_data["pilots"]:
                item["gates"] = {
                    gate: ("blocked" if gate == "performance" else "pass")
                    for gate in build_pilot_dashboard.GATES
                    if gate != "initial-scan"
                }
            newer = self._write(root, newer_data, "newer.json")
            dashboard = build_pilot_dashboard.build_rows(
                self.manifest, [newer, older])
        self.assertEqual(dashboard["generated_at"], "2026-08-03T12:00:00+00:00")
        self.assertTrue(all(row["overall"] == "pass"
                            for row in dashboard["rows"]))

    def test_scan_failure_and_compiler_error_have_distinct_overall_status(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            data = self._evidence()
            data["pilots"][0]["initial_scan"]["expectation_met"] = False
            data["pilots"][1]["initial_scan"]["observed"]["status"] = (
                "compiler-error")
            path = self._write(root, data)
            rows = build_pilot_dashboard.build_rows(
                self.manifest, [path])["rows"]
        self.assertEqual(rows[0]["overall"], "fail")
        self.assertEqual(rows[1]["overall"], "compiler-error")

    def test_rejects_invalid_file_schema_backend_time_and_pilot_shape(self):
        cases = (
            ({}, "unsupported pilot evidence schema"),
            ({**self._evidence(), "backend": "cpython"}, "backend must"),
            ({**self._evidence(), "generated_at": None},
             "must be an ISO-8601 string"),
            ({**self._evidence(), "generated_at": "not-a-time"},
             "invalid generated_at"),
            ({**self._evidence(), "generated_at": "2026-08-02"},
             "include a timezone"),
            ({**self._evidence(), "pilots": {}},
             "pilots must be a non-empty array"),
            ({**self._evidence(), "pilots": [None]},
             "every pilot evidence item needs an id"),
        )
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            for index, (data, message) in enumerate(cases):
                path = self._write(root, data, f"case-{index}.json")
                with self.subTest(message=message), self.assertRaisesRegex(
                        DashboardError, message):
                    build_pilot_dashboard.load_evidence(path, self.manifest)
            malformed = root / "malformed.json"
            malformed.write_text("{", encoding="utf8")
            with self.assertRaisesRegex(DashboardError, "cannot read"):
                build_pilot_dashboard.load_evidence(malformed, self.manifest)

    def test_rejects_unknown_duplicate_or_mismatched_pilots(self):
        mutations = []
        data = self._evidence()
        data["pilots"][0]["id"] = "unknown"
        mutations.append((data, "unknown pilot"))
        data = self._evidence()
        data["pilots"][1]["id"] = data["pilots"][0]["id"]
        mutations.append((data, "duplicate pilot"))
        data = self._evidence()
        data["pilots"][0]["category"] = "external-c"
        mutations.append((data, "category mismatch"))
        data = self._evidence()
        data["pilots"][0]["provenance"]["head"] = "0" * 40
        mutations.append((data, "provenance mismatch"))
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            for index, (data, message) in enumerate(mutations):
                path = self._write(root, data, f"case-{index}.json")
                with self.subTest(message=message), self.assertRaisesRegex(
                        DashboardError, message):
                    build_pilot_dashboard.load_evidence(path, self.manifest)

    def test_matrix_evidence_accepts_a_verified_pilot_subset(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            data = self._evidence()
            data["pilots"] = [data["pilots"][1]]
            path = self._write(root, data)
            dashboard = build_pilot_dashboard.build_rows(self.manifest, [path])
        rows = {row["id"]: row for row in dashboard["rows"]}
        self.assertEqual(rows["murmurhash-external-c"]["overall"], "blocked")
        self.assertEqual(rows["cypack-pure-cython"]["overall"], "not-run")

    def test_merges_checkout_scan_and_integration_artifacts_per_pilot(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            paths = [self._write(root, self._evidence(), "matrix.json")]
            contracts = (
                (self.manifest.pilots[0], "selected-source-port", "pass"),
                (self.manifest.pilots[1], "partial-scalar-adapter", None),
                (self.manifest.pilots[2], "supported-subset", None),
            )
            for index, (pilot, contract, performance) in enumerate(contracts):
                data = self._integration(
                    pilot, contract=contract, performance=performance)
                paths.append(self._write(root, data, f"integration-{index}.json"))
            dashboard = build_pilot_dashboard.build_rows(self.manifest, paths)
        rows = {row["id"]: row for row in dashboard["rows"]}
        self.assertEqual(rows["cypack-pure-cython"]["overall"], "pass")
        self.assertEqual(rows["murmurhash-external-c"]["overall"], "partial")
        self.assertEqual(rows["frozenlist-extension-type"]["overall"], "partial")
        self.assertEqual(rows["bezier-numpy-blocked"]["overall"], "blocked")
        self.assertEqual(
            rows["frozenlist-extension-type"]["contract"], "supported-subset")
        self.assertEqual(len(dashboard["evidence_artifacts"]), 4)

    def test_incomplete_selected_source_integration_is_partial(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-partial-") as temp_dir:
            path = Path(temp_dir) / "cypack.json"
            report = self._integration(self.manifest.pilots[0])
            report["gates"] = {"generate": "pass", "port-patch": "pass"}
            path.write_text(json.dumps(report), encoding="utf8")
            dashboard = build_pilot_dashboard.build_rows(self.manifest, [path])
            row = next(
                item for item in dashboard["rows"]
                if item["id"] == "cypack-pure-cython")
            self.assertEqual(row["contract"], "selected-source-port")
            self.assertEqual(row["overall"], "partial")

    def test_integration_evidence_fails_closed_on_shape_and_provenance(self):
        pilot = self.manifest.pilots[1]
        base = self._integration(pilot)
        mutations = (
            ({**base, "schema_version": 2}, "integration schema"),
            ({**base, "backend": "cpython"}, "integration backend"),
            ({**base, "pilot": "unknown"}, "unknown integration pilot"),
            ({**base, "upstream_commit": "0" * 40}, "commit mismatch"),
            ({**base, "provenance": {}}, "provenance mismatch"),
            ({**base, "port_contract": {"status": "full"}},
             "port_contract status"),
            ({**base, "gates": []}, "integration gates are missing"),
            ({**base, "gates": {"invented": "pass"}},
             "unknown integration gates"),
            ({**base, "gates": {"normal": "maybe"}},
             "invalid normal status"),
            ({**base, "gates": {"wheel-build": "pass"}},
             "has no dashboard gates"),
        )
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            for index, (data, message) in enumerate(mutations):
                path = self._write(root, data, f"case-{index}.json")
                with self.subTest(message=message), self.assertRaisesRegex(
                        DashboardError, message):
                    build_pilot_dashboard.load_integration_evidence(
                        path, self.manifest)

    def test_same_timestamp_conflicting_gate_or_contract_fails_closed(self):
        pilot = self.manifest.pilots[0]
        first = self._integration(pilot)
        gate_conflict = self._integration(pilot)
        gate_conflict["gates"]["normal"] = "fail"
        contract_conflict = self._integration(
            pilot, contract="supported-subset")
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            first_path = self._write(root, first, "first.json")
            gate_path = self._write(root, gate_conflict, "gate.json")
            contract_path = self._write(root, contract_conflict, "contract.json")
            with self.assertRaisesRegex(DashboardError, "conflicting normal"):
                build_pilot_dashboard.build_rows(
                    self.manifest, [first_path, gate_path])
            with self.assertRaisesRegex(DashboardError, "conflicting port contracts"):
                build_pilot_dashboard.build_rows(
                    self.manifest, [first_path, contract_path])

    def test_rejects_unknown_or_invalid_gate_values(self):
        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            root = Path(temp)
            data = self._evidence()
            data["pilots"][0]["gates"] = {"invented": "pass"}
            path = self._write(root, data)
            with self.assertRaisesRegex(DashboardError, "unknown gates"):
                build_pilot_dashboard.build_rows(self.manifest, [path])
            data["pilots"][0]["gates"] = {"normal": "maybe"}
            path = self._write(root, data)
            with self.assertRaisesRegex(DashboardError, "invalid normal status"):
                build_pilot_dashboard.build_rows(self.manifest, [path])

            data = self._evidence()
            data["pilots"][0]["gates"] = []
            path = self._write(root, data)
            with self.assertRaisesRegex(DashboardError, "gates must be an object"):
                build_pilot_dashboard.build_rows(self.manifest, [path])

    def test_initial_scan_absence_and_malformed_shapes_fail_closed(self):
        item = {"id": "pilot"}
        self.assertEqual(build_pilot_dashboard._initial_scan_gate(item), "not-run")
        with self.assertRaisesRegex(DashboardError, "must be an object"):
            build_pilot_dashboard._initial_scan_gate(
                {"id": "pilot", "initial_scan": []})
        with self.assertRaisesRegex(DashboardError, "observed result missing"):
            build_pilot_dashboard._initial_scan_gate(
                {"id": "pilot", "initial_scan": {}})

    def test_markdown_and_cli_render_compact_fail_closed_dashboard(self):
        dashboard = build_pilot_dashboard.build_rows(self.manifest)
        rendered = build_pilot_dashboard.render_markdown(
            self.manifest, dashboard)
        self.assertIn("# aHPy third-party compatibility dashboard", rendered)
        self.assertEqual(rendered.count("**not-run**"), 4)
        self.assertIn("source audit", rendered)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(build_pilot_dashboard.main([
                "--manifest", str(MANIFEST_PATH)]), 0)
        self.assertIn("Evidence timestamp: `none`", stdout.getvalue())

        with tempfile.TemporaryDirectory(prefix="ahpy-dashboard-") as temp:
            output = Path(temp) / "docs" / "dashboard.md"
            self.assertEqual(build_pilot_dashboard.main([
                "--manifest", str(MANIFEST_PATH),
                "--output", str(output),
            ]), 0)
            self.assertTrue(output.is_file())

            bad = Path(temp) / "bad.json"
            bad.write_text("{}", encoding="utf8")
            with self.assertRaises(SystemExit):
                build_pilot_dashboard.main([
                    "--manifest", str(MANIFEST_PATH),
                    "--evidence", str(bad),
                ])


if __name__ == "__main__":
    unittest.main()
