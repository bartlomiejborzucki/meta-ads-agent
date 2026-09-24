"""Compare a live session's Meta Ads MCP tools with what this project expects.

The capability map was read from Meta's published reference, never
introspected (the README's "Never run against Meta"). Anyone with a
connected session can close that gap by pasting the session's tool list -
the agent's own list of available tools, ``/mcp`` output, JSON, anything
containing the names. This module finds the ``ads_*`` names in that text
and reports four things:

* **missing** - tools the capability map routes work to, that the session
  does not have. The most urgent: a skill will reach for them.
* **new** - tools the session has that Meta's reference did not list when
  the map was written. Any of them may close a fallback gap.
* **unverified** - the community-reported names, and whether this session
  confirms or refutes each.
* **gap candidates** - new or confirmed tools whose names suggest one of
  the fallback gaps. A name is a hint to read the tool's description,
  not evidence that the gap is closed.

It changes nothing. Updating the map is the refresh procedure in
``docs/reference/capability-refresh.md``, done by a person.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from meta_ads_agent.capabilities import Registry
from meta_ads_agent.errors import ConfigError, ValidationError

# Host prefixes such as `mcp__meta-ads__ads_get_ad_accounts`.
_HOST_PREFIX = re.compile(r"mcp__[\w-]+?__")
_TOOL = re.compile(r"(?<![a-z0-9_])ads_[a-z0-9_]*[a-z0-9]")

# Words in a tool name that make it worth reading for each fallback gap. Each
# inner tuple is all-of; any one of them matching is enough.
_GAP_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "local_image_upload": (("upload", "image"), ("upload", "media")),
    "local_video_upload": (("upload", "video"), ("upload", "media")),
    "create_video_creative": (("video", "creative"),),
    "create_existing_post_creative": (("post", "creative"), ("boost", "post")),
    "create_multi_variant_creative": (("asset_feed",), ("variant",), ("dynamic_creative",)),
    "create_carousel_creative": (("carousel",), ("child_attachment",), ("multi_share",)),
    "delete_entity": (
        ("delete", "campaign"),
        ("delete", "ad_set"),
        ("delete", "adset"),
        ("delete", "entity"),
        ("delete_ad",),
    ),
}


@dataclass(frozen=True, slots=True)
class Inventory:
    reviewed: _dt.date | None
    documented: frozenset[str]
    unverified: frozenset[str]


def default_inventory_path() -> Path:
    packaged = Path(__file__).with_name("_data") / "mcp-tools.yaml"
    if packaged.is_file():
        return packaged
    repo = Path(__file__).resolve().parents[2] / "config" / "mcp-tools.yaml"
    if repo.is_file():
        return repo
    raise ConfigError(f"Could not locate mcp-tools.yaml at {packaged} or {repo}.")


def load_inventory(path: Path | None = None) -> Inventory:
    raw = yaml.safe_load((path or default_inventory_path()).read_text(encoding="utf-8")) or {}
    reviewed = raw.get("reviewed")
    return Inventory(
        reviewed=reviewed if isinstance(reviewed, _dt.date) else None,
        documented=frozenset(raw.get("documented") or ()),
        unverified=frozenset(raw.get("unverified") or ()),
    )


def tool_names(text: str) -> set[str]:
    """Every ``ads_*`` tool name in pasted text, whatever surrounds it."""
    return set(_TOOL.findall(_HOST_PREFIX.sub(" ", text)))


@dataclass(slots=True)
class Drift:
    live: set[str]
    missing: dict[str, list[str]] = field(default_factory=dict)  # tool -> capabilities
    missing_unmapped: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    unverified_confirmed: list[str] = field(default_factory=list)
    unverified_absent: list[str] = field(default_factory=list)
    gap_candidates: dict[str, list[str]] = field(default_factory=dict)  # capability -> tools

    @property
    def clean(self) -> bool:
        return not (self.missing or self.missing_unmapped or self.new or self.gap_candidates)


def compare(text: str, registry: Registry, inventory: Inventory) -> Drift:
    live = tool_names(text)
    if not live:
        raise ValidationError(
            "no ads_* tool names found in the input. Paste the session's tool list - "
            "names such as ads_get_ad_accounts - rather than a summary of it."
        )
    mapped: dict[str, list[str]] = {}
    for cap in registry.capabilities.values():
        for tool in cap.mcp_tools:
            mapped.setdefault(tool, []).append(cap.name)

    drift = Drift(live=live)
    drift.missing = {t: sorted(caps) for t, caps in sorted(mapped.items()) if t not in live}
    drift.missing_unmapped = sorted(inventory.documented - live - set(mapped))
    drift.new = sorted(live - inventory.documented - inventory.unverified)
    drift.unverified_confirmed = sorted(inventory.unverified & live)
    drift.unverified_absent = sorted(inventory.unverified - live)

    worth_reading = set(drift.new) | set(drift.unverified_confirmed)
    for capability, hints in _GAP_HINTS.items():
        gap = registry.capabilities.get(capability)
        if gap is None or not gap.is_gap:
            continue
        tools = sorted(
            t for t in worth_reading if any(all(w in t for w in group) for group in hints)
        )
        if tools:
            drift.gap_candidates[capability] = tools
    return drift
