#!/usr/bin/env python3
"""Build the pinned murmurhash scalar-boundary Universal HPy pilot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from artifact_utils import require_universal_binary
from pilot_matrix import DEFAULT_MANIFEST, load_manifest
from run_pilots import verify_checkout
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "ahpy" / "pilot_ports" / "murmurhash"
MODULE = "ahpy_murmurhash_pilot"
PILOT_ID = "murmurhash-external-c"
UPSTREAM_COMMIT = "58831632dab79389a5cee7715fb688ef2297ff78"
UPSTREAM_FILES = {
    "murmurhash/MurmurHash3.cpp": "upstream/MurmurHash3.cpp",
    "murmurhash/include/murmurhash/MurmurHash3.h":
        "upstream/murmurhash/MurmurHash3.h",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _selected_pilot(manifest):
    matches = [pilot for pilot in manifest.pilots if pilot.id == PILOT_ID]
    if len(matches) != 1:
        raise AssertionError(f"manifest must contain exactly one {PILOT_ID} pilot")
    pilot = matches[0]
    if pilot.commit != UPSTREAM_COMMIT:
        raise AssertionError(
            f"murmurhash pilot commit drifted: {pilot.commit} != {UPSTREAM_COMMIT}")
    return pilot


def _runtime_program(debug=False):
    prefix = ""
    suffix = ""
    if debug:
        prefix = (
            "from hpy.debug import LeakDetector\n"
            "detector = LeakDetector()\n"
            "detector.start()\n"
        )
        suffix = "detector.stop()\n"
    return """\
import ahpy_murmurhash_pilot as module

def rotl32(value, amount):
    return ((value << amount) | (value >> (32 - amount))) & 0xffffffff

def murmur3_u64(value, seed):
    data = value.to_bytes(8, "little")
    h1 = seed & 0xffffffff
    for offset in (0, 4):
        k1 = int.from_bytes(data[offset:offset + 4], "little")
        k1 = (k1 * 0xcc9e2d51) & 0xffffffff
        k1 = rotl32(k1, 15)
        k1 = (k1 * 0x1b873593) & 0xffffffff
        h1 ^= k1
        h1 = rotl32(h1, 13)
        h1 = (h1 * 5 + 0xe6546b64) & 0xffffffff
    h1 ^= 8
    h1 ^= h1 >> 16
    h1 = (h1 * 0x85ebca6b) & 0xffffffff
    h1 ^= h1 >> 13
    h1 = (h1 * 0xc2b2ae35) & 0xffffffff
    h1 ^= h1 >> 16
    return h1

""" + prefix + """\
cases = (
    (0, 0),
    (1, 0),
    (0x0123456789abcdef, 42),
    (0xffffffffffffffff, 0xffffffff),
)
before = module.native_calls()
for value, seed in cases:
    expected = murmur3_u64(value, seed)
    assert module.hash_u64(value, seed) == expected
    assert module.hash_u64_nogil(value, seed) == expected
assert module.native_calls() == before + 2 * len(cases)
for invalid in (-1, 1 << 64):
    calls = module.native_calls()
    try:
        module.hash_u64_nogil(invalid)
    except OverflowError:
        pass
    else:
        raise AssertionError("missing unsigned conversion failure")
    assert module.native_calls() == calls
""" + suffix


def build_and_run(python, checkout, output=None, manifest_path=DEFAULT_MANIFEST):
    started = time.monotonic()
    manifest = load_manifest(manifest_path)
    pilot = _selected_pilot(manifest)
    checkout = Path(checkout).resolve()
    provenance = verify_checkout(pilot, checkout)
    with TemporaryDirectory(prefix="ahpy-murmurhash-pilot-") as temp_dir:
        project = Path(temp_dir) / "project"
        shutil.copytree(FIXTURE, project)
        upstream_hashes = {}
        for source_name, target_name in UPSTREAM_FILES.items():
            source = checkout / source_name
            target = project / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            upstream_hashes[source_name] = _sha256(source)

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        build = project / "build"
        build_started = time.monotonic()
        run([
            python,
            str(project / "setup.py"),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build),
        ], cwd=project, env=environment, stdout=subprocess.DEVNULL)
        build_seconds = time.monotonic() - build_started

        generated = project / (MODULE + ".c")
        verify_source_boundary(
            generated,
            required=(
                "#include <hpy.h>",
                '#include "ahpy_murmur_scalar.h"',
                "HPyThreadState",
                "HPy_LeavePythonExecution",
                "HPy_ReenterPythonExecution",
                "ahpy_murmur3_u64",
            ),
        )
        binary = require_universal_binary(build, MODULE)
        verify_binary_boundary(binary)
        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(binary.parent)
        mode_seconds = {}
        for mode, hpy_mode, debug in (
            ("normal", None, False),
            ("trace", "trace", False),
            ("debug", "debug", True),
        ):
            selected = runtime_environment.copy()
            if hpy_mode:
                selected["HPY"] = hpy_mode
            mode_started = time.monotonic()
            run([
                python, "-c", _runtime_program(debug),
            ], cwd=project, env=selected)
            mode_seconds[mode] = time.monotonic() - mode_started

        report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pilot": PILOT_ID,
            "upstream_commit": pilot.commit,
            "backend": "hpy-universal",
            "python": os.path.abspath(python),
            "provenance": {
                **provenance,
                "source_sha256": upstream_hashes,
            },
            "port_contract": {
                "status": "partial-scalar-adapter",
                "input": "uint64-little-endian",
                "upstream_python_bytes_api_supported": False,
            },
            "gates": {
                "generate": "pass",
                "port-patch": "pass",
                "native-build": "pass",
                "source-audit": "pass",
                "binary-audit": "pass",
                "tests": "pass",
                "normal": "pass",
                "trace": "pass",
                "debug": "pass",
                "conversion-failure": "pass",
            },
            "artifacts": {
                "generated_source": generated.name,
                "binary": binary.name,
            },
            "timings_seconds": {
                "build": build_seconds,
                **mode_seconds,
                "total": time.monotonic() - started,
            },
        }
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    selected = Path(options.python)
    python = os.path.abspath(options.python) if selected.exists() else shutil.which(
        options.python)
    if python is None:
        parser.error(f"Python interpreter not found: {options.python}")
    report = build_and_run(
        python, options.checkout, options.output, options.manifest)
    if options.output is None:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
