#!/usr/bin/env python3
"""Prove clean aHPy sdist, offline install, removal, and onboarding."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahpy_version import (
    AHPY_BUILD_FRONTEND_VERSION,
    AHPY_DISTRIBUTION,
    AHPY_HPY_SUPPORTED_VERSION,
    AHPY_SETUPTOOLS_VERSION,
    AHPY_VERSION,
    CYTHON_BASE_COMMIT,
    provenance_project_urls,
    source_commit,
    validate_source_commit,
)
from pep517_integration import (
    EXAMPLE,
    _copy_frontend_source,
    _frontend_metadata,
    _runtime_program,
)
from release_evidence import write_release_bundle
from verify_reproducible_packages import SOURCE_DATE_EPOCH, normalize_sdist


RELEASE_SOURCE_PATHS = (
    "Cython", "bin", "pyximport", "Tools/ahpy", "tests/ahpy", "docs/ahpy",
    "examples", "setup.py", "setup.cfg", "pyproject.toml", "README.rst",
    "CHANGES.rst", "COPYING.txt", "LICENSE.txt", "MANIFEST.in", "cython.py",
    "ahpy_version.py", "ahpy_build_backend.py", "ahpy_build_config.py",
    "ahpy_hpy_compat.py", "TODO.md", "AGENTTODO.md", "CONTRIBUTING.md",
    "SECURITY.md",
)


def _require_clean_release_source(root=ROOT):
    root = Path(root)
    if not (root / ".git").exists():
        raise AssertionError(
            "release artifact source must be an exact Git checkout")
    result = subprocess.run(
        [
            "git", "status", "--porcelain=v1", "--untracked-files=all",
            "--", *RELEASE_SOURCE_PATHS,
        ],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise AssertionError(
            "cannot verify release source cleanliness: %s" %
            result.stderr.strip())
    if result.stdout.strip():
        raise AssertionError(
            "release artifact source contains uncommitted inputs:\n%s" %
            result.stdout.rstrip())
    return source_commit(root)


def _require_unchanged_release_source(expected_revision):
    observed = _require_clean_release_source()
    if observed != expected_revision:
        raise AssertionError("release source commit changed during the build")
    return observed


def _run(command, *, cwd=None, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _venv_python(venv):
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    result = Path(venv) / relative
    if not result.is_file():
        raise AssertionError("venv did not create %s" % result)
    return str(result)


def _verify_sdist_source_members(
        archive, members, source_root, source_revision):
    source_root = Path(source_root)
    if not (source_root / ".git").exists():
        raise AssertionError("sdist source audit requires a Git checkout")
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *RELEASE_SOURCE_PATHS],
        cwd=source_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise AssertionError(
            "cannot enumerate tracked release inputs: %s" %
            result.stderr.strip())
    tracked = {name for name in result.stdout.split("\0") if name}
    for member in members:
        if not member.isfile():
            continue
        _, separator, relative = member.name.partition("/")
        if not separator:
            raise AssertionError(
                "sdist member lacks one source root: %s" % member.name)
        payload = archive.extractfile(member).read()
        if relative == ".gitrev":
            if payload != (source_revision + "\n").encode("ascii"):
                raise AssertionError("sdist .gitrev differs from source commit")
        elif relative == "PKG-INFO":
            continue
        elif relative not in tracked:
            raise AssertionError(
                "sdist contains an untracked source input: %s" % relative)
        elif (source_root / relative).read_bytes() != payload:
            raise AssertionError(
                "sdist member differs from tracked source: %s" % relative)


def verify_sdist(sdist, source_root=None):
    required_suffixes = (
        "/PKG-INFO",
        "/setup.py",
        "/pyproject.toml",
        "/ahpy_version.py",
        "/ahpy_build_backend.py",
        "/ahpy_build_config.py",
        "/ahpy_hpy_compat.py",
        "/Cython/Compiler/RuntimeAPI.py",
        "/Tools/ahpy/release_artifact_integration.py",
        "/Tools/ahpy/release_evidence.py",
        "/Tools/ahpy/benchmark_hpy.py",
        "/Tools/ahpy/calibrate_performance_budgets.py",
        "/tests/ahpy/benchmark_generated.pyx",
        "/tests/ahpy/benchmark_reference.c",
        "/tests/ahpy/benchmark_external.c",
        "/tests/ahpy/benchmark_external.h",
        "/tests/ahpy/performance-budgets.toml",
        "/docs/ahpy/onboarding.md",
        "/examples/ahpy_pep517/pyproject.toml",
        "/pyximport/__init__.py",
        "/LICENSE.txt",
        "/CONTRIBUTING.md",
        "/SECURITY.md",
        "/.gitrev",
    )
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise AssertionError("unsafe sdist member: %s" % member.name)
            if member.issym() or member.islnk():
                raise AssertionError("sdist must not contain links: %s" % member.name)
        for suffix in required_suffixes:
            if not any(name.endswith(suffix) for name in names):
                raise AssertionError("sdist lacks required member %s" % suffix)
        forbidden = (
            "/.git/", "/__pycache__/", ".DS_Store", ".so", ".pyd", ".pyc",
        )
        for name in names:
            if any(token in name for token in forbidden):
                raise AssertionError("sdist contains forbidden member: %s" % name)
        pkg_info = next(name for name in names if name.endswith("/PKG-INFO"))
        metadata = archive.extractfile(pkg_info).read().decode("utf8")
        revision_name = next(
            name for name in names if name.endswith("/.gitrev"))
        source_revision = validate_source_commit(
            archive.extractfile(revision_name).read().decode("ascii"))
        if source_root is not None:
            if not (Path(source_root) / ".git").exists():
                raise AssertionError(
                    "sdist source audit requires a Git checkout")
            if source_commit(source_root) != source_revision:
                raise AssertionError("sdist revision differs from Git HEAD")
            _verify_sdist_source_members(
                archive, members, source_root, source_revision)
    if "Name: %s\n" % AHPY_DISTRIBUTION not in metadata:
        raise AssertionError("sdist metadata has the wrong distribution name")
    if "Version: %s\n" % AHPY_VERSION not in metadata:
        raise AssertionError("sdist metadata has the wrong version")
    for label, url in provenance_project_urls(source_revision).items():
        if "Project-URL: %s, %s\n" % (label, url) not in metadata:
            raise AssertionError(
                "sdist metadata lacks exact provenance field %s" % label)
    return len(names)


def _assert_frontend(python, present, cwd):
    if present:
        program = (
            "from importlib import metadata\n"
            "assert metadata.version(%r) == %r\n" %
            (AHPY_DISTRIBUTION, AHPY_VERSION) +
            "from Cython.Compiler.RuntimeAPI import HPY_UNIVERSAL_BACKEND\n"
            "assert HPY_UNIVERSAL_BACKEND == 'hpy-universal'\n"
            "hooks = tuple(metadata.entry_points("
            "group='cython.runtime_backend_build_hooks', "
            "name='hpy-universal'))\n"
            "assert len(hooks) == 1\n"
            "assert hooks[0].value == ("
            "'ahpy_hpy_compat:'"
            "'install_hpy_universal_loader_compat')\n"
            "from Cython.Build import Dependencies, cythonize\n"
            "assert 'hpy-universal' not in ("
            "Dependencies._runtime_backend_build_hooks)\n"
            "assert cythonize([], runtime_backend='hpy-universal') == []\n"
            "hook = Dependencies._runtime_backend_build_hooks["
            "'hpy-universal']\n"
            "assert hook.__module__ == 'ahpy_hpy_compat'\n"
            "import ahpy_build_backend, ahpy_build_config, ahpy_hpy_compat\n"
        )
    else:
        program = (
            "from importlib import import_module, metadata, util\n"
            "try:\n"
            "    metadata.version(%r)\n" % AHPY_DISTRIBUTION +
            "except metadata.PackageNotFoundError:\n"
            "    pass\n"
            "else:\n"
            "    raise AssertionError('aHPy distribution survived uninstall')\n"
            "try:\n"
            "    import_module('Cython.Compiler.RuntimeAPI')\n"
            "except ModuleNotFoundError:\n"
            "    pass\n"
            "else:\n"
            "    raise AssertionError('aHPy compiler survived uninstall')\n"
            "assert util.find_spec('ahpy_build_config') is None\n"
            "assert util.find_spec('ahpy_hpy_compat') is None\n"
        )
    _run([python, "-c", program], cwd=cwd)


def _build_provenance(python, expected_source_commit=None):
    program = (
        "from importlib.metadata import version\n"
        "import json, platform, sys, sysconfig\n"
        "print(json.dumps({"
        "'python': platform.python_version(),"
        "'python_implementation': platform.python_implementation(),"
        "'python_executable': sys.executable,"
        "'platform': platform.platform(),"
        "'compiler': sysconfig.get_config_var('CC'),"
        "'build_frontend_version': version('build'),"
        "'installed_hpy': version('hpy'),"
        "'installed_setuptools': version('setuptools')"
        "}, sort_keys=True))\n"
    )
    selected = subprocess.run(
        [python, "-c", program],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    provenance = json.loads(selected.stdout)
    for field, expected in (
        ("build_frontend_version", AHPY_BUILD_FRONTEND_VERSION),
        ("installed_hpy", AHPY_HPY_SUPPORTED_VERSION),
        ("installed_setuptools", AHPY_SETUPTOOLS_VERSION),
    ):
        if provenance[field] != expected:
            raise AssertionError(
                "release provenance requires %s=%s, found %s" % (
                    field, expected, provenance[field]))
    revision = source_commit(ROOT)
    if (expected_source_commit is not None and
            revision != validate_source_commit(expected_source_commit)):
        raise AssertionError("release source commit changed during the build")
    provenance.update({
        "source_commit": revision,
        "cython_base_commit": CYTHON_BASE_COMMIT,
        "hpy_compatibility": AHPY_HPY_SUPPORTED_VERSION,
        "setuptools_compatibility": AHPY_SETUPTOOLS_VERSION,
        "build_frontend": "build",
        "source_date_epoch": int(SOURCE_DATE_EPOCH),
    })
    return provenance


def build_and_run(python, report_path=None, bundle_dir=None):
    python = os.path.abspath(python) if Path(python).exists() else shutil.which(python)
    if python is None:
        raise ValueError("Python interpreter not found")
    if bundle_dir:
        bundle_dir = Path(bundle_dir)
        if bundle_dir.exists() and any(bundle_dir.iterdir()):
            raise ValueError("release bundle directory must be empty")
    with TemporaryDirectory(prefix="ahpy-release-artifacts-") as temp_dir:
        source_revision = _require_clean_release_source()
        temp = Path(temp_dir)
        source = temp / "frontend-source"
        _copy_frontend_source(source)
        artifacts = temp / "artifacts"
        artifacts.mkdir()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("HPY", None)
        environment["NO_CYTHON_COMPILE"] = "true"
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        environment["PYTHONHASHSEED"] = "0"
        environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH

        _run([
            python, "-m", "build", "--sdist", "--no-isolation",
            "--outdir", str(artifacts), str(source),
        ], env=environment)
        sdists = sorted(artifacts.glob("ahpy_compiler-*.tar.gz"))
        if len(sdists) != 1:
            raise AssertionError("expected one clean aHPy sdist")
        sdist = normalize_sdist(sdists[0])
        member_count = verify_sdist(sdist, source_root=ROOT)

        wheelhouse = temp / "wheelhouse"
        wheelhouse.mkdir()
        _run([
            python, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(wheelhouse),
            "hpy==0.9.0", "setuptools==83.0.0",
        ], env=environment)
        dependency_wheels = sorted(wheelhouse.glob("*.whl"))
        dependency_names = [path.name.lower() for path in dependency_wheels]
        if len(dependency_wheels) != 2:
            raise AssertionError("expected exact HPy and setuptools wheels")
        if not any(name.startswith("hpy-0.9.0-") for name in dependency_names):
            raise AssertionError("wheelhouse lacks exact HPy 0.9.0")
        if not any(
                name.startswith("setuptools-83.0.0-")
                for name in dependency_names):
            raise AssertionError("wheelhouse lacks exact setuptools 83.0.0")
        isolated = environment.copy()
        isolated["PIP_FIND_LINKS"] = str(wheelhouse)
        isolated["PIP_NO_INDEX"] = "1"
        _run([
            python, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(artifacts), str(sdist),
        ], env=isolated)
        frontend_wheels = sorted(artifacts.glob("ahpy_compiler-*.whl"))
        if len(frontend_wheels) != 1:
            raise AssertionError("expected one frontend wheel built from sdist")
        frontend_wheel = frontend_wheels[0]
        _frontend_metadata(frontend_wheel)
        shutil.copy2(frontend_wheel, wheelhouse / frontend_wheel.name)

        clean_venv = temp / "clean-venv"
        _run([python, "-m", "venv", str(clean_venv)])
        clean_python = _venv_python(clean_venv)
        install_environment = isolated.copy()
        install_environment.pop("NO_CYTHON_COMPILE", None)
        _run([
            clean_python, "-m", "pip", "install", "--no-index",
            "--find-links", str(wheelhouse),
            "%s==%s" % (AHPY_DISTRIBUTION, AHPY_VERSION), "hpy==0.9.0",
            "setuptools==83.0.0",
        ], cwd=temp, env=install_environment)
        _assert_frontend(clean_python, True, temp)

        project = temp / "onboarding-project"
        shutil.copytree(EXAMPLE, project)
        example_dist = temp / "example-dist"
        example_dist.mkdir()
        _run([
            clean_python, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(example_dist), str(project),
        ], cwd=temp, env=install_environment)
        example_wheels = sorted(example_dist.glob("ahpy_pep517_example-*.whl"))
        if len(example_wheels) != 1:
            raise AssertionError("onboarding did not produce the example wheel")
        example_wheel = example_wheels[0]
        _run([
            clean_python, "-m", "pip", "install", "--no-deps",
            str(example_wheel),
        ], cwd=temp, env=install_environment)
        runtime_environment = environment.copy()
        runtime_environment.pop("NO_CYTHON_COMPILE", None)
        _run([clean_python, "-c", _runtime_program(False)], env=runtime_environment)
        debug_environment = runtime_environment.copy()
        debug_environment["HPY"] = "debug"
        _run([clean_python, "-c", _runtime_program(True)], env=debug_environment)

        _run([
            clean_python, "-m", "pip", "uninstall", "-y",
            AHPY_DISTRIBUTION,
        ], cwd=temp, env=install_environment)
        _assert_frontend(clean_python, False, temp)
        _run([
            clean_python, "-m", "pip", "install", "--no-index",
            "--find-links", str(wheelhouse),
            "%s==%s" % (AHPY_DISTRIBUTION, AHPY_VERSION),
        ], cwd=temp, env=install_environment)
        _assert_frontend(clean_python, True, temp)

        _run([
            clean_python, "-m", "pip", "uninstall", "-y",
            "ahpy-pep517-example",
        ], cwd=temp, env=install_environment)
        _run([
            clean_python, "-c",
            "from importlib.util import find_spec; "
            "assert find_spec('ahpy_pep517_example') is None",
        ], cwd=temp, env=runtime_environment)
        _run([
            clean_python, "-m", "pip", "install", "--no-deps",
            str(example_wheel),
        ], cwd=temp, env=install_environment)
        _run([clean_python, "-c", _runtime_program(False)], env=runtime_environment)

        _require_unchanged_release_source(source_revision)
        report = {
            "schema_version": 2,
            "provenance": _build_provenance(
                python, expected_source_commit=source_revision),
            "sdist": {
                "name": sdist.name,
                "sha256": _sha256(sdist),
                "members": member_count,
            },
            "frontend_wheel": {
                "name": frontend_wheel.name,
                "sha256": _sha256(frontend_wheel),
            },
            "example_wheel": {
                "name": example_wheel.name,
                "sha256": _sha256(example_wheel),
            },
            "build_dependencies": [
                {"name": path.name, "sha256": _sha256(path)}
                for path in dependency_wheels
            ],
            "offline_install": True,
            "frontend_uninstall_reinstall": True,
            "example_uninstall_reinstall": True,
            "runtime_modes": ["normal", "debug", "normal-after-reinstall"],
        }
        if bundle_dir:
            write_release_bundle(
                bundle_dir,
                report,
                [sdist, frontend_wheel, example_wheel, *dependency_wheels],
            )
        if report_path:
            report_path = Path(report_path)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf8",
            )
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle-dir", type=Path)
    args = parser.parse_args()
    report = build_and_run(args.python, args.output, args.bundle_dir)
    print("aHPy clean release-artifact onboarding passed: %s" %
          report["sdist"]["name"])


if __name__ == "__main__":
    main()
