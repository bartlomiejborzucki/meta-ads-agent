"""``meta-ads-agent state`` - inspect campaign state and plan a resume.

Read-only and offline. It reports what this tool recorded and what a resume
would do next; it never contacts Meta, because the reconciliation read belongs
to the agent through the MCP.
"""

from __future__ import annotations

import contextlib

from meta_ads_agent.api.client import normalise_account_id
from meta_ads_agent.cli.output import echo, emit_json, fail, heading, warn
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.models.state import Stage, stage_order
from meta_ads_agent.state.store import StateStore, fingerprint_matches
from meta_ads_agent.workspace import Workspace

# What a resume should do at each stage boundary. Prose, because the actual
# work is the agent's - this only tells it where to pick up.
_RESUME_HINTS: dict[Stage, str] = {
    Stage.PLANNED: "validate the plan (meta-ads-agent validate-plan)",
    Stage.VALIDATED: "create the campaign, PAUSED",
    Stage.CAMPAIGN_CREATED: "create the remaining ad sets, PAUSED",
    Stage.AD_SETS_CREATED: "resolve and upload assets (deduplicated by fingerprint)",
    Stage.ASSETS_UPLOADED: "create the creatives",
    Stage.CREATIVES_CREATED: "create the ads, PAUSED",
    Stage.ADS_CREATED: "render placement previews",
    Stage.PREVIEWED: "QA the previews against the plan",
    Stage.QA_PASSED: "report what was built and ask whether to activate",
    Stage.AWAITING_APPROVAL: "nothing - waiting for explicit activation approval",
    Stage.ACTIVATED: "nothing - the pipeline is complete",
}


def run_state(
    slug: str | None,
    *,
    as_json: bool = False,
    list_all: bool = False,
    account: str | None = None,
) -> int:
    try:
        workspace = Workspace.locate()
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1

    store = StateStore(workspace)

    if list_all or not slug:
        return _list(workspace, store, as_json=as_json, account=account)

    try:
        state = store.load_state(slug)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1

    plan = None
    plan_drift = False
    if store.plan_exists(slug):
        try:
            plan = store.load_plan(slug)
            plan_drift = bool(
                state.plan_fingerprint and not fingerprint_matches(state.plan_fingerprint, plan)
            )
        except MetaAdsAgentError as exc:
            warn(f"plan could not be read: {exc}")

    resume = state.resume_from()

    if as_json:
        emit_json(
            {
                "slug": state.slug,
                "ad_account_id": state.ad_account_id,
                "stage": state.stage.value,
                "stage_index": stage_order(state.stage),
                "activated": state.activated,
                "used_api_fallback": state.used_fallback,
                "plan_present": plan is not None,
                "plan_drift": plan_drift,
                "objects": [
                    {
                        "id": o.id,
                        "type": o.type.value,
                        "name": o.name,
                        "provider": o.provider.value,
                        "plan_ref": o.plan_ref,
                        "status_at_creation": o.status_at_creation,
                    }
                    for o in state.objects
                ],
                "failures": [
                    {
                        "stage": f.stage.value,
                        "message": f.message,
                        "retry_safe": f.retry_safe,
                        "meta_code": f.meta_code,
                    }
                    for f in state.failures
                ],
                "resume_from": resume.value if resume else None,
                "resume_action": _RESUME_HINTS.get(state.stage) if resume else None,
            }
        )
        return 1 if plan_drift else 0

    heading(f"Campaign state: {state.slug}")
    echo(f"  account    {state.ad_account_id}")
    echo(f"  stage      {state.stage.value} ({stage_order(state.stage) + 1}/11)")
    echo(f"  activated  {'yes' if state.activated else 'no'}")
    echo(f"  updated    {state.updated_at:%Y-%m-%d %H:%M:%S} UTC")
    if state.used_fallback:
        echo("  note       some objects were created through the API fallback")

    if state.objects:
        heading(f"Created objects ({len(state.objects)})")
        for obj in state.objects:
            provider = "MCP" if obj.provider.value == "official_mcp" else "FALLBACK"
            echo(
                f"  {obj.type.value:<9} {obj.id:<20} {provider:<9} "
                f"{obj.status_at_creation or '?':<8} {obj.name or ''}"
            )
    else:
        echo("")
        echo("  no objects created yet")

    if state.failures:
        heading(f"Failures ({len(state.failures)})")
        for failure in state.failures:
            retry = "retry-safe" if failure.retry_safe else "NOT retry-safe"
            echo(f"  {failure.stage.value} ({retry}): {failure.message}")
        echo("")
        echo("  A write marked NOT retry-safe may have partially applied. Query")
        echo("  Meta for the object before attempting it again.")

    heading("Resume")
    if plan_drift:
        echo(
            "  BLOCKED: the plan changed after these objects were created.",
            "red",
        )
        echo("  Continuing would apply a different plan to existing structure.")
        echo("  Restore the plan that produced them, or start a new slug.")
        return 1
    if not plan:
        echo("  no plan.yaml alongside this state, so a resume cannot be planned")
    elif resume is None:
        echo("  nothing to do - the pipeline is complete")
    else:
        echo(f"  next stage  {resume.value}")
        echo(f"  next action {_RESUME_HINTS.get(state.stage, 'continue the pipeline')}")
    echo("")
    echo("  Before mutating anything, re-read these objects from Meta. Local")
    echo("  state is a convenience; Meta is authoritative.")
    return 0


def _list(workspace: Workspace, store: StateStore, *, as_json: bool, account: str | None) -> int:
    wanted = normalise_account_id(account) if account else None
    slugs = workspace.list_campaigns()
    rows = []
    for slug in slugs:
        entry: dict[str, object] = {"slug": slug}
        if store.plan_exists(slug):
            # An unreadable plan is reported by `state <slug>`; here it only
            # means the account column is unknown.
            with contextlib.suppress(MetaAdsAgentError):
                entry["account"] = store.load_plan(slug).ad_account_id
        if store.state_exists(slug):
            try:
                state = store.load_state(slug)
                entry.update(
                    stage=state.stage.value,
                    objects=len(state.objects),
                    activated=state.activated,
                    account=state.ad_account_id,
                )
            except MetaAdsAgentError as exc:
                entry["error"] = str(exc)
        else:
            entry["stage"] = "no state (plan only)" if store.plan_exists(slug) else "empty"
        if wanted is None or entry.get("account") == wanted:
            rows.append(entry)

    if as_json:
        emit_json({"workspace": str(workspace.root), "account": wanted, "campaigns": rows})
        return 0

    heading(f"Campaigns in {workspace.root}")
    if not rows:
        echo("  none yet")
        return 0
    accounts = {row.get("account") for row in rows}
    for row in rows:
        where = f" {row.get('account', '?')!s:<20}" if len(accounts) > 1 else ""
        echo(
            f"  {row['slug']!s:<32}{where} {row.get('stage', '?')!s:<22} "
            f"{row.get('objects', 0)} object(s)"
        )
    echo("")
    echo("  Detail:  meta-ads-agent state <slug>")
    return 0
