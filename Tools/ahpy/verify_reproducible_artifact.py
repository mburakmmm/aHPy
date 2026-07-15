#!/usr/bin/env python3
"""Require byte-identical Universal artifacts from two clean builds."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

from build_portability_artifact import build_artifact


def verify(python):
    with TemporaryDirectory(prefix="ahpy-reproducible-") as temp_dir:
        root = Path(temp_dir)
        first = root / "first"
        second = root / "second"
        build_artifact(python, first)
        build_artifact(python, second)
        first_names = sorted(path.name for path in first.iterdir())
        second_names = sorted(path.name for path in second.iterdir())
        if first_names != second_names:
            raise AssertionError(
                "artifact file sets differ: %r != %r" %
                (first_names, second_names))
        mismatches = [
            name for name in first_names
            if (first / name).read_bytes() != (second / name).read_bytes()
        ]
        if mismatches:
            raise AssertionError(
                "artifact files are not reproducible: %s" %
                ", ".join(mismatches))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    python_path = Path(args.python)
    if python_path.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    verify(python)
    print("Universal HPy portability artifact: reproducible build passed")


if __name__ == "__main__":
    main()
