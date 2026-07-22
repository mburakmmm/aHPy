#!/usr/bin/env python3
"""Run the generated Universal corpus under Windows Application Verifier."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from direct_build import discover_msvc_environment
from test_generated_hpy import build_and_run


ROOT = Path(__file__).resolve().parents[2]
POSITIVE_CONTROL = ROOT / "tests" / "ahpy" / "appverifier_positive_control.c"
RUNTIME_WRAPPER = Path(__file__).resolve().parent / "appverifier_runtime_wrapper.py"
EXPECTED_RUNTIME_PROCESSES = 5


def _candidate_paths(name, environment=None):
    environment = os.environ if environment is None else environment
    candidates = []
    on_path = shutil.which(name, path=environment.get("PATH"))
    if on_path:
        candidates.append(Path(on_path))
    windows = environment.get("WINDIR")
    program_files = environment.get("ProgramFiles(x86)")
    if windows:
        candidates.append(Path(windows) / "System32" / name)
    if program_files:
        kits = Path(program_files) / "Windows Kits" / "10"
        candidates.extend((
            kits / "App Certification Kit" / name,
            kits / "Debuggers" / "x64" / name,
        ))
        candidates.extend(sorted((kits / "bin").glob("*/x64/%s" % name)))
    unique = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _locate_tool(name, environment=None):
    for candidate in _candidate_paths(name, environment):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Windows native-memory gate requires %s; searched: %s" % (
            name,
            ", ".join(map(str, _candidate_paths(name, environment))) or
            "no Windows SDK locations",
        ))


def _appverif_export_command(appverif, target_name, xml_path):
    return [
        str(appverif),
        "-export", "log",
        "-for", target_name,
        "-with", "To=%s" % xml_path,
    ]


def _xml_severities(path):
    severities = []
    for element in ET.parse(path).iter():
        attributes = {key.lower(): value for key, value in element.attrib.items()}
        severity = attributes.get("severity")
        if severity is not None:
            severities.append(severity.strip().lower())
    return severities


def _xml_errors(path):
    errors = {"error", "0x3f", "0x0000003f", "63"}
    return [value for value in _xml_severities(path) if value in errors]


def _run(command, *, environment=None, cwd=None, check=True, timeout=120):
    return subprocess.run(
        list(map(str, command)),
        env=environment,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def _configure_target(appverif, gflags, target_name, evidence_dir):
    _run([appverif, "-delete", "logs", "-for", target_name], check=False)
    _run([appverif, "-delete", "settings", "-for", target_name], check=False)
    _run([gflags, "/p", "/disable", target_name], check=False)
    _run([appverif, "/verify", target_name])
    _run([gflags, "/p", "/enable", target_name, "/full"])
    query = _run([appverif, "-query", "*", "-for", target_name])
    page_heap = _run([gflags, "/p"])
    (evidence_dir / (target_name + "-appverif-query.txt")).write_text(
        query.stdout + query.stderr, encoding="utf8")
    (evidence_dir / (target_name + "-gflags-query.txt")).write_text(
        page_heap.stdout + page_heap.stderr, encoding="utf8")
    query_text = (query.stdout + query.stderr).lower()
    heap_text = (page_heap.stdout + page_heap.stderr).lower()
    if target_name.lower() not in query_text or "heap" not in query_text:
        raise RuntimeError(
            "AppVerifier query did not prove Basics/heap verification for %s" %
            target_name)
    if target_name.lower() not in heap_text or "full traces" not in heap_text:
        raise RuntimeError(
            "GFlags query did not prove full page heap for %s" % target_name)


def _cleanup_target(appverif, gflags, target_name):
    results = []
    for command in (
        [gflags, "/p", "/disable", target_name],
        [appverif, "-delete", "settings", "-for", target_name],
    ):
        result = _run(command, check=False)
        results.append({
            "command": list(map(str, command)),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    return results


def _compile_positive_control(source, binary, environment):
    compiler = shutil.which("cl.exe", path=environment.get("PATH"))
    if compiler is None:
        raise RuntimeError("Visual C++ environment does not expose cl.exe")
    _run(
        [compiler, "/nologo", "/Od", "/Zi", str(source),
         "/Fe:%s" % binary],
        environment=environment,
        cwd=binary.parent,
    )


def _write_sitecustomize(probe_dir):
    probe_dir.mkdir(parents=True, exist_ok=True)
    source = '''import ctypes
import json
import os
from pathlib import Path

if os.environ.get("AHPY_APPVERIFIER_REQUIRE") == "1":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    modules = ("verifier.dll", "vrfcore.dll", "vfbasics.dll")
    loaded = [name for name in modules if kernel32.GetModuleHandleW(name)]
    token = os.environ["AHPY_APPVERIFIER_TOKEN"]
    marker_dir = Path(os.environ["AHPY_APPVERIFIER_MARKER_DIR"])
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / (token + ".json")
    marker.write_text(json.dumps({
        "schema_version": 1,
        "pid": os.getpid(),
        "loaded_verifier_modules": loaded,
    }, indent=2, sort_keys=True) + "\\n", encoding="utf8")
    if "verifier.dll" not in loaded:
        raise RuntimeError("Application Verifier injection is not active")
'''
    (probe_dir / "sitecustomize.py").write_text(source, encoding="utf8")


def _copy_raw_logs(destination, target_names, source=None):
    source = (Path.home() / "AppVerifierLogs"
              if source is None else Path(source))
    destination.mkdir(parents=True, exist_ok=True)
    normalized_targets = tuple(name.lower() for name in target_names)
    copied = []
    if source.is_dir():
        for item in source.iterdir():
            item_name = item.name.lower()
            if item.is_file() and any(
                    target in item_name for target in normalized_targets):
                target = destination / item.name
                shutil.copy2(item, target)
                copied.append(target)
    if not copied:
        raise RuntimeError(
            "Application Verifier produced no target-specific raw logs")
    return copied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--build-dir",
        default=str(ROOT / "build" / "ahpy-appverifier"),
    )
    args = parser.parse_args()

    if os.name != "nt":
        print(
            "Application Verifier gate requires 64-bit Windows.",
            file=sys.stderr,
        )
        return 2
    if platform.architecture()[0] != "64bit":
        raise RuntimeError("Application Verifier gate requires 64-bit Python")
    if not bool(ctypes.windll.shell32.IsUserAnAdmin()):
        raise RuntimeError("Application Verifier gate requires an admin user")

    python = Path(shutil.which(args.python) or args.python).resolve()
    if not python.is_file():
        raise FileNotFoundError("selected Python does not exist: %s" % python)
    build_dir = Path(args.build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = build_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    probe_dir = build_dir / "probe"
    _write_sitecustomize(probe_dir)

    preflight = {
        "schema_version": 1,
        "appverif_candidates": [
            {"path": str(path), "exists": path.is_file()}
            for path in _candidate_paths("appverif.exe")
        ],
        "gflags_candidates": [
            {"path": str(path), "exists": path.is_file()}
            for path in _candidate_paths("gflags.exe")
        ],
    }
    (build_dir / "preflight.json").write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    appverif = _locate_tool("appverif.exe")
    gflags = _locate_tool("gflags.exe")
    msvc_environment = discover_msvc_environment(platform.machine())
    target_python = python.with_name(
        "ahpy_appverifier_python_%d.exe" % os.getpid())
    positive_binary = build_dir / "ahpy_appverifier_overrun.exe"
    targets = [target_python.name, positive_binary.name]
    cleanup = []
    try:
        shutil.copy2(python, target_python)
        _compile_positive_control(
            POSITIVE_CONTROL, positive_binary, msvc_environment)
        for target in targets:
            _configure_target(appverif, gflags, target, build_dir)

        environment_report = {
            "schema_version": 1,
            "python": sys.version,
            "python_executable": str(python),
            "verified_python": str(target_python),
            "platform": platform.platform(),
            "appverif": str(appverif),
            "gflags": str(gflags),
            "positive_control_sha256": hashlib.sha256(
                POSITIVE_CONTROL.read_bytes()).hexdigest(),
            "expected_runtime_processes": EXPECTED_RUNTIME_PROCESSES,
            "diagnostic_scope": "heap-corruption; not a native leak gate",
        }
        (build_dir / "environment.json").write_text(
            json.dumps(environment_report, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )

        positive = _run([positive_binary], cwd=build_dir, check=False)
        (build_dir / "positive-control.stdout").write_text(
            positive.stdout, encoding="utf8")
        (build_dir / "positive-control.stderr").write_text(
            positive.stderr, encoding="utf8")
        (build_dir / "positive-control-exit.json").write_text(
            json.dumps({"returncode": positive.returncode}, indent=2) + "\n",
            encoding="utf8",
        )
        if positive.returncode == 0:
            raise RuntimeError(
                "full-page-heap positive control was not detected")
        positive_xml = build_dir / "positive-control.xml"
        _run(_appverif_export_command(
            appverif, positive_binary.name, positive_xml))
        if not positive_xml.is_file() or not _xml_errors(positive_xml):
            raise RuntimeError(
                "positive control produced no AppVerifier error entry")

        runtime_prefix = [
            str(python), str(RUNTIME_WRAPPER),
            "--target", str(target_python),
            "--appverif", str(appverif),
            "--probe-dir", str(probe_dir),
            "--evidence-dir", str(runtime_dir),
            "--",
        ]
        build_and_run(str(python), runtime_prefix=runtime_prefix)
        reports = sorted(runtime_dir.glob("runtime-*.json"))
        xml_logs = sorted(runtime_dir.glob("runtime-*.xml"))
        markers = sorted((runtime_dir / "markers").glob("*.json"))
        observed = {
            "reports": len(reports),
            "xml_logs": len(xml_logs),
            "injection_markers": len(markers),
        }
        (build_dir / "runtime-counts.json").write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
        if any(value != EXPECTED_RUNTIME_PROCESSES
               for value in observed.values()):
            raise RuntimeError(
                "expected five verified runtime reports/logs/markers: %r" %
                observed)
        dirty = [str(path) for path in xml_logs if _xml_errors(path)]
        if dirty:
            raise RuntimeError(
                "AppVerifier reported runtime errors: %s" % ", ".join(dirty))
        _copy_raw_logs(build_dir / "raw-logs", targets)
    finally:
        for target in targets:
            cleanup.extend(_cleanup_target(appverif, gflags, target))
        (build_dir / "cleanup.json").write_text(
            json.dumps(cleanup, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
        try:
            target_python.unlink()
        except FileNotFoundError:
            pass

    failed_cleanup = [item for item in cleanup if item["returncode"]]
    if failed_cleanup:
        raise RuntimeError(
            "Application Verifier/GFlags cleanup failed: %r" % failed_cleanup)
    print(
        "Application Verifier gate passed: native overrun detected and five "
        "generated Universal runtime processes were clean."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
