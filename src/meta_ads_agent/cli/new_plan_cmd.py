"""``meta-ads-agent new-plan`` - a plan drafted from the workspace.

Fills a campaign plan from the offer brief, ``brand.yaml`` and the cached
account, so the same ids and URLs are not typed again for every campaign. It
invents nothing: a value that is nowhere is listed as missing, with where to
put it. Prints the plan; writes only with ``--write``.

Exit codes:
  0  the plan was drafted (and written, with --write)
  1  a plan already exists at that slug
  2  something needed is missing, or an input could not be read
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.cli.output import echo, emit_json, fail, heading, warn
from meta_ads_agent.cli.render_cmd import account_timezone
from meta_ads_agent.cli.validate_cmd import load_account, load_brand
from meta_ads_agent.errors import ConfigError, MetaAdsAgentError, ValidationError
from meta_ads_agent.models._common import dump_yaml_ready
from meta_ads_agent.models.brand import BrandConfig, Offer
from meta_ads_agent.scaffold import Asset, load_variants, relative_asset, scaffold_plan
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.workspace import Workspace

_HEADER = (
    "# Campaign plan - the source of truth for INTENT.\n"
    "# Drafted by 'meta-ads-agent new-plan' from the offer, brand.yaml and the cached\n"
    "# account. Review it - audience, optimisation goal and placements are yours to\n"
    "# decide - then validate-plan before anything is built.\n"
    "# Budget amounts are display amounts in the stated currency."
)


def run_new_plan(
    *,
    slug: str,
    budget: Decimal,
    offer_slug: str | None = None,
    objective: str | None = None,
    budget_type: str = "daily",
    budget_level: str = "campaign",
    currency: str | None = None,
    countries: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    account_id: str | None = None,
    page_id: str | None = None,
    instagram_account_id: str | None = None,
    url: str | None = None,
    optimization_goal: str | None = None,
    assets: list[str] | None = None,
    image_hashes: list[str] | None = None,
    video_ids: list[str] | None = None,
    copy_path: str | None = None,
    split: str = "auto",
    name: str | None = None,
    end: _dt.date | None = None,
    brand_path: str | None = None,
    write: bool = False,
    as_json: bool = False,
) -> int:
    workspace = Workspace.locate(required=False)
    if write and not workspace.exists:
        fail("no workspace here to write the plan into. Run `meta-ads-agent init` first.")
        return 2
    target = workspace.plan_file(slug)
    if write and target.exists():
        fail(f"{target} already exists; choose another --slug")
        return 1

    try:
        brand = load_brand(brand_path, workspace)
        offer = _offer(workspace, offer_slug)
        account = _account(workspace, account_id, brand)
        raw_copy, copy_source = _copy(workspace, slug, copy_path)
        # No copy at all is one more missing input; scaffold_plan lists it
        # with the others rather than stopping here at the first.
        variants = load_variants(raw_copy, copy_source) if raw_copy is not None else []
        media = [
            *(Asset(local_path=relative_asset(path, target.parent)) for path in assets or []),
            *(Asset(image_hash=h) for h in image_hashes or []),
            *(Asset(video_id=v) for v in video_ids or []),
        ]
        zone = account_timezone(workspace, account.id) if account else None
        result = scaffold_plan(
            slug=slug,
            budget=budget,
            assets=media,
            variants=variants,
            brand=brand,
            offer=offer,
            offer_slug=offer_slug,
            account=account,
            objective=objective,
            budget_type=budget_type,
            budget_level=budget_level,
            currency=currency,
            countries=[c.strip() for c in countries.split(",") if c.strip()] if countries else None,
            age_min=age_min,
            age_max=age_max,
            ad_account_id=account_id,
            page_id=page_id,
            instagram_account_id=instagram_account_id,
            destination_url=url,
            optimization_goal=optimization_goal,
            split=split,
            campaign_name=name,
            # The end of that day, in the account's timezone when it is known.
            end=_dt.datetime.combine(end, _dt.time(23, 59), tzinfo=zone or _dt.UTC)
            if end
            else None,
            tz=zone,
        )
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    doc = result.document
    data = dump_yaml_ready(doc)
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        workspace.write_yaml(target, data, header=_HEADER)

    ads = [ad for ad_set in doc.campaign.ad_sets for ad in ad_set.ads]
    if as_json:
        emit_json(
            {
                "slug": doc.slug,
                "campaign": doc.campaign.name,
                "ad_sets": len(doc.campaign.ad_sets),
                "ads": len(ads),
                "written": write,
                "plan": str(target) if write else None,
                "sources": result.sources,
                "notes": result.notes,
            }
        )
        return 0

    heading(f"Drafted {doc.slug}")
    echo(f"  campaign   {doc.campaign.name}")
    echo(f"  ads        {len(ads)}, all PAUSED")
    echo("")
    echo("  Where each value came from:")
    for name, source in result.sources.items():
        echo(f"    {name:<32} {source}")
    for note in result.notes:
        warn(note)
    echo("")
    if not write:
        echo(yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip())
        echo("")
        echo("  nothing written. Re-run with --write to save it in the workspace.")
        return 0
    echo(f"  written to {target}")
    echo(f"  Next: meta-ads-agent validate-plan {target}")
    return 0


def _offer(workspace: Workspace, slug: str | None) -> Offer | None:
    if not slug:
        return None
    path = workspace.offers_dir / f"{slug}.yaml"
    if not path.is_file():
        known = sorted(p.stem for p in workspace.offers_dir.glob("*.yaml"))
        raise ConfigError(
            f"no offer {slug!r} at {path}."
            + (f" Offers here: {', '.join(known)}." if known else "")
        )
    try:
        return Offer.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except (PydanticValidationError, yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        raise ConfigError(f"offer {path} is not valid: {exc}") from exc


def _account(
    workspace: Workspace, account_id: str | None, brand: BrandConfig | None
) -> AccountContext | None:
    """Cached facts for the account the plan is for, when it can be told which."""
    wanted = account_id or (brand.account.ad_account_id if brand else None)
    if wanted and not wanted.startswith("act_"):
        wanted = f"act_{wanted}"
    if not wanted:
        cached = workspace.cached_accounts() if workspace.exists else []
        if len(cached) != 1:
            return None  # none, or several: which one is the caller's to say
        wanted = cached[0]
    return load_account(None, workspace, wanted)


def _copy(workspace: Workspace, slug: str, explicit: str | None) -> tuple[object, str]:
    path = Path(explicit).expanduser() if explicit else workspace.copy_file(slug)
    if not path.is_file():
        if explicit:
            raise ConfigError(f"copy file {path} does not exist")
        return None, f"campaigns/{slug}/copy.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), str(path)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        raise ValidationError(f"{path} could not be read as YAML: {exc}") from exc
