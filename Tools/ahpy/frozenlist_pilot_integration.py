#!/usr/bin/env python3
"""Build the pinned frozenlist extension-type/GC/inheritance HPy pilot."""

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
FIXTURE = ROOT / "tests" / "ahpy" / "pilot_ports" / "frozenlist"
MODULE = "frozenlist_port"
PILOT_ID = "frozenlist-extension-type"
UPSTREAM_COMMIT = "351ad4bb62b30d943b0aa7463a0f85f7339b6ada"
UPSTREAM_SOURCE = "frozenlist/_frozenlist.pyx"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _selected_pilot(manifest):
    matches = [pilot for pilot in manifest.pilots if pilot.id == PILOT_ID]
    if len(matches) != 1:
        raise AssertionError(f"manifest must contain exactly one {PILOT_ID} pilot")
    pilot = matches[0]
    if pilot.commit != UPSTREAM_COMMIT:
        raise AssertionError(
            f"frozenlist pilot commit drifted: {pilot.commit} != {UPSTREAM_COMMIT}")
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
import gc
import weakref
from frozenlist_port import DerivedFrozenList, FrozenList

class Probe:
    pass

class BrokenIterable:
    def __iter__(self):
        raise ValueError("broken iterable")

""" + prefix + """\
items = FrozenList([1, 2])
assert items.frozen is False
assert len(items) == 2
assert items[0] == 1
assert 2 in items
items.append(3)
items.insert(1, 9)
items[0] = 8
del items[2]
items.extend((4, 5))
items.reverse()
assert items.snapshot() == [5, 4, 3, 9, 8]
assert items.count(9) == 1
assert items.index(3) == 2
assert items.pop() == 8
items.remove(9)
assert items.snapshot() == [5, 4, 3]
assert repr(items) == "<FrozenList(frozen=False, [5, 4, 3])>"
try:
    hash(items)
except RuntimeError as error:
    assert str(error) == "Cannot hash unfrozen list."
else:
    raise AssertionError("missing unfrozen hash failure")
items.freeze()
assert items.frozen is True
items_hash = hash(items)
tuple_hash = hash((5, 4, 3))
assert items_hash == tuple_hash, (items_hash, tuple_hash)
for mutation in (
    lambda: items.append(1),
    lambda: items.insert(0, 1),
    lambda: items.__setitem__(0, 1),
    lambda: items.__delitem__(0),
    lambda: items.extend([1]),
    lambda: items.reverse(),
    lambda: items.pop(),
    lambda: items.remove(4),
    lambda: items.clear(),
):
    try:
        mutation()
    except RuntimeError as error:
        assert str(error) == "Cannot modify frozen list."
    else:
        raise AssertionError("missing frozen mutation failure")
assert items.snapshot() == [5, 4, 3]

derived = DerivedFrozenList([10, 20])
assert derived.inherited_size() == 2
derived.append(30)
assert derived.snapshot() == [10, 20, 30]
derived.freeze()
assert hash(derived) == hash((10, 20, 30))

probe = Probe()
probe_ref = weakref.ref(probe)
cycle = FrozenList([probe])
cycle.append(cycle)
del probe
del cycle
for _ in range(3):
    gc.collect()
assert probe_ref() is None

for _ in range(25):
    try:
        FrozenList(BrokenIterable())
    except ValueError as error:
        assert str(error) == "broken iterable"
    else:
        raise AssertionError("missing constructor failure")
""" + suffix


def build_and_run(python, checkout, output=None, manifest_path=DEFAULT_MANIFEST):
    started = time.monotonic()
    manifest = load_manifest(manifest_path)
    pilot = _selected_pilot(manifest)
    checkout = Path(checkout).resolve()
    provenance = verify_checkout(pilot, checkout)
    upstream_source = checkout / UPSTREAM_SOURCE
    with TemporaryDirectory(prefix="ahpy-frozenlist-pilot-") as temp_dir:
        project = Path(temp_dir) / "project"
        shutil.copytree(FIXTURE, project)
        shutil.copy2(checkout / pilot.license_file, project / "LICENSE")
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
                "HPyType_FromSpec",
                "HPyType_SpecParam_Base",
                "HPyField_Store",
                "HPyField_Load",
                "HPy_tp_traverse",
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
                "source_sha256": {UPSTREAM_SOURCE: _sha256(upstream_source)},
                "license_sha256": _sha256(checkout / pilot.license_file),
            },
            "port_contract": {
                "status": "supported-subset",
                "object_field_gc": True,
                "same_module_inheritance": True,
                "free_threading_atomic_semantics": False,
                "omitted_surfaces": [
                    "iterator-protocol",
                    "rich-comparison",
                    "copy-and-deepcopy",
                    "mutable-sequence-registration",
                ],
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
                "gc-cycle": "pass",
                "inheritance": "pass",
                "constructor-failure": "pass",
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
