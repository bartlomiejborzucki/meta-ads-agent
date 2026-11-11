"""``meta-ads-agent record`` - write what happened on Meta into the workspace.

State used to be a JSON file the agent wrote by hand. The store that was meant
to write it - one writer at a time, two sessions merged rather than
overwritten, a fingerprint tying the ids to the plan that produced them - was
only ever called by tests. These commands are the missing callers.

  record object      an id Meta returned, against the plan element it is for
  record stage       a stage with no object of its own: validated, previewed, ...
  record failure     a call that failed, and whether a retry is safe
  record activation  the campaign was published or activated
  record asset       a local file's identity on Meta, so it is uploaded once
  cache-account      account facts read from Meta, for the validator

None of them calls Meta. They record; the agent's MCP calls act.

Exit codes:
  0  recorded
  1  refused: the plan changed, another id is already recorded for that
     element, or two sessions recorded different objects
  2  bad input, or no workspace / plan / state to record into
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.cli.init_cmd import write_account_cache
from meta_ads_agent.cli.output import echo, emit_json, fail
from meta_ads_agent.errors import MetaAdsAgentError, ReconciliationError, WorkspaceError
from meta_ads_agent.models.plan import CampaignPlanDocument, CreativeMode
from meta_ads_agent.models.state import (
    CampaignState,
    CreatedObject,
    Failure,
    ObjectType,
    Provider,
    Stage,
    stage_order,
)
from meta_ads_agent.state.assets import AssetStore, probe_asset
from meta_ads_agent.state.store import StateStore
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.workspace import Workspace

# Meta's field names for facts the validator knows by another name.
_ACCOUNT_ALIASES = {
    "timezone": "timezone_name",
    "min_daily_budget_cents": "min_daily_budget",
}


def _reason(exc: Exception) -> str:
    """A model's own message, without pydantic's framing around it."""
    if isinstance(exc, PydanticValidationError):
        return "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
    return str(exc)


_Opened = tuple[StateStore, CampaignPlanDocument, CampaignState]


def _open(slug: str) -> _Opened | int:
    """The store, plan and state for *slug* - or the exit code to stop with.

    2 when there is no workspace, plan or readable state; 1 when the state is
    there but refuses this plan, which is a decision for a person.
    """
    try:
        store = StateStore(Workspace.locate())
        doc = store.load_plan(slug)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2
    try:
        return store, doc, store.load_or_create_state(doc)
    except ReconciliationError as exc:
        fail(str(exc))
        return 1
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2


def progress(doc: CampaignPlanDocument, state: CampaignState) -> Stage | None:
    """The furthest build stage the recorded objects complete, or None.

    Worked out from the plan, so the stage is never something the agent has to
    remember to set: record every id, and the stage follows.
    """
    recorded = {o.plan_ref for o in state.objects if o.plan_ref}
    if "campaign" not in recorded:
        return None
    ad_sets = doc.campaign.ad_sets
    if not all(f"ad_sets[{i}]" in recorded for i in range(len(ad_sets))):
        return Stage.CAMPAIGN_CREATED
    ads = [
        (f"ad_sets[{i}].ads[{j}]", ad) for i, s in enumerate(ad_sets) for j, ad in enumerate(s.ads)
    ]
    built = [(ref, ad) for ref, ad in ads if ad.creative.mode is not CreativeMode.EXISTING_POST]
    creatives_done = all(f"{ref}.creative" in recorded for ref, _ in built)
    # An upload is recorded under the first plan element that uses the file.
    # Creatives existing means their media did; otherwise look for any file
    # with no recorded upload.
    # Keyed the way plan-calls keys an upload: one per file, however the plan
    # spells its path, under the first element that uses it.
    local = {
        os.path.normpath(asset.local_path): f"{ref}.creative.{where}"
        for ref, ad in reversed(ads)
        for where, asset in reversed(ad.creative.asset_refs())
        if asset.local_path
    }
    uploads_done = creatives_done or all(ref in recorded for ref in local.values())
    if not uploads_done:
        return Stage.AD_SETS_CREATED
    if not creatives_done:
        return Stage.ASSETS_UPLOADED
    if not all(ref in recorded for ref, _ in ads):
        return Stage.CREATIVES_CREATED
    return Stage.ADS_CREATED


def _report(state: CampaignState, as_json: bool, **extra: Any) -> int:
    resume = state.resume_from()
    if as_json:
        emit_json(
            {
                "slug": state.slug,
                "stage": state.stage.value,
                "objects": len(state.objects),
                "resume_from": resume.value if resume else None,
                **extra,
            }
        )
    else:
        echo(f"  stage      {state.stage.value}, {len(state.objects)} object(s) recorded")
        echo(f"  next       {resume.value if resume else 'nothing - the build is finished'}")
    return 0


def run_record_object(
    slug: str,
    *,
    object_type: str,
    object_id: str,
    plan_ref: str,
    name: str | None = None,
    parent_id: str | None = None,
    status: str | None = None,
    provider: str = "official_mcp",
    as_json: bool = False,
) -> int:
    opened = _open(slug)
    if isinstance(opened, int):
        return opened
    store, doc, state = opened
    try:
        obj = CreatedObject(
            id=object_id,
            type=ObjectType(object_type),
            name=name,
            provider=Provider(provider),
            plan_ref=plan_ref,
            parent_id=parent_id,
            status_at_creation=status,
        )
    except (PydanticValidationError, ValueError) as exc:
        fail(_reason(exc))
        return 2
    try:
        recorded = store.record_object(state, obj)
        stage = progress(doc, state)
        if stage is not None and stage_order(stage) > stage_order(state.stage):
            store.advance(state, stage)
    except (ReconciliationError, ValueError) as exc:
        # ValueError: this plan element already has a different id. Both are
        # real objects on Meta until someone looks - not something to overwrite.
        fail(str(exc))
        return 1
    if not as_json:
        echo(f"  recorded   {recorded.type.value} {recorded.id}  [{plan_ref}]")
    return _report(state, as_json, recorded={"type": recorded.type.value, "id": recorded.id})


def run_record_stage(slug: str, *, stage: str, as_json: bool = False) -> int:
    opened = _open(slug)
    if isinstance(opened, int):
        return opened
    store, _, state = opened
    try:
        store.advance(state, Stage(stage))
    except ValueError as exc:
        fail(str(exc))
        return 1
    return _report(state, as_json)


def run_record_failure(
    slug: str,
    *,
    stage: str,
    message: str,
    code: int | None = None,
    subcode: int | None = None,
    retry_safe: bool = False,
    plan_ref: str | None = None,
    as_json: bool = False,
) -> int:
    opened = _open(slug)
    if isinstance(opened, int):
        return opened
    store, _, state = opened
    try:
        failure = Failure(
            stage=Stage(stage),
            message=message,
            meta_code=code,
            meta_subcode=subcode,
            retry_safe=retry_safe,
            plan_ref=plan_ref,
        )
    except (PydanticValidationError, ValueError) as exc:
        fail(_reason(exc))
        return 2
    store.record_failure(state, failure)
    if not as_json:
        echo(
            f"  failure    {stage}: {message}"
            + ("" if retry_safe else "  (NOT retry-safe: query Meta before trying again)")
        )
    return _report(state, as_json, failures=len(state.failures))


def run_record_activation(slug: str, *, as_json: bool = False) -> int:
    opened = _open(slug)
    if isinstance(opened, int):
        return opened
    store, _, state = opened
    state.activated = True
    state.activated_at = state.activated_at or _dt.datetime.now(_dt.UTC)
    try:
        store.advance(state, Stage.ACTIVATED)
    except ValueError as exc:
        fail(str(exc))
        return 1
    return _report(state, as_json, activated=True)


def run_record_asset(
    slug: str,
    *,
    file: str,
    image_hash: str | None = None,
    video_id: str | None = None,
    plan_ref: str | None = None,
    provider: str = "official_mcp",
    as_json: bool = False,
) -> int:
    """A local file's identity on Meta: into the asset manifest, and state if asked."""
    if bool(image_hash) == bool(video_id):
        fail("give exactly one of --image-hash or --video-id")
        return 2
    opened = _open(slug)
    if isinstance(opened, int):
        return opened
    store, doc, state = opened
    kind = ObjectType.VIDEO if video_id else ObjectType.IMAGE
    try:
        probe = probe_asset(Path(file).expanduser())
        if probe.object_type is not kind:
            fail(f"{file} is {probe.kind.value}, but a {kind.value} id was given for it")
            return 2
        record = AssetStore(store.workspace).remember(
            probe,
            doc.ad_account_id,
            image_hash=image_hash,
            video_id=video_id,
            provider=Provider(provider),
        )
    except (MetaAdsAgentError, ValueError) as exc:
        fail(str(exc))
        return 2
    remote = record.video_id if kind is ObjectType.VIDEO else record.image_hash
    if not as_json:
        echo(f"  remembered {probe.path.name} as {kind.value} {remote}")
        if remote != (video_id or image_hash):
            echo("             (it was already uploaded; the first id is kept)", "dim")
    if plan_ref and remote:
        return run_record_object(
            slug,
            object_type=kind.value,
            object_id=remote,
            plan_ref=plan_ref,
            name=probe.path.name,
            provider=provider,
            as_json=as_json,
        )
    return _report(state, as_json, asset={"kind": kind.value, "id": remote})


