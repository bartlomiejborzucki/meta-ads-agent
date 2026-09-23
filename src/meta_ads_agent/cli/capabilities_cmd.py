"""``meta-ads-agent capabilities`` - what routes where.

Prints the capability registry: which layer owns each capability, which gaps
the fallback covers, and what is not supported at all. ``--validate`` checks
the registry parses and flags entries nobody has reviewed recently.

This reports the project's *known* mapping. It cannot introspect a live MCP
session - only a running agent can do that. The output says so, because
claiming a capability exists on the strength of a local file is exactly the
mistake this command should not make.
"""

from __future__ import annotations

from meta_ads_agent.capabilities import Provider, Registry, load_registry
from meta_ads_agent.cli.output import echo, emit_json, fail, heading, warn
from meta_ads_agent.errors import MetaAdsAgentError

_STALE_DAYS = 90


def run_capabilities(
    *,
    as_json: bool = False,
    validate: bool = False,
    area: str | None = None,
    gaps_only: bool = False,
    capability: str | None = None,
    compare_with: str | None = None,
) -> int:
    try:
        registry = load_registry()
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1

    if compare_with:
        return _compare(registry, compare_with, as_json=as_json)

    if validate:
        return _validate(registry)

    if capability:
        return _show_one(registry, capability, as_json=as_json)

    if as_json:
        emit_json(_as_payload(registry, area=area, gaps_only=gaps_only))
        return 0

    _render(registry, area=area, gaps_only=gaps_only)
    return 0


def _as_payload(registry: Registry, *, area: str | None, gaps_only: bool) -> dict[str, object]:
    selected = [
        cap
        for cap in registry.capabilities.values()
        if (not area or cap.area == area) and (not gaps_only or cap.is_gap)
    ]
    return {
        "registry_version": registry.version,
        "reviewed": str(registry.reviewed),
        "mcp_endpoint": registry.mcp_endpoint,
        "graph_api_version": registry.graph_api_version,
        "source": "local capability registry (config/capabilities.yaml)",
        "caveat": (
            "This is the project's recorded mapping, not live introspection of "
            "a connected MCP session. Verify with the connected server before "
            "relying on a single tool name."
        ),
        "capabilities": [
            {
                "name": cap.name,
                "area": cap.area,
                "preferred_provider": cap.preferred_provider.value,
                "fallback_provider": cap.fallback_provider.value,
                "risk_level": cap.risk_level.value,
                "requires_approval": cap.requires_approval,
                "mcp_tools": list(cap.mcp_tools),
                "cli": cap.cli,
                "last_reviewed": str(cap.last_reviewed) if cap.last_reviewed else None,
                "is_gap": cap.is_gap,
                "notes": cap.notes.strip() or None,
            }
            for cap in sorted(selected, key=lambda c: (c.area, c.name))
        ],
    }


def _render(registry: Registry, *, area: str | None, gaps_only: bool) -> None:
    heading("Capability routing")
    echo(f"  registry version {registry.version}, reviewed {registry.reviewed}")
    echo(f"  official MCP     {registry.mcp_endpoint}")
    echo(f"  graph API        {registry.graph_api_version}")
    echo("")
    echo("  Rule: if the official MCP covers it, use the MCP. The fallback")
    echo("  exists only for gaps, and is meant to shrink over time.")

    if gaps_only:
        _render_gaps(registry)
        return

    for area_name, caps in registry.by_area().items():
        if area and area_name != area:
            continue
        heading(area_name)
        for cap in caps:
            marker = {
                Provider.OFFICIAL_MCP: "MCP     ",
                Provider.API_FALLBACK: "FALLBACK",
                Provider.NONE: "NONE    ",
            }[cap.preferred_provider]
            approval = " approval" if cap.requires_approval else ""
            echo(f"  {marker}  {cap.name:<34} {cap.risk_level.value}{approval}")

    _render_gaps(registry)

    unsupported = registry.unsupported()
    if unsupported:
        heading("Not supported in this release")
        for cap in unsupported:
            echo(f"  {cap.name}")
            if cap.notes.strip():
                echo(f"    {cap.notes.strip().splitlines()[0]}", "dim")

    heading("Caveat")
    echo("  This is the recorded mapping, not live introspection. Meta can")
    echo("  rename or add tools. Ask your agent to list the connected server's")
    echo("  tools, and see docs/reference/capability-refresh.md.")


def _render_gaps(registry: Registry) -> None:
    gaps = registry.gaps()
    heading(f"Fallback gaps ({len(gaps)})")
    if not gaps:
        echo("  None. Everything routes through the official MCP.")
        return
    echo("  These need the optional [api] extra and a Meta access token.")
    echo("")
    for cap in gaps:
        echo(f"  {cap.name}", "bold")
        if cap.cli:
            echo(f"    command: {cap.cli}")
        if cap.notes.strip():
            for line in cap.notes.strip().splitlines():
                echo(f"    {line.strip()}", "dim")


