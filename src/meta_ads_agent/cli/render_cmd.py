"""``meta-ads-agent render-plan`` - brand naming and UTM templates, applied.

Shows every name and destination URL the templates change. With ``--write``
the rendered plan replaces ``plan.yaml``, which then validates and builds
like any other plan. Without it, nothing is written.

Exit codes:
  0  rendered (or nothing to render)
  1  a template could not be rendered - an unknown token, or one with no value
  2  the plan file itself could not be read or parsed
"""

from __future__ import annotations

from pathlib import Path

from meta_ads_agent.cli.output import echo, emit_json, fail, heading
from meta_ads_agent.cli.validate_cmd import load_brand, read_plan
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.naming import render_plan
from meta_ads_agent.workspace import Workspace

_HEADER = (
    "# Campaign plan - the source of truth for INTENT.\n"
    "# Rendered by 'meta-ads-agent render-plan': names and UTMs expanded from\n"
    "# brand.yaml. Rendering again changes nothing.\n"
    "# Budget amounts are display amounts in the stated currency."
)


def run_render_plan(
    plan_path: str, *, brand_path: str | None = None, write: bool = False, as_json: bool = False
) -> int:
    target = Path(plan_path).expanduser()
    doc = read_plan(target)
    if doc is None:
        return 2

    workspace = Workspace.locate(required=False)
    brand = load_brand(brand_path, workspace)
    try:
        result = render_plan(doc, brand)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1

    if write and result.changed:
        workspace.write_yaml(
            target, result.document.model_dump(mode="json", exclude_none=True), header=_HEADER
        )

    if as_json:
        emit_json(
            {
                "plan": str(target),
                "brand_config": brand is not None,
                "written": write and result.changed,
                "changes": [
                    {"path": path, "from": old, "to": new} for path, old, new in result.changes
                ],
            }
        )
        return 0

    heading(f"Rendering {target}")
    if brand is None:
        echo("  no brand.yaml found - only each ad set's own tracking.utm applies", "yellow")
    if not result.changed:
        echo("  nothing to render: no templated names, and every URL already carries its UTMs")
        return 0
    for path, old, new in result.changes:
        echo(f"  {path}")
        echo(f"    - {old}", "dim")
        echo(f"    + {new}")
    echo("")
    if write:
        echo(f"  written to {target}. Comments in the original file are not kept.")
        echo("  Validate it next: meta-ads-agent validate-plan " + str(target))
    else:
        echo("  nothing written. Re-run with --write to save the rendered plan.")
    return 0
