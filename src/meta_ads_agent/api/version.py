"""The Graph API version, in exactly one place.

Scattering a version string across call sites is how a project ends up pinned
to three different API versions at once. Every fallback request reads it from
here.

Upgrade policy is in docs/reference/api-versioning.md. In short: the default
tracks the version this release was tested against, ``META_GRAPH_API_VERSION``
overrides it, and the SDK's own major must match - ``facebook-business`` majors
track Graph versions.
"""

from __future__ import annotations

import os
import re

# Graph/Marketing API version current when this release was tested (2026-09-16).
# facebook-business 26.0.1 is the matching SDK major.
DEFAULT_GRAPH_API_VERSION = "v26.0"

# Oldest version Meta still supported at that date. Below this, calls fail.
OLDEST_SUPPORTED_VERSION = "v24.0"

_VERSION_RE = re.compile(r"^v\d+\.\d+$")

ENV_VAR = "META_GRAPH_API_VERSION"


def graph_api_version(override: str | None = None) -> str:
    """Resolve the version to use: argument, then environment, then default."""
    value = (override or os.environ.get(ENV_VAR) or DEFAULT_GRAPH_API_VERSION).strip()
    if not _VERSION_RE.match(value):
        raise ValueError(
            f"{ENV_VAR}={value!r} is not a Graph API version. Expected a form "
            f"like {DEFAULT_GRAPH_API_VERSION!r}."
        )
    return value


def version_tuple(version: str) -> tuple[int, int]:
    major, minor = version.lstrip("v").split(".", 1)
    return int(major), int(minor)


def is_probably_unsupported(version: str) -> bool:
    """True when *version* is older than the oldest version known supported.

    Advisory: Meta's support window moves on its own schedule, so this can only
    say "this looks too old", never "this is fine".
    """
    return version_tuple(version) < version_tuple(OLDEST_SUPPORTED_VERSION)
