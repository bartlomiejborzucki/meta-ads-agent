"""Finding the payload and the manifest, in a wheel or in a checkout.

The skills ship inside the wheel as well as in the repository. That is what
makes a single install command possible: ``uv tool install git+...`` puts the
CLI on the machine, and the CLI already has the skills it is about to copy -
no second clone, no second download, and no chance of the CLI and the payload
being different versions of the project.
"""

from __future__ import annotations

from pathlib import Path

from meta_ads_agent.errors import ConfigError
from meta_ads_agent.install.manifest import ReleaseManifest, load_manifest

MANIFEST_FILENAME = "release-manifest.json"


def _package_data() -> Path:
    return Path(__file__).resolve().parents[1] / "_data"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def payload_source() -> Path:
    """The directory holding ``meta-ads-*`` skill folders."""
    packaged = _package_data() / "skills"
    if packaged.is_dir():
        return packaged
    checkout = _repo_root() / "skills"
    if checkout.is_dir():
        return checkout
    raise ConfigError(
        f"could not find the skill payload. Looked in {packaged} and {checkout}. "
        "Reinstall the package."
    )


def manifest_path() -> Path:
    packaged = _package_data() / MANIFEST_FILENAME
    if packaged.is_file():
        return packaged
    checkout = _repo_root() / MANIFEST_FILENAME
    if checkout.is_file():
        return checkout
    raise ConfigError(
        f"could not find {MANIFEST_FILENAME}. Looked in {packaged} and {checkout}. "
        "Without it there is no way to tell a complete installation from a "
        "partial one, so the installer refuses to guess."
    )


def release_manifest() -> ReleaseManifest:
    return load_manifest(manifest_path())
