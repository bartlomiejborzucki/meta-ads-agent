"""A campaign read from Meta, turned into a new plan.

Duplicating a campaign is usually "the same again, with one thing changed".
Doing it as a plan rather than a copy call keeps the usual gate: the new
plan is reviewed, rendered and validated, then built PAUSED, and nothing
about the source is touched.

The input is what the agent read from Meta, saved as JSON in the Marketing
API's field names (docs/reference/duplicate-input.md)::

    {"ad_account_id": "act_...", "currency": "PLN",
     "campaign": {...}, "ad_sets": [{..., "ads": [{"name": ..., "creative": {...}}]}]}

What is copied, and what is deliberately not:

* Budgets and bids arrive in minor units and become display amounts in the
  account currency. Without a currency they cannot be read, so they are
  refused rather than guessed.
* Schedules are not copied: the source's dates are usually in the past.
* Targeting fields the plan models are mapped; every other targeting key is
  kept verbatim in ``targeting.raw``, so nothing narrows silently.
* A creative is mapped when its shape is one the plan can express: a single
  image or video link ad, a carousel, or an existing post. A multi-variant
  creative (``asset_feed_spec``) is refused, naming the ad: its rules do not
  survive a round trip through this model.
* Every status is PAUSED. The model has no field for anything else.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.errors import ValidationError
from meta_ads_agent.models.plan import ASSET_PLACEMENTS, CampaignPlanDocument
from meta_ads_agent.money import Money

# Targeting keys the plan models. Everything else goes to raw.
_MODELLED_TARGETING = {
    "age_min",
    "age_max",
    "genders",
    "custom_audiences",
    "excluded_custom_audiences",
    "targeting_automation",
}
_POSITION_KEYS = {
    "facebook": "facebook_positions",
    "instagram": "instagram_positions",
    "messenger": "messenger_positions",
    "audience_network": "audience_network_positions",
    "threads": "threads_positions",
}
_PLACEMENT_NAMES = {pair: name for name, pair in ASSET_PLACEMENTS.items()}


@dataclass(slots=True)
class Duplicate:
    document: CampaignPlanDocument
    notes: list[str] = field(default_factory=list)


def duplicate_plan(
    source: dict[str, Any],
    *,
    slug: str,
    name: str | None = None,
    currency: str | None = None,
    account: str | None = None,
) -> Duplicate:
    """Build a new plan from a saved campaign, or raise naming what blocks it."""
    if not isinstance(source, dict) or not isinstance(source.get("campaign"), dict):
        raise ValidationError('the source must be {"campaign": {...}, "ad_sets": [...]}')
    campaign = source["campaign"]
    ad_sets = source.get("ad_sets", source.get("adsets"))
    if not isinstance(ad_sets, list) or not ad_sets:
        raise ValidationError("the source has no ad_sets; read them with the campaign")

    notes: list[str] = []
    code = (currency or source.get("currency") or "").upper() or None
    offset = source.get("currency_offset")
    account_id = _account(account or source.get("ad_account_id") or campaign.get("account_id"))

    def money(value: Any, where: str) -> Decimal | None:
        if value in (None, "", "0", 0):
            return None
        if code is None:
            raise ValidationError(
                f"{where} is {value} in minor units, and no currency was given. Pass "
                "--currency with the account's currency (read it from Meta)."
            )
        return Money.from_minor(int(str(value)), code, offset=offset).display

    campaign_budget = _budget(campaign, "campaign", money, code)
    plan_ad_sets = []
    for index, raw_set in enumerate(ad_sets):
        where = f"ad_sets[{index}] {raw_set.get('name', '')!r}".rstrip()
        plan_ad_sets.append(_ad_set(raw_set, where, money, code, campaign_budget, notes))

    if any(s.get("start_time") or s.get("end_time") for s in ad_sets) or campaign.get("stop_time"):
        notes.append("schedules were not copied; set start and end for the new campaign")

    data: dict[str, Any] = {
        "schema_version": 1,
        "slug": slug,
        "ad_account_id": account_id,
        "notes": (
            f"Duplicated from campaign {campaign.get('id', '?')} "
            f"({campaign.get('name', '?')}) on {_dt.date.today()}."
        ),
        "campaign": {
            "name": name or f"{campaign.get('name', 'Campaign')} (copy)",
            "objective": _required(campaign, "objective", "campaign"),
            "buying_type": campaign.get("buying_type") or "AUCTION",
            "special_ad_categories": [
                c for c in campaign.get("special_ad_categories") or [] if c != "NONE"
            ],
            "ad_sets": plan_ad_sets,
            "status": "PAUSED",
        },
    }
    if campaign_budget:
        data["campaign"]["budget"] = campaign_budget
    dsa = {
        key: next((str(s[f"dsa_{key}"]) for s in ad_sets if s.get(f"dsa_{key}")), None)
        for key in ("beneficiary", "payor")
    }
    if any(dsa.values()):
        data["campaign"]["dsa"] = {k: v for k, v in dsa.items() if v}
    if campaign.get("bid_strategy"):
        notes.append(
            f"the source campaign sets bid strategy {campaign['bid_strategy']}, which a plan "
            "has no campaign field for; set it when the campaign is built"
        )

    try:
        document = CampaignPlanDocument.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(f"the copied plan is not valid: {exc}") from exc
    return Duplicate(document, notes)


def _account(value: Any) -> str:
    if not value:
        raise ValidationError("no ad account in the source; pass --account act_<id>")
    text = str(value)
    return text if text.startswith("act_") else f"act_{text}"


def _required(obj: dict[str, Any], key: str, where: str) -> Any:
    if not obj.get(key):
        raise ValidationError(f"{where} has no {key}; read it with the other fields")
    return obj[key]


def _budget(obj: dict[str, Any], level: str, money: Any, code: str | None) -> dict[str, Any] | None:
    for kind in ("daily", "lifetime"):
        amount = money(obj.get(f"{kind}_budget"), f"{level} {kind}_budget")
        if amount is not None:
            return {
                "level": "campaign" if level == "campaign" else "ad_set",
                "type": kind,
                "amount": str(amount),
                "currency": code,
            }
    return None


def _ad_set(
    raw: dict[str, Any],
    where: str,
    money: Any,
    code: str | None,
    campaign_budget: dict[str, Any] | None,
    notes: list[str],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": _required(raw, "name", where),
        "targeting": _targeting(raw.get("targeting") or {}, where),
        "status": "PAUSED",
    }
    for key in ("optimization_goal", "billing_event", "bid_strategy"):
        if raw.get(key):
            out[key] = raw[key]
    bid = money(raw.get("bid_amount"), f"{where} bid_amount")
    if bid is not None:
        out["bid_amount"] = str(bid)
    budget = _budget(raw, "ad_set", money, code)
    if budget and campaign_budget:
        notes.append(f"{where}: its own budget was dropped; the campaign budget governs")
    elif budget:
        out["budget"] = budget

    placements = _placements(raw.get("targeting") or {})
    if placements:
        out["placements"] = {"mode": "manual", "positions": placements}

    tracking: dict[str, Any] = {}
    promoted = raw.get("promoted_object") or {}
    if promoted.get("pixel_id"):
        tracking["dataset_id"] = str(promoted["pixel_id"])
    if promoted.get("custom_event_type"):
        tracking["conversion_event"] = promoted["custom_event_type"]
    if promoted.get("custom_conversion_id"):
        tracking["custom_conversion_id"] = str(promoted["custom_conversion_id"])
    if tracking:
        out["tracking"] = tracking

    ads = raw.get("ads") or []
    if not ads:
        raise ValidationError(f"{where} has no ads; read them with the ad set")
    out["ads"] = [_ad(ad, f"{where} ad {ad.get('name', i)!r}") for i, ad in enumerate(ads)]
    return out


def _targeting(raw: dict[str, Any], where: str) -> dict[str, Any]:
    geo = raw.get("geo_locations") or {}
    countries = geo.get("countries") or []
    if not countries:
        raise ValidationError(
            f"{where}: targeting has no geo_locations.countries. A plan needs the "
            "countries it delivers to; add them by hand."
        )
    out: dict[str, Any] = {"countries": list(countries)}
    for key in ("age_min", "age_max"):
        if raw.get(key) is not None:
            out[key] = int(raw[key])
    genders = sorted(set(raw.get("genders") or []))
    out["genders"] = {(1,): "male", (2,): "female"}.get(tuple(genders), "all")
    out["custom_audience_ids"] = [str(a["id"]) for a in raw.get("custom_audiences") or []]
    out["excluded_custom_audience_ids"] = [
        str(a["id"]) for a in raw.get("excluded_custom_audiences") or []
    ]
    automation = raw.get("targeting_automation") or {}
    if "advantage_audience" in automation:
        out["advantage_audience"] = bool(automation["advantage_audience"])
    rest = {k: v for k, v in raw.items() if k not in _MODELLED_TARGETING}
    if set(geo) - {"countries"}:
        rest["geo_locations"] = geo  # regions, cities, exclusions: kept whole
    else:
        rest.pop("geo_locations", None)
    if rest:
        out["raw"] = rest
    return out


def _placements(targeting: dict[str, Any]) -> list[str]:
    platforms = targeting.get("publisher_platforms") or []
    positions: list[str] = []
    for platform in platforms:
        for position in targeting.get(_POSITION_KEYS.get(platform, ""), []) or []:
            positions.append(_PLACEMENT_NAMES.get((platform, position), f"{platform}_{position}"))
        if not targeting.get(_POSITION_KEYS.get(platform, "")):
            positions.append(platform)
    return positions


def _ad(ad: dict[str, Any], where: str) -> dict[str, Any]:
    creative = ad.get("creative") or {}
    return {
        "name": _required(ad, "name", where),
        "creative": _creative(creative, where),
        "status": "PAUSED",
    }


def _creative(c: dict[str, Any], where: str) -> dict[str, Any]:
    if c.get("asset_feed_spec"):
        raise ValidationError(
            f"{where}: a multi-variant creative (asset_feed_spec) is not copied - its "
            "rules do not survive this model. Plan that ad by hand."
        )
    spec = c.get("object_story_spec") or {}
    identity = {
        k: str(v)
        for k, v in {
            "page_id": spec.get("page_id"),
            "instagram_account_id": spec.get("instagram_user_id")
            or spec.get("instagram_actor_id")
            or c.get("instagram_user_id"),
        }.items()
        if v
    }

    if c.get("source_instagram_media_id") and not spec:
        return {
            "mode": "existing_post",
            "instagram_media_id": str(c["source_instagram_media_id"]),
            **identity,
        }
    if not spec:
        post = c.get("object_story_id") or c.get("effective_object_story_id")
        if post:
            page = str(post).split("_", 1)[0]
            return {"mode": "existing_post", "post_id": str(post), "page_id": page}
        raise ValidationError(
            f"{where}: the creative has no object_story_spec or post id. Read the "
            "creative's fields, not only its id."
        )

    if spec.get("video_data"):
        video = spec["video_data"]
        cta = video.get("call_to_action") or {}
        link = (cta.get("value") or {}).get("link")
        if not link:
            raise ValidationError(f"{where}: the video creative has no call_to_action link")
        return {
            "mode": "single_video",
            "destination_url": link,
            "assets": [{"video_id": str(video["video_id"])}],
            "variants": [
                _variant(where, video.get("message"), video.get("title"),
                         video.get("link_description"), cta.get("type"))
            ],
            **identity,
        }  # fmt: skip

    link_data = spec.get("link_data")
    if not link_data:
        raise ValidationError(
            f"{where}: object_story_spec has neither link_data nor video_data; "
            "this creative's shape is not one a plan can express"
        )
    cta_type = (link_data.get("call_to_action") or {}).get("type")
    common = {"destination_url": _required(link_data, "link", where), **identity}
    if link_data.get("caption"):
        common["display_link"] = link_data["caption"]

    cards = link_data.get("child_attachments") or []
    if cards:
        return {
            "mode": "carousel",
            "cards": [_card(card, f"{where} card {i}") for i, card in enumerate(cards)],
            "variants": [_variant(where, link_data.get("message"), None, None, cta_type)],
            **common,
        }
    if not link_data.get("image_hash"):
        raise ValidationError(f"{where}: the link creative has no image_hash")
    return {
        "mode": "single_image",
        "assets": [{"image_hash": link_data["image_hash"]}],
        "variants": [
            _variant(where, link_data.get("message"), link_data.get("name"),
                     link_data.get("description"), cta_type)
        ],
        **common,
    }  # fmt: skip


def _card(card: dict[str, Any], where: str) -> dict[str, Any]:
    if card.get("video_id"):
        asset: dict[str, Any] = {"video_id": str(card["video_id"])}
    elif card.get("image_hash"):
        asset = {"image_hash": card["image_hash"]}
    else:
        raise ValidationError(f"{where}: no image_hash or video_id")
    out: dict[str, Any] = {"asset": asset}
    for source, target in (("name", "headline"), ("description", "description"), ("link", "link")):
        if card.get(source):
            out[target] = card[source]
    return out


def _variant(
    where: str,
    message: str | None,
    headline: str | None,
    description: str | None,
    cta_type: str | None,
) -> dict[str, Any]:
    if not message:
        raise ValidationError(f"{where}: the creative has no primary text (message)")
    out: dict[str, Any] = {"angle": "as in the source campaign", "primary_text": message}
    if headline:
        out["headline"] = headline
    if description:
        out["description"] = description
    if cta_type:
        out["cta_type"] = cta_type
    return out
