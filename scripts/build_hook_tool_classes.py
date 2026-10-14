#!/usr/bin/env python3
"""Generate hooks/tool-classes.json, the approval class of every Meta MCP tool.

The plugin's PreToolUse hook (hooks/approval_gate.py) classes each Meta MCP
call by name. It runs with the standard library only, so it cannot read
capabilities.yaml; this script turns the registry into JSON it can read.
``--check`` fails when the committed file is out of date (ADR-011).

A tool's class is the highest class among the capabilities that route to it
through the official MCP. A capability served by the fallback lists MCP tools
that are related reads (``ads_get_ad_images`` beside ``local_image_upload``),
not its route, so those lists are ignored. Every tool in the inventory must
end with a class: the few no capability routes are classed below, by hand,
with the reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from meta_ads_agent.capabilities import (  # noqa: E402
    APPROVAL_REQUIRED,
    Provider,
    RiskLevel,
    load_registry,
    risk_rank,
)
from meta_ads_agent.tool_inventory import load_inventory  # noqa: E402

OUTPUT = REPO / "hooks" / "tool-classes.json"

# Inventory tools no official-MCP capability routes to, classed by what they
# do rather than left to the hook's guess.
UNROUTED: dict[str, tuple[RiskLevel, str]] = {
    "ads_boost_ig_post": (
        RiskLevel.ACTIVATE,
        "a boost starts delivery; Meta does not document a paused boost (ADR-010)",
    ),
    "ads_get_ad_images": (RiskLevel.READ, "lists images already uploaded"),
    "ads_get_ad_videos": (RiskLevel.READ, "lists videos already uploaded"),
    "ads_creative_upload_image": (
        RiskLevel.CREATE_PAUSED,
        "unverified; uploads an image from a URL, which spends nothing",
    ),
    "ads_entity_get_report": (RiskLevel.READ, "unverified; fetches a report"),
    "ads_entity_schedule_report": (
        RiskLevel.CREATE_PAUSED,
        "unverified; schedules a report, which spends nothing",
    ),
}


def build() -> str:
    registry = load_registry(REPO / "config" / "capabilities.yaml")
    inventory = load_inventory(REPO / "config" / "mcp-tools.yaml")

    classes: dict[str, RiskLevel] = {}
    for cap in registry.capabilities.values():
        if cap.preferred_provider is not Provider.OFFICIAL_MCP:
            continue
        for tool in cap.mcp_tools:
            current = classes.get(tool)
            if current is None or risk_rank(cap.risk_level) > risk_rank(current):
                classes[tool] = cap.risk_level

    for tool, (level, _reason) in UNROUTED.items():
        if tool in classes:
            raise SystemExit(
                f"error: {tool} is now routed by capabilities.yaml as {classes[tool]}; "
                "remove it from UNROUTED in this script"
            )
        classes[tool] = level

    missing = sorted((inventory.documented | inventory.unverified) - classes.keys())
    if missing:
        raise SystemExit(
            "error: no approval class for these inventoried tools - route them in "
            f"capabilities.yaml or class them in UNROUTED here: {missing}"
        )

    payload = {
        "_generated": (
            "GENERATED from config/capabilities.yaml by "
            "scripts/build_hook_tool_classes.py - edit those, then regenerate."
        ),
        "reviewed": str(registry.reviewed) if registry.reviewed else None,
        "approval_required": sorted(str(level) for level in APPROVAL_REQUIRED),
        "tools": {tool: str(classes[tool]) for tool in sorted(classes)},
    }
    return json.dumps(payload, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    args = parser.parse_args()

    text = build()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
    if args.check:
        if current != text:
            print(f"{OUTPUT.relative_to(REPO)} is out of date - run {Path(__file__).name}")
            return 1
        print(f"{OUTPUT.relative_to(REPO)} matches capabilities.yaml")
        return 0
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO)}: {len(json.loads(text)['tools'])} tool(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
