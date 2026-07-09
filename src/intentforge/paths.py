"""Path helpers for source checkouts and installed IntentForge packages."""

from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the installed intentforge package directory."""

    return Path(__file__).resolve().parent


def project_root() -> Path:
    """Return the repo root for a checkout, or cwd for an installed package.

    In a src-layout checkout, this file lives at src/intentforge/paths.py.
    In a wheel install, repo-only assets such as examples/ are not present, so
    output should default to the caller's working directory instead of
    site-packages.
    """

    package_dir = package_root()
    for candidate in (package_dir.parents[1], package_dir.parent, Path.cwd()):
        if (candidate / "pyproject.toml").exists() and (candidate / "src").is_dir():
            return candidate
    return Path.cwd()


def default_output_root() -> Path:
    """Return the default output directory."""

    return project_root() / "output"


def examples_dir() -> Path:
    """Return the development checkout examples directory."""

    return project_root() / "examples"
