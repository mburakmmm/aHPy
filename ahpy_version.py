"""aHPy distribution identity, separate from the embedded Cython version."""

from pathlib import Path
import re
import subprocess


AHPY_DISTRIBUTION = "aHPy-compiler"
AHPY_VERSION = "3.3.0.1.dev0"
CYTHON_BASE_VERSION = "3.3.0a2.dev0"
CYTHON_BASE_COMMIT = "b99cb0e3b5425e11414cadd24168a6cc850e8000"
AHPY_HPY_SUPPORTED_VERSION = "0.9.0"
AHPY_SETUPTOOLS_VERSION = "83.0.0"
AHPY_BUILD_FRONTEND_VERSION = "1.5.0"

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def validate_source_commit(commit):
    commit = str(commit).strip()
    if not _COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeError(
            "aHPy package provenance requires one full lowercase Git commit")
    return commit


def source_commit(root=None):
    """Resolve the exact source commit from an archive or Git checkout."""
    root = Path(root or Path(__file__).resolve().parent)
    revision_file = root / ".gitrev"
    git_marker = root / ".git"
    if not git_marker.exists() and revision_file.is_file():
        return validate_source_commit(
            revision_file.read_text(encoding="ascii"))
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(
            "aHPy package source has neither .gitrev nor a readable Git HEAD")
    return validate_source_commit(result.stdout)


def provenance_project_urls(commit):
    """Return standard Core Metadata URLs carrying the frozen build identity."""
    commit = validate_source_commit(commit)
    return {
        "aHPy source commit": (
            "https://github.com/mburakmmm/aHPy/commit/%s" % commit
        ),
        "Cython base commit": (
            "https://github.com/cython/cython/commit/%s" %
            CYTHON_BASE_COMMIT
        ),
        "HPy %s compatibility" % AHPY_HPY_SUPPORTED_VERSION: (
            "https://github.com/mburakmmm/aHPy/blob/%s/"
            "tests/ahpy/release-contract.toml" % commit
        ),
    }

__version__ = AHPY_VERSION
