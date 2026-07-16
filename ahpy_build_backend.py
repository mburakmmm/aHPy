"""PEP 517 wrapper that pins the installed aHPy frontend and Universal ABI."""

from __future__ import annotations

from importlib import metadata
import shlex

from setuptools import build_meta as _backend

from ahpy_version import AHPY_DISTRIBUTION, AHPY_VERSION


def assert_ahpy_frontend(version_getter=metadata.version):
    """Reject missing, stale, or substituted build frontends."""
    try:
        installed = version_getter(AHPY_DISTRIBUTION)
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "PEP 517 requires the %s distribution; upstream Cython or the "
            "unrelated PyPI ahpy project cannot provide the Universal backend"
            % AHPY_DISTRIBUTION) from exc
    if installed != AHPY_VERSION:
        raise RuntimeError(
            "PEP 517 aHPy frontend mismatch: expected %s, installed %s" %
            (AHPY_VERSION, installed))
    from Cython.Compiler.RuntimeAPI import HPY_UNIVERSAL_BACKEND
    if HPY_UNIVERSAL_BACKEND != "hpy-universal":
        raise RuntimeError("installed aHPy frontend has no Universal backend")
    return installed


def universal_config_settings(config_settings=None):
    """Return a copy with exactly one Universal HPy global option."""
    settings = dict(config_settings or {})
    raw_options = settings.get("--global-option", [])
    if isinstance(raw_options, str):
        raw_options = [raw_options]
    else:
        raw_options = list(raw_options)
    options = []
    abi_options = []
    for raw in raw_options:
        split = shlex.split(str(raw))
        options.extend(split)
        abi_options.extend(
            value for value in split if value.startswith("--hpy-abi="))
    if any(value != "--hpy-abi=universal" for value in abi_options):
        raise RuntimeError(
            "aHPy PEP 517 backend permits only --hpy-abi=universal")
    if not abi_options:
        options.append("--hpy-abi=universal")
    settings["--global-option"] = options
    return settings


def _settings(config_settings):
    assert_ahpy_frontend()
    return universal_config_settings(config_settings)


def get_requires_for_build_wheel(config_settings=None):
    return _backend.get_requires_for_build_wheel(_settings(config_settings))


def prepare_metadata_for_build_wheel(
    metadata_directory, config_settings=None,
):
    return _backend.prepare_metadata_for_build_wheel(
        metadata_directory, _settings(config_settings))


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _backend.build_wheel(
        wheel_directory, _settings(config_settings), metadata_directory)


def get_requires_for_build_sdist(config_settings=None):
    return _backend.get_requires_for_build_sdist(_settings(config_settings))


def build_sdist(sdist_directory, config_settings=None):
    return _backend.build_sdist(sdist_directory, _settings(config_settings))


def get_requires_for_build_editable(config_settings=None):
    return _backend.get_requires_for_build_editable(_settings(config_settings))


def prepare_metadata_for_build_editable(
    metadata_directory, config_settings=None,
):
    return _backend.prepare_metadata_for_build_editable(
        metadata_directory, _settings(config_settings))


def build_editable(
    wheel_directory, config_settings=None, metadata_directory=None,
):
    return _backend.build_editable(
        wheel_directory, _settings(config_settings), metadata_directory)
