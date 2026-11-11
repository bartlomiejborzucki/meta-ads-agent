"""A campaign plan, assembled from what the workspace already knows.

A plan used to be written by hand from an annotated template, with the same
ids and URLs typed again for every campaign: the Page, the Instagram account,
the dataset, the countries, the landing page, the EU transparency fields.
``brand.yaml`` has had fields for all of them since the first release
(``account:``, "defaults used to pre-fill a campaign plan"), and nothing read
them. This module does.

It fills a plan from four places, nearest first:

1. what the caller passed (the command line);
2. the offer brief - its landing page and call to action;
3. ``brand.yaml`` - the account defaults, EU transparency fields, declared
   special ad categories, Advantage preferences, naming and UTM conventions;
4. the cached account facts - the account id and currency, and the Page or
   Instagram account when the account has exactly one.

**It invents nothing.** A value that is in none of those places is reported
as missing, with where to put it; the plan is not built with a guess in its
place. What it does decide is mechanical: one ad set, one ad per asset or per
copy variant, names from the brand's templates. Targeting beyond countries
and ages, the optimisation goal and bid strategy stay the campaign skill's
judgement, added to the plan afterwards.

The result is an ordinary plan: review it, then ``validate-plan``.
"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.errors import ValidationError
from meta_ads_agent.models._common import looks_like_video
from meta_ads_agent.models.brand import BrandConfig, NamingConvention, Offer
from meta_ads_agent.models.plan import CampaignPlanDocument, CopyVariant
from meta_ads_agent.naming import render_plan
from meta_ads_agent.validation.account import AccountContext

SPLITS = ("auto", "per-asset", "per-variant", "matrix", "multi-variant")


@dataclass(frozen=True, slots=True)
class Asset:
    """One creative asset for the scaffold: a local file, or an id already on Meta."""

    local_path: str | None = None
    image_hash: str | None = None
    video_id: str | None = None

    @property
    def is_video(self) -> bool:
        return bool(self.video_id or (self.local_path and looks_like_video(self.local_path)))

    @property
    def label(self) -> str:
        """Short name for an ad that uses this asset."""
        name = (
            Path(self.local_path).stem
            if self.local_path
            else (self.image_hash or self.video_id or "asset")[:12]
        )
        # It goes into a name template: a brace in a file name is text, not a token.
        return name.replace("{", "(").replace("}", ")")

    def as_plan(self) -> dict[str, str]:
        for key in ("local_path", "image_hash", "video_id"):
            value = getattr(self, key)
            if value:
                return {key: value}
        raise ValidationError("an asset needs a file, an image hash or a video id")


@dataclass(slots=True)
class Scaffold:
    document: CampaignPlanDocument
    #: plan field -> where its value came from, for the review.
    sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _Resolver:
    """Picks each value from the nearest place that has it, and remembers where."""

    sources: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def pick(self, name: str, candidates: list[tuple[Any, str]], *, how: str | None = None) -> Any:
        """The first non-empty candidate. *how* makes the field required."""
        for value, source in candidates:
            if value not in (None, "", [], {}):
                self.sources[name] = source
                return value
        if how:
            self.missing.append(f"{name}: {how}")
        return None


def scaffold_plan(
    *,
    slug: str,
    budget: Decimal,
    assets: list[Asset],
    variants: list[CopyVariant],
    brand: BrandConfig | None = None,
    offer: Offer | None = None,
    offer_slug: str | None = None,
    account: AccountContext | None = None,
    objective: str | None = None,
    budget_type: str = "daily",
    budget_level: str = "campaign",
    currency: str | None = None,
    countries: list[str] | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    ad_account_id: str | None = None,
    page_id: str | None = None,
    instagram_account_id: str | None = None,
    destination_url: str | None = None,
    optimization_goal: str | None = None,
    split: str = "auto",
    campaign_name: str | None = None,
    end: _dt.datetime | None = None,
    created_at: _dt.datetime | None = None,
    tz: _dt.tzinfo | None = None,
) -> Scaffold:
    """Build a plan, or raise naming every value that is missing and where it goes."""
    if split not in SPLITS:
        raise ValidationError(f"split must be one of {', '.join(SPLITS)}, not {split!r}")
    defaults = brand.account if brand else None
    r = _Resolver()

    account_id = r.pick(
        "ad_account_id",
        [
            (ad_account_id, "--account"),
            (defaults.ad_account_id if defaults else None, "brand.yaml account.ad_account_id"),
            (account.id if account else None, "cached account"),
        ],
        how="pass --account act_<id>, or set account.ad_account_id in brand.yaml",
    )
    code = r.pick(
        "currency",
        [
            (currency.upper() if currency else None, "--currency"),
            (account.currency if account else None, "cached account"),
            (defaults.currency if defaults else None, "brand.yaml account.currency"),
        ],
        how="pass --currency, or read the account from Meta and run `cache-account`",
    )
    campaign_objective = r.pick(
        "campaign.objective",
        [
            (objective, "--objective"),
            (defaults.objective if defaults else None, "brand.yaml account.objective"),
        ],
        how="pass --objective (e.g. OUTCOME_SALES), or set account.objective in brand.yaml",
    )
    where = r.pick(
        "targeting.countries",
        [
            ([c.upper() for c in countries or []], "--countries"),
            (list(defaults.countries) if defaults else None, "brand.yaml account.countries"),
        ],
        how="pass --countries PL,DE, or set account.countries in brand.yaml",
    )
    page = r.pick(
        "creative.page_id",
        [
            (page_id, "--page-id"),
            (defaults.page_id if defaults else None, "brand.yaml account.page_id"),
            (_only(account.available_page_ids if account else []), "the account's only Page"),
        ],
        how="pass --page-id, or set account.page_id in brand.yaml",
    )
    instagram = r.pick(
        "creative.instagram_account_id",
        [
            (instagram_account_id, "--instagram-account-id"),
            (
                defaults.instagram_account_id if defaults else None,
                "brand.yaml account.instagram_account_id",
            ),
            (
                _only(account.available_instagram_account_ids if account else []),
                "the account's only Instagram account",
            ),
        ],
    )
    url = r.pick(
        "creative.destination_url",
        [
            (destination_url, "--url"),
            (offer.landing_page if offer else None, "offer landing_page"),
            (brand.default_destination_url if brand else None, "brand.yaml destination"),
        ],
        how="pass --url, name an offer with --offer, or set default_destination_url in brand.yaml",
    )
    cta = r.pick(
        "variants.cta_type",
        [
            (offer.cta if offer else None, "offer cta"),
            (defaults.cta_type if defaults else None, "brand.yaml account.cta_type"),
        ],
    )
    dataset = r.pick(
        "tracking.dataset_id",
        [(defaults.dataset_id if defaults else None, "brand.yaml account.dataset_id")],
    )
    event = r.pick(
        "tracking.conversion_event",
        [(defaults.conversion_event if defaults else None, "brand.yaml account.conversion_event")],
    )

    if not assets:
        r.missing.append(
            "assets: pass --assets FILE..., or --image-hash / --video-id for media already "
            "on the account"
        )
    if not variants:
        r.missing.append(
            "copy: pass --copy FILE (a YAML list of variants: angle, primary_text, headline, "
            f"...), or save it as campaigns/{slug}/copy.yaml"
        )
    if budget_type == "lifetime" and end is None:
        r.missing.append("schedule: a lifetime budget needs an end date - pass --end")
    if r.missing:
        raise ValidationError(
            "the plan cannot be drafted yet. Missing:\n  - " + "\n  - ".join(r.missing)
        )

    notes: list[str] = []
    advantage = dict(brand.advantage_defaults) if brand else {}
    if advantage:
        r.sources["creative.advantage"] = "brand.yaml advantage_defaults"
    # The default campaign template starts with {brand}; with no brand.yaml
    # there is no brand to name, so the name starts at the objective.
    naming = brand.naming if brand else NamingConvention(campaign="{objective} | {date}")
    ads = _ads(
        assets=assets,
        variants=[_with_cta(v, cta) for v in variants],
        split=_resolve_split(split, assets, variants, notes),
        ad_name=naming.ad,
        shared={
            "destination_url": url,
            "page_id": page,
            **({"instagram_account_id": instagram} if instagram else {}),
            **({"advantage": {"enhancements": advantage}} if advantage else {}),
        },
    )

    money = {"type": budget_type, "amount": str(budget), "currency": code}
    targeting: dict[str, Any] = {"countries": where}
    if age_min is not None:
        targeting["age_min"] = age_min
    if age_max is not None:
        targeting["age_max"] = age_max
    ad_set: dict[str, Any] = {"name": naming.ad_set, "targeting": targeting, "ads": ads}
    if optimization_goal:
        ad_set["optimization_goal"] = optimization_goal
        r.sources["ad_set.optimization_goal"] = "--optimization-goal"
    else:
        notes.append(
            "no optimisation goal: choose one valid for the objective (ads_get_field_context) "
            "and add it to the ad set before building"
        )
    tracking = {k: v for k, v in (("dataset_id", dataset), ("conversion_event", event)) if v}
    if tracking:
        ad_set["tracking"] = tracking
    if end is not None:
        ad_set["schedule"] = {"end": end.isoformat()}
    campaign: dict[str, Any] = {
        "name": campaign_name or naming.campaign,
        "objective": campaign_objective,
        "ad_sets": [ad_set],
    }
    if budget_level == "campaign":
        campaign["budget"] = {"level": "campaign", **money}
    else:
        ad_set["budget"] = {"level": "ad_set", **money}
    if brand and brand.special_ad_category:
        campaign["special_ad_categories"] = list(brand.special_ad_category)
        r.sources["campaign.special_ad_categories"] = "brand.yaml special_ad_category"
    dsa = (
        {k: v for k, v in (("beneficiary", brand.dsa.beneficiary), ("payor", brand.dsa.payor)) if v}
        if brand
        else {}
    )
    if dsa:
        campaign["dsa"] = dsa
        r.sources["campaign.dsa"] = "brand.yaml dsa"

    data: dict[str, Any] = {
        "schema_version": 1,
        "slug": slug,
        "ad_account_id": account_id,
        "campaign": campaign,
    }
    if created_at is not None:
        data["created_at"] = created_at.isoformat()
    if brand:
        data["brand"] = brand.name
    if offer_slug:
        data["offer"] = offer_slug

    try:
        draft = CampaignPlanDocument.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(f"the drafted plan is not valid: {exc}") from exc
    # Names and UTMs straight away, so what is reviewed is what gets built.
    rendered = render_plan(draft, brand, tz=tz)
    if len(ads) > 1:
        notes.append(f"{len(ads)} ads in one ad set, sharing its budget")
    return Scaffold(rendered.document, r.sources, notes)


def _only(values: list[str]) -> str | None:
    """The single value, when there is exactly one. Two is a choice, not a default."""
    return values[0] if len(values) == 1 else None


def _with_cta(variant: CopyVariant, cta: str | None) -> CopyVariant:
    return variant if variant.cta_type or not cta else variant.model_copy(update={"cta_type": cta})


def _resolve_split(
    split: str, assets: list[Asset], variants: list[CopyVariant], notes: list[str]
) -> str:
    many_assets, many_variants = len(assets) > 1, len(variants) > 1
    if split == "auto":
        if many_assets and many_variants:
            raise ValidationError(
                f"{len(variants)} copy variants and {len(assets)} assets can be combined two "
                "ways, and they are different tests. Pass --split matrix for one ad per "
                f"pairing ({len(variants) * len(assets)} ads, each reported separately), or "
                "--split multi-variant for one ad where Meta mixes them (one result, no "
                "per-pairing numbers)."
            )
        return "per-variant" if many_variants else "per-asset"
    if split == "per-asset" and many_variants:
        raise ValidationError(
            "--split per-asset takes one copy variant; with several, use matrix or multi-variant"
        )
    if split == "per-variant" and many_assets:
        raise ValidationError(
            "--split per-variant takes one asset; with several, use matrix or multi-variant"
        )
    if split == "multi-variant" and len({a.is_video for a in assets}) > 1:
        raise ValidationError(
            "--split multi-variant takes images or videos, not both. Plan two campaigns' "
            "worth of ads with --split matrix, or pass one kind."
        )
    if split == "matrix":
        notes.append(
            f"matrix: {len(variants)} variant(s) x {len(assets)} asset(s) = "
            f"{len(variants) * len(assets)} ads"
        )
    return split


def _ads(
    *,
    assets: list[Asset],
    variants: list[CopyVariant],
    split: str,
    ad_name: str,
    shared: dict[str, Any],
) -> list[dict[str, Any]]:
    def copy(variant: CopyVariant) -> dict[str, Any]:
        return variant.model_dump(mode="json", exclude_none=True)

    if split == "multi-variant":
        return [
            {
                "name": ad_name,
                "creative": {
                    "mode": "multi_variant",
                    "assets": [a.as_plan() for a in assets],
                    "variants": [copy(v) for v in variants],
                    **shared,
                },
            }
        ]
    pairs = [(v, a) for v in variants for a in assets]
    # {variant} names the angle. With several assets under one angle the names
    # would collide, so the asset's own name tells them apart.
    several_assets = len(assets) > 1
    return [
        {
            "name": f"{ad_name} | {asset.label}" if several_assets else ad_name,
            "creative": {
                "mode": "single_video" if asset.is_video else "single_image",
                "assets": [asset.as_plan()],
                "variants": [copy(variant)],
                **shared,
            },
        }
        for variant, asset in pairs
    ]


def load_variants(raw: Any, source: str) -> list[CopyVariant]:
    """Copy variants from a parsed YAML file: a list, or ``{"variants": [...]}``."""
    if isinstance(raw, dict):
        raw = raw.get("variants")
    if not isinstance(raw, list) or not raw:
        raise ValidationError(
            f"{source} has no copy variants. Expected a list, or `variants:` holding one, "
            "each with `angle` and `primary_text`."
        )
    try:
        return [CopyVariant.model_validate(item) for item in raw]
    except PydanticValidationError as exc:
        raise ValidationError(f"{source} is not valid copy: {exc}") from exc


def relative_asset(path: str, plan_dir: Path) -> str:
    """*path* as the plan will name it: relative to the plan's own directory.

    Plans resolve local assets against their own directory, so a workspace
    moves between machines. A path on another drive stays absolute.
    """
    target = Path(path).expanduser().resolve()
    try:
        return Path(os.path.relpath(target, plan_dir.resolve())).as_posix()
    except ValueError:  # Windows: a different drive
        return target.as_posix()