def run_cache_account(
    source: str,
    *,
    account: str | None = None,
    pages: str | None = None,
    instagram_accounts: str | None = None,
    datasets: str | None = None,
    as_json: bool = False,
) -> int:
    """Save account facts read from Meta where ``validate-plan`` looks for them."""
    try:
        workspace = Workspace.locate()
    except WorkspaceError as exc:
        fail(str(exc))
        return 2
    try:
        text = sys.stdin.read() if source == "-" else Path(source).expanduser().read_text("utf-8")
        raw = json.loads(text)
    except (OSError, ValueError) as exc:
        fail(f"cannot read account JSON from {source}: {exc}")
        return 2
    rows = raw.get("data", raw) if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows) or not rows:
        fail('expected one account object, a list of them, or {"data": [...]} as Meta returns')
        return 2

    def account_id(row: dict[str, Any]) -> str:
        value = str(row.get("id") or row.get("account_id") or "")
        return value if value.startswith("act_") or not value else f"act_{value}"

    wanted = account if not account or account.startswith("act_") else f"act_{account}"
    matches = [r for r in rows if not wanted or account_id(r) == wanted]
    if len(matches) != 1:
        ids = ", ".join(account_id(r) or "?" for r in rows)
        fail(f"{len(matches)} account(s) match. The input has: {ids}. Pass --account to pick one.")
        return 2
    row = dict(matches[0])
    for theirs, ours in _ACCOUNT_ALIASES.items():
        if theirs in row and ours not in row:
            row[ours] = row[theirs]
    for flag, key in (
        (pages, "available_page_ids"),
        (instagram_accounts, "available_instagram_account_ids"),
        (datasets, "available_dataset_ids"),
    ):
        if flag:
            row[key] = [v.strip() for v in flag.split(",") if v.strip()]
    try:
        context = AccountContext.from_meta(row)
    except PydanticValidationError as exc:
        fail(f"these are not account facts the validator can use: {exc}")
        return 2
    payload = context.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    payload["id"] = context.id

    # account.yaml when it is free or already this account's; otherwise a file
    # per account, so one account's facts never validate another's plan.
    single = workspace.account_file
    current = workspace.cached_accounts()
    if not single.is_file() or current in ([], [context.id]):
        target = single
    else:
        target = workspace.account_file_for(context.id)
        target.parent.mkdir(parents=True, exist_ok=True)
    write_account_cache(workspace, payload, path=target)

    kept = sorted(k for k in payload if k != "id")
    if as_json:
        emit_json({"account": context.id, "written": str(target), "fields": kept})
        return 0
    echo(f"  cached     {context.id} -> {target}")
    echo(f"  fields     {', '.join(kept) or 'the id only'}")
    if not context.currency:
        echo("  no currency in the input: budgets cannot be checked against the account", "yellow")
    return 0
