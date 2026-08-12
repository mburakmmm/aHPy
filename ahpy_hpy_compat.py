"""Compatibility hooks for supported HPy build toolchains."""

from __future__ import annotations


_LEGACY_IMPORT = "    from pkg_resources import resource_filename\n"
_LEGACY_RESOLVE = (
    "    ext_filepath = resource_filename(__name__, {ext_file!r})\n"
)
_PATH_IMPORT = "    from pathlib import Path\n"
_PATH_RESOLVE = (
    "    ext_filepath = str(Path(__file__).resolve().with_name({ext_file!r}))\n"
)


def install_hpy_universal_loader_compat(hpy_devel=None):
    """Remove the retired ``pkg_resources`` dependency from HPy loader stubs.

    HPy 0.9's generated Universal Python stub only needs the path of the
    adjacent ``.hpy0`` binary.  Setuptools 83 removed ``pkg_resources``, so
    resolve that sibling with the standard library before HPy creates stubs.
    Newer HPy templates that no longer contain the legacy pair are untouched.
    """
    if hpy_devel is None:
        try:
            import hpy.devel as hpy_devel
        except ImportError as exc:
            raise RuntimeError(
                "Universal HPy builds require the hpy package") from exc

    attribute = "_HPY_UNIVERSAL_MODULE_STUB_TEMPLATE"
    try:
        template = getattr(hpy_devel, attribute)
    except AttributeError as exc:
        raise RuntimeError("HPy exposes no Universal loader template") from exc

    has_import = _LEGACY_IMPORT in template
    has_resolve = _LEGACY_RESOLVE in template
    if has_import != has_resolve:
        raise RuntimeError("unrecognized partial HPy pkg_resources loader template")
    if not has_import:
        return False

    template = template.replace(_LEGACY_IMPORT, _PATH_IMPORT, 1)
    template = template.replace(_LEGACY_RESOLVE, _PATH_RESOLVE, 1)
    setattr(hpy_devel, attribute, template)
    return True


def register_hpy_universal_loader_compat():
    """Register loader preparation through Cython's backend-neutral seam."""
    from Cython.Build import register_runtime_backend_build_hook
    from Cython.Compiler.RuntimeAPI import HPY_UNIVERSAL_BACKEND

    return register_runtime_backend_build_hook(
        HPY_UNIVERSAL_BACKEND,
        install_hpy_universal_loader_compat,
    )


register_hpy_universal_loader_compat()
