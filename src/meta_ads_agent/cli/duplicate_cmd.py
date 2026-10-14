"""``meta-ads-agent duplicate-plan`` - a campaign read from Meta, as a new plan.

The agent reads the source campaign, its ad sets, ads and creatives through
the MCP and saves them as JSON; this turns that into a new ``plan.yaml``,
everything PAUSED, nothing about the source touched. The new plan then goes
through render-plan, validate-plan and a normal build.

Exit codes:
  0  the plan was built (and written, with --write)
  1  a plan already exists at that slug
  2  the source could not be read or mapped
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from meta_ads_agent.cli.output import echo, emit_json, fail, heading, warn
from meta_ads_agent.duplicate import duplicate_plan
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.models._common import dump_yaml_ready
from meta_ads_agent.workspace import Workspace

_HEADER = (
    "# Campaign plan - the source of truth for INTENT.\n"
    "# Duplicated by 'meta-ads-agent duplicate-plan' from a campaign read from Meta.\n"
    "# Review it, then render-plan and validate-plan before anything is built.\n"
    "# Budget amounts are display amounts in the stated currency."
)


def run_duplicate_plan(
    source_path: str,
    *,
    slug: str,
    name: str | None,
    currency: str | None,
    account: str | None,
    write: bool,
    as_json: bool,
) -> int:
    path = Path(source_path).expanduser()
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"cannot read {path}: {exc}")
        return 2
    try:
        result = duplicate_plan(source, slug=slug, name=name, currency=currency, account=account)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    doc = result.document
    data = dump_yaml_ready(doc)
    target: Path | None = None
    if write:
        workspace = Workspace.locate()
        target = workspace.plan_file(doc.slug)
        if target.exists():
            fail(f"{target} already exists; choose another --slug")
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        workspace.write_yaml(target, data, header=_HEADER)

    ad_sets = doc.campaign.ad_sets
    if as_json:
        emit_json(
            {
                "slug": doc.slug,
                "campaign": doc.campaign.name,
                "ad_sets": len(ad_sets),
                "ads": sum(len(s.ads) for s in ad_sets),
                "written": target is not None,
                "plan": str(target) if target else None,
                "notes": result.notes,
            }
        )
        return 0

    heading(f"Duplicated as {doc.slug}")
    echo(f"  campaign   {doc.campaign.name}")
    echo(f"  ad sets    {len(ad_sets)}, ads {sum(len(s.ads) for s in ad_sets)}, all PAUSED")
    for note in result.notes:
        warn(note)
    echo("")
    if target is None:
        echo(yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip())
        echo("")
        echo("  nothing written. Re-run with --write to save it in the workspace.")
        return 0
    echo(f"  written to {target}")
    echo(f"  Next: meta-ads-agent render-plan {target} --write")
    echo(f"        meta-ads-agent validate-plan {target}")
    return 0
