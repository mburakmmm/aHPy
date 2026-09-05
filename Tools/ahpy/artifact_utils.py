"""Locate loadable Universal HPy extension binaries without linker sidecars."""

from __future__ import annotations

import os
from pathlib import Path


def universal_extension_suffix(os_name=None):
    """Return the native Universal HPy extension suffix for *os_name*."""
    if os_name is None:
        os_name = os.name
    return ".hpy0.pyd" if os_name == "nt" else ".hpy0.so"


def find_universal_binaries(
    root, module_name=None, *, os_name=None, extension_suffix=None,
):
    """Return sorted loadable Universal binaries below *root*.

    MSVC emits ``.hpy0.lib`` and ``.hpy0.exp`` linker sidecars next to build
    objects.  Matching the complete HPy extension suffix keeps those files out
    of runtime, audit, and packaging decisions.
    """
    if extension_suffix is None:
        extension_suffix = universal_extension_suffix(os_name)
    if not extension_suffix.startswith(".hpy0."):
        raise ValueError(
            "Universal HPy extension suffix must start with .hpy0.: %s" %
            extension_suffix)

    if module_name is None:
        pattern = "*" + extension_suffix
    else:
        module_basename = module_name.rsplit(".", 1)[-1]
        pattern = module_basename + extension_suffix
    return sorted(
        path for path in Path(root).rglob(pattern) if path.is_file())


def require_universal_binary(
    root, module_name, *, os_name=None, extension_suffix=None,
):
    """Return the only loadable Universal binary for *module_name*."""
    binaries = find_universal_binaries(
        root,
        module_name,
        os_name=os_name,
        extension_suffix=extension_suffix,
    )
    if len(binaries) != 1:
        raise AssertionError(
            "expected one %s Universal HPy binary, got %r" %
            (module_name, binaries))
    return binaries[0]
