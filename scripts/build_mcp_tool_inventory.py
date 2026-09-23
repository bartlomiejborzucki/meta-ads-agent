#!/usr/bin/env python3
"""Regenerate config/mcp-tools.yaml from docs/research/current-meta-capabilities.md.

The research document is where the sources and dates live; the YAML is the
machine-readable copy the CLI ships. ``--check`` fails when they disagree, so
an edit to one without the other is caught in CI.

Tool names are read from the inventory section (tables and prose alike), with
the document's shorthand expanded: `ads_pixel_event_read` / `_create` means
ads_pixel_event_read and ads_pixel_event_create. The community-reported names
come from the table in their own section.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "research" / "current-meta-capabilities.md"
OUT = REPO / "config" / "mcp-tools.yaml"
REGISTRY = REPO / "config" / "capabilities.yaml"

HEADER = """\
# ---------------------------------------------------------------------------
# Meta Ads MCP tool inventory
# ---------------------------------------------------------------------------
# Every tool name Meta's published Ads MCP reference lists, and separately the
# names a community source reports that the reference does not. GENERATED from
# docs/research/current-meta-capabilities.md by
# scripts/build_mcp_tool_inventory.py - edit the document, then regenerate.
#
# `meta-ads-agent capabilities --compare <tool list>` reads this to say what a
# live session has that the map does not, and what the map expects that the
# session lacks. Names are hints, not contracts - see capabilities.yaml.
# ---------------------------------------------------------------------------

"""


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def documented(text: str) -> list[str]:
    inventory = _section(text, "## Tool inventory (official MCP)", "## Classification")
    names: set[str] = set()
    for line in inventory.splitlines():
        cell = line.split("|")[1] if line.startswith("|") else line
        full = re.findall(r"`(ads_[a-z0-9_]+)`", cell)
        names.update(full)
        shorthand = re.findall(r"`(_[a-z0-9_]+)`", cell)
        if full and shorthand:
            stem = full[0].rsplit("_", 1)[0]
            names.update(stem + suffix for suffix in shorthand)
    return sorted(names)


def unverified(text: str) -> list[str]:
    section = _section(text, "## Community-reported tools", "## Things this document")
    return sorted(set(re.findall(r"^\| `(ads_[a-z0-9_]+)` \|", section, re.MULTILINE)))


def render() -> str:
    text = DOC.read_text(encoding="utf-8")
    reviewed = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["reviewed"]
    body = {"reviewed": reviewed, "documented": documented(text), "unverified": unverified(text)}
    return HEADER + yaml.safe_dump(body, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != rendered:
            print(f"{OUT.relative_to(REPO)} is out of date: run {Path(__file__).name}")
            return 1
        print(f"{OUT.relative_to(REPO)} matches the research document")
        return 0
    OUT.write_text(rendered, encoding="utf-8")
    count = len(yaml.safe_load(rendered)["documented"])
    print(f"wrote {OUT.relative_to(REPO)}: {count} documented tool(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
