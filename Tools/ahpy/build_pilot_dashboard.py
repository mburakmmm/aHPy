#!/usr/bin/env python3
"""Render a fail-closed PRD-8 compatibility dashboard from CI evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from pilot_matrix import DEFAULT_MANIFEST, ManifestError, load_manifest
from pilot_performance import validate_performance


GATES = (
    "checkout",
    "initial-scan",
    "port-patch",
    "generate",
    "native-build",
    "source-audit",
    "binary-audit",
    "tests",
    "normal",
    "trace",
    "debug",
    "performance",
)
GATE_STATUSES = {"pass", "fail", "blocked", "compiler-error", "not-run"}
INTEGRATION_EXTRA_GATES = {
    "conversion-failure",
    "constructor-failure",
    "gc-cycle",
    "inheritance",
    "installed-debug",
    "installed-normal",
    "installed-trace",
    "wheel-audit",
    "wheel-build",
    "wheel-install",
}
INTEGRATION_GATES = (
    (set(GATES) - {"checkout", "initial-scan"}) | INTEGRATION_EXTRA_GATES)
PORT_CONTRACTS = {
    "selected-source-port",
    "partial-scalar-adapter",
    "supported-subset",
}
PARTIAL_CONTRACTS = {"partial-scalar-adapter", "supported-subset"}


class DashboardError(ValueError):
    """Dashboard input is malformed, inconsistent, or overclaims evidence."""


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardError(f"cannot read pilot evidence {path}: {exc}") from exc


def _validate_timestamp(value, path):
    if not isinstance(value, str):
        raise DashboardError(f"{path}: generated_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DashboardError(f"{path}: invalid generated_at {value!r}") from exc
    if parsed.tzinfo is None:
        raise DashboardError(f"{path}: generated_at must include a timezone")
    return parsed


def load_evidence(path, manifest):
    data = _read_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise DashboardError(f"{path}: unsupported pilot evidence schema")
    if data.get("backend") != "hpy-universal":
        raise DashboardError(f"{path}: evidence backend must be hpy-universal")
    generated_at = _validate_timestamp(data.get("generated_at"), path)
    pilots = data.get("pilots")
    if not isinstance(pilots, list) or not pilots:
        raise DashboardError(f"{path}: pilots must be a non-empty array")
    expected = {pilot.id: pilot for pilot in manifest.pilots}
    observed = {}
    for item in pilots:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise DashboardError(f"{path}: every pilot evidence item needs an id")
        pilot_id = item["id"]
        if pilot_id not in expected:
            raise DashboardError(f"{path}: unknown pilot {pilot_id!r}")
        if pilot_id in observed:
            raise DashboardError(f"{path}: duplicate pilot {pilot_id!r}")
        if item.get("category") != expected[pilot_id].category:
            raise DashboardError(f"{path}: {pilot_id} category mismatch")
        provenance = item.get("provenance")
        if (not isinstance(provenance, dict) or
                provenance.get("head") != expected[pilot_id].commit or
                provenance.get("origin") != expected[pilot_id].repository or
                provenance.get("pristine") is not True):
            raise DashboardError(f"{path}: {pilot_id} provenance mismatch")
        observed[pilot_id] = item
    return generated_at, observed


def load_integration_evidence(path, manifest):
    data = _read_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise DashboardError(f"{path}: unsupported pilot integration schema")
    if data.get("backend") != "hpy-universal":
        raise DashboardError(
            f"{path}: integration backend must be hpy-universal")
    generated_at = _validate_timestamp(data.get("generated_at"), path)
    expected = {pilot.id: pilot for pilot in manifest.pilots}
    pilot_id = data.get("pilot")
    if pilot_id not in expected:
        raise DashboardError(f"{path}: unknown integration pilot {pilot_id!r}")
    pilot = expected[pilot_id]
    if data.get("upstream_commit") != pilot.commit:
        raise DashboardError(f"{path}: {pilot_id} integration commit mismatch")
    provenance = data.get("provenance")
    if provenance is not None and (
            not isinstance(provenance, dict) or
            provenance.get("head") != pilot.commit or
            provenance.get("origin") != pilot.repository or
            provenance.get("pristine") is not True):
        raise DashboardError(
            f"{path}: {pilot_id} integration provenance mismatch")
    contract = data.get("port_contract")
    if not isinstance(contract, dict) or contract.get("status") not in PORT_CONTRACTS:
        raise DashboardError(
            f"{path}: {pilot_id} port_contract status is invalid")
    gates = data.get("gates")
    if not isinstance(gates, dict):
        raise DashboardError(f"{path}: {pilot_id} integration gates are missing")
    unknown = set(gates) - INTEGRATION_GATES
    if unknown:
        raise DashboardError(
            f"{path}: {pilot_id} unknown integration gates: "
            f"{', '.join(sorted(unknown))}")
    canonical = {}
    for gate, value in gates.items():
        status = value.get("status") if isinstance(value, dict) else value
        if status not in GATE_STATUSES:
            raise DashboardError(
                f"{path}: {pilot_id} invalid {gate} status {status!r}")
        if gate in GATES:
            canonical[gate] = status
    if not canonical:
        raise DashboardError(
            f"{path}: {pilot_id} integration has no dashboard gates")
    performance_status = canonical.get("performance")
    performance = data.get("performance")
    if performance_status == "pass":
        if not isinstance(performance, dict) or performance.get(
                "budget_enforced") is not False:
            raise DashboardError(
                f"{path}: {pilot_id} passing performance evidence is incomplete")
        comparison = performance.get("comparison")
        if not isinstance(comparison, str) or not comparison:
            raise DashboardError(
                f"{path}: {pilot_id} performance comparison is missing")
        try:
            validate_performance({
                key: value for key, value in performance.items()
                if key not in {"comparison", "budget_enforced"}
            })
        except AssertionError as exc:
            raise DashboardError(
                f"{path}: {pilot_id} invalid performance evidence: {exc}") from exc
    elif performance is not None:
        raise DashboardError(
            f"{path}: {pilot_id} performance payload requires a passing gate")
    return generated_at, pilot_id, canonical, contract["status"]


def _initial_scan_gate(item):
    scan = item.get("initial_scan")
    if scan is None:
        return "not-run"
    if not isinstance(scan, dict):
        raise DashboardError(f"{item['id']}: initial_scan must be an object")
    observed = scan.get("observed")
    if not isinstance(observed, dict):
        raise DashboardError(f"{item['id']}: initial_scan observed result missing")
    status = observed.get("status")
    if status == "compiler-error":
        return "compiler-error"
    return "pass" if scan.get("expectation_met") is True else "fail"


def _extra_gates(item):
    gates = item.get("gates", {})
    if not isinstance(gates, dict):
        raise DashboardError(f"{item['id']}: gates must be an object")
    unknown = set(gates) - set(GATES)
    if unknown:
        raise DashboardError(
            f"{item['id']}: unknown gates: {', '.join(sorted(unknown))}")
    result = {}
    for gate, value in gates.items():
        status = value.get("status") if isinstance(value, dict) else value
        if status not in GATE_STATUSES:
            raise DashboardError(
                f"{item['id']}: invalid {gate} status {status!r}")
        if gate == "performance" and status == "blocked" and (
                not isinstance(value, dict) or
                not isinstance(value.get("reason"), str) or
                not value["reason"].strip()):
            raise DashboardError(
                f"{item['id']}: blocked performance needs an exact reason")
        result[gate] = status
    return result


def _merge_gate(row, timestamps, gate, status, generated_at, path):
    previous = timestamps.get(gate)
    if previous is not None and generated_at == previous[0] \
            and status != row["gates"][gate]:
        raise DashboardError(
            f"{row['id']}: conflicting {gate} evidence at {generated_at.isoformat()}: "
            f"{previous[1]} and {path}")
    if previous is None or generated_at > previous[0]:
        row["gates"][gate] = status
        timestamps[gate] = (generated_at, str(path))


def build_rows(manifest, evidence_paths=()):
    latest = None
    rows_by_id = {
        pilot.id: {
            "id": pilot.id,
            "category": pilot.category,
            "commit": pilot.commit,
            "contract": None,
            "integration_seen": False,
            "evidence_seen": False,
            "gates": {gate: "not-run" for gate in GATES},
        }
        for pilot in manifest.pilots
    }
    gate_timestamps = {pilot.id: {} for pilot in manifest.pilots}
    contract_timestamps = {}
    used_paths = []
    for path in evidence_paths:
        data = _read_json(path)
        if isinstance(data, dict) and "pilots" in data:
            generated_at, items = load_evidence(path, manifest)
            for pilot_id, item in items.items():
                row = rows_by_id[pilot_id]
                row["evidence_seen"] = True
                _merge_gate(
                    row, gate_timestamps[pilot_id], "checkout", "pass",
                    generated_at, path)
                _merge_gate(
                    row, gate_timestamps[pilot_id], "initial-scan",
                    _initial_scan_gate(item), generated_at, path)
                for gate, status in _extra_gates(item).items():
                    _merge_gate(
                        row, gate_timestamps[pilot_id], gate, status,
                        generated_at, path)
        elif isinstance(data, dict) and "pilot" in data:
            generated_at, pilot_id, gates, contract = \
                load_integration_evidence(path, manifest)
            row = rows_by_id[pilot_id]
            row["evidence_seen"] = True
            row["integration_seen"] = True
            for gate, status in gates.items():
                _merge_gate(
                    row, gate_timestamps[pilot_id], gate, status,
                    generated_at, path)
            previous = contract_timestamps.get(pilot_id)
            if previous is not None and generated_at == previous[0] \
                    and contract != row["contract"]:
                raise DashboardError(
                    f"{pilot_id}: conflicting port contracts at "
                    f"{generated_at.isoformat()}")
            if previous is None or generated_at > previous[0]:
                row["contract"] = contract
                contract_timestamps[pilot_id] = (generated_at, str(path))
        else:
            raise DashboardError(f"{path}: unrecognized pilot evidence shape")
        used_paths.append(str(Path(path).resolve()))
        if latest is None or generated_at > latest:
            latest = generated_at
    rows = []
    for pilot in manifest.pilots:
        row = rows_by_id[pilot.id]
        gates = row["gates"]
        completed = all(
            gates[gate] == "pass"
            for gate in GATES
            if gate not in {"initial-scan", "performance"}
        )
        if "compiler-error" in gates.values():
            overall = "compiler-error"
        elif "fail" in gates.values():
            overall = "fail"
        elif row["contract"] in PARTIAL_CONTRACTS and row["integration_seen"]:
            overall = "partial"
        elif completed and gates["performance"] in {"pass", "blocked"}:
            overall = "pass"
        elif row["integration_seen"]:
            overall = "partial"
        elif (gates["initial-scan"] == "pass" and
              pilot.expected_initial_status == "rejected"):
            overall = "blocked"
        else:
            overall = "not-run"
        row["overall"] = overall
        row.pop("integration_seen")
        row.pop("evidence_seen")
        rows.append(row)
    return {
        "generated_at": latest.isoformat() if latest else None,
        "evidence": used_paths[-1] if used_paths else None,
        "evidence_artifacts": used_paths,
        "rows": rows,
    }


def render_markdown(manifest, dashboard):
    lines = [
        "# aHPy third-party compatibility dashboard",
        "",
        "This file is generated from the pinned PRD-8 manifest and retained "
        "pilot evidence. `not-run` is preserved when no artifact proves a "
        "gate; an expected initial rejection is shown as `blocked`, not as a "
        "compatible library pass.",
        "",
        f"- Manifest selection date: `{manifest.selected_at}`",
        f"- Evidence timestamp: `{dashboard['generated_at'] or 'none'}`",
        f"- Evidence artifacts: `{len(dashboard['evidence_artifacts'])}`",
        "",
        "| Pilot | Category | Commit | Contract | Overall | Checkout | Initial scan | "
        "Generate | Build | Tests | Normal | Trace | Debug | Performance |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in dashboard["rows"]:
        gate = row["gates"]
        lines.append(
            f"| `{row['id']}` | `{row['category']}` | `{row['commit'][:12]}` | "
            f"`{row['contract'] or 'none'}` | **{row['overall']}** | "
            f"{gate['checkout']} | "
            f"{gate['initial-scan']} | {gate['generate']} | "
            f"{gate['native-build']} | {gate['tests']} | {gate['normal']} | "
            f"{gate['trace']} | {gate['debug']} | {gate['performance']} |")
    lines.extend([
        "",
        "A production pass additionally requires the port patch, source audit "
        "and binary audit gates even though the compact table omits those "
        "columns. See `pilot-matrix.md` for the full evidence contract.",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    try:
        manifest = load_manifest(options.manifest)
        dashboard = build_rows(manifest, options.evidence)
        rendered = render_markdown(manifest, dashboard)
    except (ManifestError, DashboardError) as exc:
        parser.error(str(exc))
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
