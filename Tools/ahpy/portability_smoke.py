#!/usr/bin/env python3
"""Stage and diagnose one unchanged Universal HPy portability artifact."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


STAGES = (
    "import-minimal",
    "minimal-semantics",
    "import-constants",
    "constants-semantics",
    "import-fibonacci",
    "fibonacci-semantics",
    "import-types",
    "type-semantics",
    "import-answer",
    "answer-semantics",
)


class PortabilityStageError(RuntimeError):
    def __init__(self, message, records):
        super().__init__(message)
        self.records = records


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(artifact_dir):
    manifest_path = artifact_dir / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    for record in manifest["files"]:
        name = record["name"]
        if Path(name).name != name:
            raise RuntimeError("unsafe portability artifact member: %s" % name)
        path = artifact_dir / name
        if not path.is_file():
            raise RuntimeError("missing portability artifact member: %s" % name)
        if path.stat().st_size != record["size"]:
            raise RuntimeError("portability artifact size mismatch: %s" % name)
        if _sha256(path) != record["sha256"]:
            raise RuntimeError("portability artifact digest mismatch: %s" % name)
    return manifest


def has_python_hpy_loader():
    try:
        return importlib.util.find_spec("hpy.universal") is not None
    except (ImportError, ModuleNotFoundError):
        return False


def prepare_native_directory(artifact_dir, manifest, destination):
    binaries = []
    for record in manifest["files"]:
        name = record["name"]
        if name.endswith((".hpy0.so", ".hpy0.pyd")):
            shutil.copy2(artifact_dir / name, destination / name)
            binaries.append(name)
    if not binaries:
        raise RuntimeError("portability artifact contains no Universal binaries")
    return sorted(binaries)


def _activate_artifact_path(artifact_dir):
    artifact_dir = str(artifact_dir.resolve())
    script_dir = str(Path(__file__).resolve().parent)
    retained = []
    for entry in sys.path:
        resolved = str(Path(entry or os.getcwd()).resolve())
        if resolved != script_dir and resolved != artifact_dir:
            retained.append(entry)
    sys.path[:] = [artifact_dir] + retained


def run_stage(stage, artifact_dir):
    _activate_artifact_path(artifact_dir)
    if stage == "import-minimal":
        import ahpy_minimal  # noqa: F401
        return
    if stage == "minimal-semantics":
        import ahpy_minimal as module

        assert module.answer() == 42
        assert module.return_none() is None
        assert module.make_pair() == [1, 2]
        return
    if stage == "import-constants":
        import constants_only  # noqa: F401
        return
    if stage == "constants-semantics":
        import constants_only as module

        assert module.VALUE == 47
        assert module.NAME == "sabit"
        return
    if stage == "import-fibonacci":
        import fibonacci  # noqa: F401
        return
    if stage == "fibonacci-semantics":
        import fibonacci as module

        assert module.fib(0) == 0
        assert module.fib(10) == 55
        return
    if stage == "import-types":
        import bootstrap_types  # noqa: F401
        return
    if stage == "type-semantics":
        import bootstrap_types as module

        marker = module.make_marker()
        assert type(marker) is module.Marker
        box = module.make_box()
        box.value = marker
        assert box.value is marker
        assert box.owner() is box
        assert box.identity(marker) is marker
        initialized = module.Initialized(marker)
        assert initialized.value is marker
        return
    if stage == "import-answer":
        import bootstrap_answer  # noqa: F401
        return
    if stage == "answer-semantics":
        import bootstrap_answer as module

        assert module.return_none() is None
        assert module.return_big_integer() == \
            1234567890123456789012345678901234567890
        assert module.make_list() == [1, None, 2]
        assert module.make_dict() == {
            "one": 1, 2: [None, {"nested": True}]}
        assert module.default_values("required") == [
            "required", 2, (3, None)]
        assert module.identity("portable") == "portable"
        return
    raise ValueError("unknown portability stage: %s" % stage)


def execute_stages(artifact_dir, loader_mode):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(artifact_dir)
    records = []
    for stage in STAGES:
        print("portability stage start: %s" % stage, flush=True)
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--stage", stage,
                "--artifact-dir", str(artifact_dir),
            ],
            cwd=artifact_dir,
            env=environment,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="", flush=True)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr, flush=True)
        record = {
            "name": stage,
            "returncode": result.returncode,
            "status": "passed" if result.returncode == 0 else "failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        records.append(record)
        if result.returncode != 0:
            if result.returncode < 0:
                detail = "signal %d" % -result.returncode
                record["termination"] = "signal"
                record["signal"] = -result.returncode
            else:
                detail = "exit %d" % result.returncode
                record["termination"] = "exit"
                record["exit_code"] = result.returncode
            raise PortabilityStageError(
                "portability stage %s failed via %s loader with %s" %
                (stage, loader_mode, detail),
                records,
            )
        print("portability stage passed: %s" % stage, flush=True)
    return records


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    artifact_dir = (
        args.artifact_dir.resolve()
        if args.artifact_dir is not None
        else Path(__file__).resolve().parent
    )
    if args.stage is not None:
        run_stage(args.stage, artifact_dir)
        return 0

    report = {
        "schema_version": 1,
        "status": "failed",
        "artifact_dir": str(artifact_dir),
        "stages": [],
    }
    try:
        manifest = verify_manifest(artifact_dir)
        report["artifact_manifest_sha256"] = _sha256(
            artifact_dir / "artifact-manifest.json")
        report["artifact_files"] = manifest["files"]
        loader_mode = "python-stub" if has_python_hpy_loader() else "native"
        provenance = {
            "implementation": platform.python_implementation(),
            "python": platform.python_version(),
            "executable": sys.executable,
            "loader_mode": loader_mode,
            "hpy_universal_loader": loader_mode == "python-stub",
            "extension_suffixes": list(importlib.machinery.EXTENSION_SUFFIXES),
            "builder": manifest["builder"],
        }
        report["provenance"] = provenance
        print(
            "portability provenance: %s" %
            json.dumps(provenance, sort_keys=True),
            flush=True,
        )

        if loader_mode == "python-stub":
            report["stages"] = execute_stages(artifact_dir, loader_mode)
        else:
            with TemporaryDirectory(prefix="ahpy-native-portability-") as temp:
                native_dir = Path(temp)
                binaries = prepare_native_directory(
                    artifact_dir, manifest, native_dir)
                report["native_binaries"] = binaries
                print(
                    "native Universal binaries: %s" % ", ".join(binaries),
                    flush=True,
                )
                report["stages"] = execute_stages(native_dir, loader_mode)
        report["status"] = "passed"
    except PortabilityStageError as failure:
        report["stages"] = failure.records
        report["failure"] = {
            "kind": type(failure).__name__,
            "message": str(failure),
        }
        if args.report is not None:
            write_report(args.report.resolve(), report)
        raise
    except Exception as failure:
        report["failure"] = {
            "kind": type(failure).__name__,
            "message": str(failure),
        }
        if args.report is not None:
            write_report(args.report.resolve(), report)
        raise
    if args.report is not None:
        write_report(args.report.resolve(), report)
    print("Prebuilt Universal HPy artifact: portability smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
