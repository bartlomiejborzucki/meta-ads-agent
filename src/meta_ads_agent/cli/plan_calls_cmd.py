"""``meta-ads-agent plan-calls`` - a validated plan as Meta MCP calls.

Prints, in build order, the tool and arguments for every object the plan
needs: budgets in minor units, targeting and creative as JSON-encoded strings,
ids that do not exist yet as ``<id:PLAN_REF>``. Objects already recorded in
state are marked done, so a resumed build continues where it stopped.

The plan is validated first, with the same checks as ``validate-plan``; a plan
with errors produces no calls. It changes nothing and calls nothing.

Exit codes:
  0  the calls were compiled (some may still list what they need)
  1  the plan has validation errors, or changed after objects were created
  2  the plan or a named file could not be read
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meta_ads_agent.cli.output import echo, emit_json, fail, heading, warn
from meta_ads_agent.cli.validate_cmd import load_account, load_brand, read_plan
from meta_ads_agent.errors import ConfigError, MetaAdsAgentError
from meta_ads_agent.mcp_calls import SCHEMA_READ, Call, compile_calls
from meta_ads_agent.models.state import CampaignState, ObjectType
from meta_ads_agent.state.assets import AssetStore, probe_asset
from meta_ads_agent.state.store import StateStore, fingerprint_matches
from meta_ads_agent.validation import validate_plan
from meta_ads_agent.workspace import Workspace


def run_plan_calls(
    plan_path: str,
    *,
    account_path: str | None = None,
    brand_path: str | None = None,
    as_json: bool = False,
    skip_assets: bool = False,
) -> int:
    target = Path(plan_path).expanduser()
    doc = read_plan(target)
    if doc is None:
        return 2
    workspace = Workspace.locate(required=False)
    brand_problems: list[str] = []
    try:
        brand = load_brand(brand_path, workspace, problems=brand_problems)
        account = load_account(account_path, workspace, doc.ad_account_id)
        report = validate_plan(
            doc,
            account=account,
            brand=brand,
            asset_base=target.parent,
            check_assets=not skip_assets,
        )
    except ConfigError as exc:
        fail(str(exc))
        return 2
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2
    if brand_problems or not report.ok:
        fail(
            "the plan does not validate, so there are no calls to make. "
            f"Run `meta-ads-agent validate-plan {target}` and fix:"
        )
        for problem in brand_problems:
            echo(f"  brand.yaml: {problem}")
        for finding in report.errors:
            echo(f"  {finding}")
        return 1

    state: CampaignState | None = None
    store = StateStore(workspace)
    if workspace.exists and store.state_exists(doc.slug):
        try:
            state = store.load_state(doc.slug)
        except MetaAdsAgentError as exc:
            fail(str(exc))
            return 2
        if (
            state.objects
            and state.plan_fingerprint
            and not fingerprint_matches(state.plan_fingerprint, doc)
        ):
            fail(
                f"the plan changed after {len(state.objects)} object(s) were created on Meta. "
                "Restore the plan that produced them, or start a new slug. "
                f"See `meta-ads-agent state {doc.slug}`."
            )
            return 1

    def lookup(path: Path) -> tuple[str, str] | None:
        """What this file is already called on the account, from the asset manifest."""
        if not workspace.exists:
            return None
        try:
            record = AssetStore(workspace).lookup(probe_asset(path), doc.ad_account_id)
        except MetaAdsAgentError:
            return None
        if record is None:
            return None
        if record.kind is ObjectType.VIDEO and record.video_id:
            return "video_id", record.video_id
        return ("image_hash", record.image_hash) if record.image_hash else None

    calls = compile_calls(
        doc,
        account=account,
        brand=brand,
        state=state,
        asset_base=target.parent,
        asset_lookup=lookup,
    )

    if as_json:
        emit_json(
            {
                "plan": str(target),
                "slug": doc.slug,
                "ad_account_id": doc.ad_account_id,
                "schema_read": SCHEMA_READ,
                "complete": calls.complete,
                "pending": len(calls.pending),
                "calls": [_as_dict(call, doc.slug) for call in calls.calls],
                "notes": calls.notes,
            }
        )
        return 0

    heading(f"Calls for {doc.slug}")
    echo(f"  account    {doc.ad_account_id}")
    echo(f"  arguments  as Meta's tool schemas listed them on {SCHEMA_READ} - if a call")
    echo("             is rejected, the error is right and this is out of date")
    echo("")
    for call in calls.calls:
        if call.done:
            echo(f"  {call.step}. {call.tool}  [{call.plan_ref}]  done: {call.done}", "dim")
            continue
        echo(f"  {call.step}. {call.tool}  [{call.plan_ref}]")
        for name, value in call.args.items():
            echo(f"       {name}: {value}")
        for need in call.needs:
            echo(f"       NEEDS  {need}", "yellow")
        for note in call.notes:
            echo(f"       note   {note}", "dim")
        echo(f"       then   {_record_command(call, doc.slug)}", "dim")
    echo("")
    for note in calls.notes:
        warn(note)
    if not calls.pending:
        echo("  nothing left to create: every object in the plan is recorded.")
    elif calls.complete:
        echo(f"  {len(calls.pending)} call(s) to make, in this order. Everything is created")
        echo("  PAUSED (or as a draft); record each id before the next call.")
    else:
        echo("  Some calls list what they NEED first. Settle those before building.")
    return 0


def _record_command(call: Call, slug: str) -> str:
    if call.file is not None:
        # An upload: remembered against the file too, so it is never uploaded twice.
        flag = "--video-id" if call.record_type == "video" else "--image-hash"
        return (
            f"meta-ads-agent record asset {slug} --file '{call.file}' {flag} <ID> "
            f"--plan-ref '{call.plan_ref}'"
        )
    return (
        f"meta-ads-agent record object {slug} --type {call.record_type} "
        f"--plan-ref '{call.plan_ref}' --id <ID>"
    )


def _as_dict(call: Call, slug: str) -> dict[str, Any]:
    return {
        "step": call.step,
        "tool": call.tool,
        "plan_ref": call.plan_ref,
        "status": "done" if call.done else "pending",
        "id": call.done,
        "args": call.args,
        "refs": call.refs,
        "needs": call.needs,
        "notes": call.notes,
        "record": _record_command(call, slug),
    }
