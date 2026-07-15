#!/usr/bin/env python3
"""Diagnose the local toolchain required by the Universal aHPy backend."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "tests" / "ahpy" / "hpy-versions.toml"

PROBE = r'''
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

result = {
    "executable": sys.executable,
    "implementation": platform.python_implementation(),
    "python_version": platform.python_version(),
    "python_minor": "%d.%d" % sys.version_info[:2],
}
try:
    from hpy.devel import HPyDevel
    include = Path(HPyDevel().include_dir)
    result.update({
        "hpy_version": importlib.metadata.version("hpy"),
        "hpy_include": str(include),
        "hpy_header": str(include / "hpy.h"),
        "hpy_header_exists": (include / "hpy.h").is_file(),
    })
except Exception as exc:
    result["hpy_error"] = "%s: %s" % (type(exc).__name__, exc)
print(json.dumps(result, sort_keys=True))
'''


def _check(check_id, status, message):
    return {"id": check_id, "status": status, "message": message}


def probe_python(python):
    result = subprocess.run(
        [python, "-c", PROBE], capture_output=True, text=True)
    if result.returncode != 0:
        return None, (
            "selected Python probe failed with exit %d: %s" %
            (result.returncode, (result.stderr or result.stdout).strip()))
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, "selected Python returned invalid probe JSON: %s" % exc


def evaluate_probe(probe, versions, which=shutil.which):
    checks = []
    if probe is None:
        return [_check("python-probe", "fail", "Python probe did not run")]
    checks.append(_check(
        "python-probe", "pass",
        "%s %s (%s)" % (
            probe["implementation"], probe["python_version"],
            probe["executable"]),
    ))
    if "hpy_error" in probe:
        checks.append(_check("hpy-import", "fail", probe["hpy_error"]))
    else:
        checks.append(_check(
            "hpy-import", "pass", "HPy %s" % probe["hpy_version"]))
        checks.append(_check(
            "hpy-header",
            "pass" if probe.get("hpy_header_exists") else "fail",
            probe.get("hpy_header", "HPy header path unavailable"),
        ))
        stable = versions["stable"]
        development = versions["development"]
        hpy_version = probe["hpy_version"]
        python_minor = probe["python_minor"]
        if hpy_version == stable["version"]:
            supported = python_minor in stable["python"]
            checks.append(_check(
                "validated-pin", "pass" if supported else "fail",
                "stable HPy %s with Python %s%s" % (
                    hpy_version,
                    python_minor,
                    "" if supported else " is outside the validated matrix",
                ),
            ))
        elif hpy_version == development["version_observed"]:
            supported = python_minor in development["python_validated"]
            checks.append(_check(
                "validated-pin", "warn" if supported else "fail",
                "development HPy %s with Python %s is an early-warning lane" %
                (hpy_version, python_minor),
            ))
        else:
            checks.append(_check(
                "validated-pin", "fail",
                "HPy %s is not stable %s or pinned development %s" % (
                    hpy_version, stable["version"],
                    development["version_observed"],
                ),
            ))

    compilers = {
        name: which(name) for name in ("cc", "gcc", "clang", "cl")
        if which(name)
    }
    checks.append(_check(
        "c-compiler", "pass" if compilers else "fail",
        ", ".join("%s=%s" % item for item in sorted(compilers.items()))
        if compilers else "no C compiler found on PATH",
    ))
    readers = {
        name: which(name)
        for name in ("nm", "llvm-nm", "dumpbin", "objdump")
        if which(name)
    }
    checks.append(_check(
        "binary-symbol-reader", "pass" if readers else "fail",
        ", ".join("%s=%s" % item for item in sorted(readers.items()))
        if readers else "no supported binary symbol reader found on PATH",
    ))
    return checks


def build_report(python, root=ROOT):
    versions_path = Path(root) / "tests" / "ahpy" / "hpy-versions.toml"
    with versions_path.open("rb") as stream:
        versions = tomllib.load(stream)
    probe, error = probe_python(python)
    checks = evaluate_probe(probe, versions)
    if error:
        checks.insert(0, _check("python-probe", "fail", error))
    return {
        "schema_version": 1,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "selected_python": os.path.abspath(python),
        "probe": probe,
        "checks": checks,
        "healthy": not any(check["status"] == "fail" for check in checks),
    }


def render_text(report):
    lines = [
        "aHPy doctor: %s" % ("healthy" if report["healthy"] else "unhealthy"),
        "platform: {system} {release} {machine}".format(**report["platform"]),
    ]
    labels = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for check in report["checks"]:
        lines.append(
            "[%s] %s: %s" %
            (labels[check["status"]], check["id"], check["message"]))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--strict", action="store_true",
        help="return failure for early-warning results as well as failed checks",
    )
    args = parser.parse_args()
    selected = Path(args.python)
    if selected.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    report = build_report(python, args.root)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    has_warning = any(
        check["status"] == "warn" for check in report["checks"])
    return 1 if not report["healthy"] or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