def _show_one(registry: Registry, name: str, *, as_json: bool) -> int:
    try:
        cap = registry.get(name)
        route = registry.route(name)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1

    if as_json:
        emit_json(
            {
                "name": cap.name,
                "area": cap.area,
                "provider": route.provider.value,
                "reason": route.reason,
                "risk_level": route.risk_level.value,
                "requires_approval": route.requires_approval,
                "mcp_tools": list(route.mcp_tools),
                "cli": route.cli,
                "last_reviewed": str(cap.last_reviewed) if cap.last_reviewed else None,
                "notes": cap.notes.strip() or None,
            }
        )
        return 0

    heading(cap.name)
    echo(f"  area              {cap.area}")
    echo(f"  provider          {route.provider.value}")
    echo(f"  reason            {route.reason}")
    echo(f"  risk level        {route.risk_level.value}")
    echo(f"  needs approval    {'yes' if route.requires_approval else 'no'}")
    if route.mcp_tools:
        echo(f"  MCP tool hints    {', '.join(route.mcp_tools)}")
    if route.cli:
        echo(f"  command           {route.cli}")
    echo(f"  last reviewed     {cap.last_reviewed or 'never'}")
    if cap.notes.strip():
        echo("")
        for line in cap.notes.strip().splitlines():
            echo(f"  {line.strip()}")
    return 0


def _validate(registry: Registry) -> int:
    heading("Validating capability registry")
    echo(f"  parsed {len(registry.capabilities)} capabilities")
    echo(f"  {len(registry.gaps())} fallback gap(s), {len(registry.unsupported())} unsupported")

    problems = 0
    for cap in registry.capabilities.values():
        if cap.preferred_provider is Provider.API_FALLBACK and not cap.cli:
            fail(f"{cap.name}: routed to the fallback but declares no cli command")
            problems += 1
        if cap.preferred_provider is Provider.OFFICIAL_MCP and not cap.mcp_tools:
            fail(f"{cap.name}: routed to the MCP but names no tool hints")
            problems += 1
        if cap.preferred_provider is Provider.NONE and not cap.notes.strip():
            fail(f"{cap.name}: unsupported but gives no explanation")
            problems += 1

    stale = registry.stale(older_than_days=_STALE_DAYS)
    if stale:
        warn(f"{len(stale)} entry/entries not reviewed in {_STALE_DAYS} days: {', '.join(stale)}")
        echo("  Refresh: docs/reference/capability-refresh.md")

    if problems:
        fail(f"{problems} problem(s) found")
        return 1
    echo("")
    echo("  registry ok")
    return 0


def _compare(registry: Registry, source: str, *, as_json: bool) -> int:
    """Hold a live session's tool list up to the map. Exit 1 when they differ."""
    import sys
    from pathlib import Path

    from meta_ads_agent.tool_inventory import compare, load_inventory

    try:
        text = sys.stdin.read() if source == "-" else Path(source).expanduser().read_text("utf-8")
        inventory = load_inventory()
        drift = compare(text, registry, inventory)
    except FileNotFoundError:
        fail(f"{source} not found")
        return 2
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    if as_json:
        emit_json(
            {
                "map_reviewed": str(inventory.reviewed) if inventory.reviewed else None,
                "live_tools": len(drift.live),
                "missing": drift.missing,
                "missing_unmapped": drift.missing_unmapped,
                "new": drift.new,
                "unverified_confirmed": drift.unverified_confirmed,
                "unverified_absent": drift.unverified_absent,
                "gap_candidates": drift.gap_candidates,
                "clean": drift.clean,
            }
        )
        return 0 if drift.clean else 1

    heading("Live tools against the capability map")
    echo(f"  session   {len(drift.live)} ads_* tool(s)")
    echo(f"  map       Meta's reference as read on {inventory.reviewed or 'an unknown date'}")
    if drift.missing:
        echo("")
        echo("  MISSING - the map routes work to these, and this session lacks them:", "red")
        for tool, caps in drift.missing.items():
            echo(f"    {tool:<42} used by {', '.join(caps)}")
    if drift.missing_unmapped:
        echo("")
        echo("  Also absent (documented, not routed to by the map):")
        for tool in drift.missing_unmapped:
            echo(f"    {tool}")
    if drift.new:
        echo("")
        echo("  NEW - in this session, not in Meta's reference when the map was written:")
        for tool in drift.new:
            echo(f"    {tool}")
    if drift.unverified_confirmed or drift.unverified_absent:
        echo("")
        echo("  Community-reported names")
        for tool in drift.unverified_confirmed:
            echo(f"    {tool:<42} present - confirmed by this session")
        for tool in drift.unverified_absent:
            echo(f"    {tool:<42} absent from this session")
    if drift.gap_candidates:
        echo("")
        echo("  Worth reading - may close a fallback gap (a name is a hint, not proof):", "yellow")
        for capability, tools in drift.gap_candidates.items():
            echo(f"    {capability:<32} {', '.join(tools)}")
    echo("")
    if drift.clean:
        echo("  The session matches the map.")
    else:
        echo(
            "  Refresh the map by hand: docs/reference/capability-refresh.md. Nothing was changed."
        )
    return 0 if drift.clean else 1
