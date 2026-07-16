"""Public-loader stub for the adjacent Universal HPy artifact."""

from importlib.machinery import ModuleSpec
import os
from pathlib import Path
import sys

import hpy.universal as _universal


def __bootstrap__():
    name = __name__
    suffix = ".hpy0.pyd" if os.name == "nt" else ".hpy0.so"
    path = str(Path(__file__).with_name(name + suffix))
    requested = os.environ.get("HPY", "universal").lower()
    mode = (
        _universal.MODE_DEBUG if requested == "debug"
        else _universal.MODE_TRACE if requested == "trace"
        else _universal.MODE_UNIVERSAL
    )
    spec = ModuleSpec(name, None, origin=path)
    sys.modules[name] = _universal.load(name, path, spec, mode)


__bootstrap__()
