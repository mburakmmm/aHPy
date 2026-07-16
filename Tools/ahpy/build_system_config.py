#!/usr/bin/env python3
"""Emit one validated Universal HPy contract for CMake or Meson."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_build_config import (
    create_contract,
    probe_toolchain,
    render_cmake,
    render_meson,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--module", required=True)
    parser.add_argument("--runtime", choices=("auto", "static", "sources"),
                        default="auto")
    parser.add_argument("--format", choices=("json", "cmake", "meson"),
                        default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = create_contract(
        probe_toolchain(args.python), args.module, args.runtime)
    if args.format == "json":
        rendered = json.dumps(contract, indent=2, sort_keys=True) + "\n"
    elif args.format == "cmake":
        rendered = render_cmake(contract)
    else:
        rendered = render_meson(contract)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf8")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
