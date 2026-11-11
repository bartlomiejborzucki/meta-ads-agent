"""A validated plan, as the Meta MCP calls that build it.

The plan speaks in display amounts, country lists and creative modes. Meta's
MCP tools want minor currency units, ``targeting`` and ``creative`` as
JSON-encoded strings, a numeric account id, and one flat parameter set per
creative format. Turning one into the other by hand, in a conversation, is
where a 70.00 PLN budget becomes 70 minor units, or a targeting object is sent
where a string was expected. This module does that translation in code.

What it produces is **a proposal with a date on it**. The argument names
below are the ones Meta's tool schemas listed on :data:`SCHEMA_READ`; Meta
changes those schemas without notice, and nothing here has been run against a
live account. A call that Meta rejects is settled by reading the error, as
always - the error wins over this file.

Each call carries:

``args``   the arguments, ready to send. An id that does not exist yet is
           written ``<id:PLAN_REF>``; ``refs`` lists which arguments have one.
``needs``  what a person or the agent must decide before the call can be made.
           The compiler does not guess an optimisation goal or a thumbnail.
``done``   the id already recorded in state for this plan element, so a
           resumed build skips what exists.

It leaves out the fields every Meta call carries about the conversation
itself (``client_conversation_id``, ``advertiser_job``, ...): those are the
agent's to fill, per call.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import (
    ASSET_PLACEMENTS,
    AdPlan,
    AdSetPlan,
    AssetRef,
    Budget,
    BudgetType,
    CampaignPlanDocument,
    CopyVariant,
    CreativeMode,
    CreativePlan,
)
from meta_ads_agent.models.state import CampaignState
from meta_ads_agent.money import Money
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.validation.checks_account import EU_EEA_COUNTRIES

#: The day the tool schemas these arguments follow were read.
SCHEMA_READ = "2026-11-11"

# What an uploaded local file is known as on Meta, if it has been uploaded
# before: ("image_hash" | "video_id", value). None when it has not.
AssetLookup = Callable[[Path], "tuple[str, str] | None"]

# Publisher platforms, longest first, for splitting a position such as
# "audience_network_classic" into its platform and Meta's position name.
_PLATFORMS = ("audience_network", "facebook", "instagram", "messenger", "threads", "whatsapp")


@dataclass(slots=True)
class Call:
    step: int
    tool: str
    plan_ref: str
    record_type: str
    args: dict[str, Any]
    refs: dict[str, str] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    done: str | None = None
    #: For an upload: the local file, so its id can be remembered against it.
    file: Path | None = None


@dataclass(slots=True)
class CallPlan:
    calls: list[Call] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def pending(self) -> list[Call]:
        return [c for c in self.calls if c.done is None]

    @property
    def complete(self) -> bool:
        """Every remaining call can be made as written."""
        return not any(c.needs for c in self.pending)


def _json(value: Any) -> str:
    """A JSON-encoded string, the way Meta's tools take nested arguments."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _placeholder(plan_ref: str) -> str:
    return f"<id:{plan_ref}>"


class _Compiler:
    def __init__(
        self,
        doc: CampaignPlanDocument,
        account: AccountContext | None,
        brand: BrandConfig | None,
        state: CampaignState | None,
        asset_base: Path,
        asset_lookup: AssetLookup | None,
    ) -> None:
        self.doc = doc
        self.account = account
        self.brand = brand
        self.state = state
        self.asset_base = asset_base
        self.asset_lookup = asset_lookup
        self.plan = CallPlan()
        self.account_id = doc.ad_account_id.removeprefix("act_")
        # A local file -> the plan_ref of the call that uploads it, or the
        # remote identity it already has.
        self._uploads: dict[Path, str] = {}
        self._known: dict[Path, tuple[str, str]] = {}

    # -- shared ------------------------------------------------------------
    def _id(self, plan_ref: str) -> str | None:
        obj = self.state.by_plan_ref(plan_ref) if self.state else None
        return obj.id if obj else None

    def _ref(self, call: Call, arg: str, plan_ref: str) -> str:
        """The id recorded for *plan_ref*, or a placeholder noted on *call*."""
        known = self._id(plan_ref)
        if known:
            return known
        call.refs[arg] = plan_ref
        return _placeholder(plan_ref)

    def _add(self, tool: str, plan_ref: str, record_type: str) -> Call:
        call = Call(
            len(self.plan.calls) + 1, tool, plan_ref, record_type, {}, done=self._id(plan_ref)
        )
        self.plan.calls.append(call)
        return call

    def _minor(self, amount: Any, currency: str) -> int:
        offset = (
            self.account.currency_offset
            if self.account
            and self.account.currency_offset is not None
            and self.account.currency == currency
            else None
        )
        return Money.from_display(amount, currency, offset=offset).minor

    def _budget_args(self, budget: Budget, daily: str, lifetime: str) -> dict[str, int]:
        key = daily if budget.type is BudgetType.DAILY else lifetime
        return {key: self._minor(budget.amount, budget.currency)}

    # -- campaign ----------------------------------------------------------
    def campaign(self) -> None:
        plan = self.doc.campaign
        call = self._add("ads_create_campaign", "campaign", "campaign")
        args: dict[str, Any] = {
            "ad_account_id": self.account_id,
            "campaign_name": plan.name,
            "objective": plan.objective,
            "buying_type": plan.buying_type,
        }
        if plan.special_ad_categories:
            args["special_ad_categories"] = _json(list(plan.special_ad_categories))
            countries = sorted({c for s in plan.ad_sets for c in s.targeting.countries})
            # The schema: every country an ad set targets must be listed here.
            args["special_ad_category_country"] = _json(countries)
        if plan.budget:
            args.update(
                self._budget_args(plan.budget, "campaign_daily_budget", "campaign_lifetime_budget")
            )
            strategies = sorted({s.bid_strategy for s in plan.ad_sets if s.bid_strategy})
            if len(strategies) == 1:
                args["campaign_bid_strategy"] = strategies[0]
                call.notes.append(
                    "with a campaign budget the bid strategy is the campaign's; the plan's "
                    "ad-set bid_strategy is sent here"
                )
            elif strategies:
                call.needs.append(
                    f"the ad sets name different bid strategies {strategies}, and with a "
                    "campaign budget there is one, on the campaign: choose it"
                )
        if plan.spend_cap:
            args["campaign_spend_cap"] = self._minor(plan.spend_cap.amount, plan.spend_cap.currency)
        if plan.schedule.start:
            args["campaign_start_time"] = plan.schedule.start.isoformat()
        if plan.schedule.end:
            args["campaign_stop_time"] = plan.schedule.end.isoformat()
        if plan.conversion_location:
            call.notes.append(
                f"conversion_location {plan.conversion_location!r} is not a campaign argument; "
                "it decides each ad set's destination_type"
            )
        call.args = args

    # -- ad sets -----------------------------------------------------------
    def ad_set(self, index: int, ad_set: AdSetPlan) -> None:
        ref = f"ad_sets[{index}]"
        call = self._add("ads_create_ad_set", ref, "ad_set")
        args: dict[str, Any] = {
            "ad_account_id": self.account_id,
            "campaign_id": self._ref(call, "campaign_id", "campaign"),
            "ad_set_name": ad_set.name,
            "billing_event": ad_set.billing_event or "IMPRESSIONS",
            "targeting": _json(self._targeting(ad_set, call)),
        }
        if not ad_set.billing_event:
            call.notes.append(
                "billing_event IMPRESSIONS: the plan sets none, and the schema says it is "
                "valid for every optimisation goal"
            )
        if ad_set.optimization_goal:
            args["optimization_goal"] = ad_set.optimization_goal
        else:
            call.needs.append(
                "optimization_goal: the plan sets none. Choose from valid_optimization_goals "
                "in the ads_create_campaign response, and write it into the plan"
            )
        cbo = self.doc.campaign.budget is not None
        if ad_set.budget:
            args.update(self._budget_args(ad_set.budget, "daily_budget", "lifetime_budget"))
        currency = self.doc.campaign.currency
        if ad_set.bid_amount is not None and currency:
            args["bid_amount"] = self._minor(ad_set.bid_amount, currency)
        if ad_set.bid_strategy and not cbo:
            args["bid_strategy"] = ad_set.bid_strategy
        if ad_set.schedule.start:
            args["start_time"] = ad_set.schedule.start.isoformat()
        if ad_set.schedule.end:
            args["end_time"] = ad_set.schedule.end.isoformat()
        elif (ad_set.budget and ad_set.budget.type is BudgetType.LIFETIME) or (
            self.doc.campaign.budget
            and self.doc.campaign.budget.type is BudgetType.LIFETIME
            and not self.doc.campaign.schedule.end
        ):
            call.needs.append("end_time: a lifetime budget needs the ad set's end date")

        dsa = self.doc.campaign.dsa
        beneficiary = dsa.beneficiary or (self.brand.dsa.beneficiary if self.brand else None)
        payor = dsa.payor or (self.brand.dsa.payor if self.brand else None)
        if beneficiary:
            args["dsa_beneficiary"] = beneficiary
        if payor:
            args["dsa_payor"] = payor
        if set(ad_set.targeting.countries) & EU_EEA_COUNTRIES and not (beneficiary and payor):
            call.needs.append(
                "dsa_beneficiary / dsa_payor: EU delivery, and neither the plan nor brand.yaml "
                "names them. Left out, Meta fills both from the account's business name - "
                "confirm that with the user, do not assume it"
            )

        tracking = ad_set.tracking
        if tracking.custom_conversion_id:
            args["promoted_object"] = _json({"custom_conversion_id": tracking.custom_conversion_id})
        elif tracking.dataset_id:
            promoted: dict[str, str] = {"pixel_id": tracking.dataset_id}
            if tracking.conversion_event:
                promoted["custom_event_type"] = tracking.conversion_event
            args["promoted_object"] = _json(promoted)
        call.args = args

    def _targeting(self, ad_set: AdSetPlan, call: Call) -> dict[str, Any]:
        """The targeting spec. What the plan models wins over ``targeting.raw``."""
        t = ad_set.targeting
        spec: dict[str, Any] = json.loads(json.dumps(t.raw))  # a deep copy of plain data
        geo = dict(spec.get("geo_locations") or {})
        geo["countries"] = list(t.countries)
        spec["geo_locations"] = geo
        if t.age_min is not None:
            spec["age_min"] = t.age_min
        if t.age_max is not None:
            spec["age_max"] = t.age_max
        if t.genders == "all":
            spec.pop("genders", None)
        else:
            spec["genders"] = [1] if t.genders == "male" else [2]
        if t.custom_audience_ids:
            spec["custom_audiences"] = [{"id": i} for i in t.custom_audience_ids]
        if t.excluded_custom_audience_ids:
            spec["excluded_custom_audiences"] = [{"id": i} for i in t.excluded_custom_audience_ids]
        if t.age_suggestion:
            spec["age_range"] = [t.age_suggestion.min, t.age_suggestion.max]
        if t.advantage_audience is not None:
            spec["targeting_automation"] = {"advantage_audience": 1 if t.advantage_audience else 0}
            if not t.advantage_audience:
                call.needs.append(
                    "advantage_audience_off_reason: the plan turns Advantage+ audience off, and "
                    "the schema wants the reason - ADVERTISER_REQUESTED_OFF, "
                    "HARD_AGE_REQUIREMENT, CUSTOM_AUDIENCE_ONLY or ADVANTAGE_AUDIENCE_UNAVAILABLE"
                )
        if t.interests:
            call.needs.append(
                f"interests {t.interests} are names, and Meta takes interest ids only. Put the "
                "ids the user gave under targeting.raw.flexible_spec, or drop them"
            )
        placements = ad_set.placements
        if placements.mode == "manual":
            for key in ("publisher_platforms", *(f"{p}_positions" for p in _PLATFORMS)):
                spec.pop(key, None)
            platforms: list[str] = list(placements.platforms)
            for position in placements.positions:
                platform, name = _position(position)
                if platform not in platforms:
                    platforms.append(platform)
                spec.setdefault(f"{platform}_positions", []).append(name)
            spec["publisher_platforms"] = platforms
        return spec

    # -- assets ------------------------------------------------------------
    def _resolve(self, path: str) -> Path:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.asset_base / target
        # Tidy, without touching the disk: the path is shown to a person, and
        # is the key that tells two spellings of one file apart.
        return Path(os.path.normpath(target))

    def uploads(self) -> None:
        """One upload per distinct local file not already on the account."""
        for index, ad_set in enumerate(self.doc.campaign.ad_sets):
            for ad_index, ad in enumerate(ad_set.ads):
                for where, asset in ad.creative.asset_refs():
                    if not asset.local_path:
                        continue
                    target = self._resolve(asset.local_path)
                    if target in self._uploads or target in self._known:
                        continue
                    known = self.asset_lookup(target) if self.asset_lookup else None
                    if known:
                        self._known[target] = known
                        continue
                    ref = f"ad_sets[{index}].ads[{ad_index}].creative.{where}"
                    self._uploads[target] = ref
                    video = _is_video(asset)
                    call = self._add(
                        "ads_creative_upload_media", ref, "video" if video else "image"
                    )
                    call.args = {"ad_account_id": self.account_id, "upload_source": "LOCAL_FILE"}
                    call.file = target
                    call.notes.append(
                        f"file: {target}. LOCAL_FILE opens Meta's upload app, where the user "
                        "picks it - only in a host that shows interactive MCP Apps. Elsewhere: "
                        'upload_source "URL" with media_type '
                        f'"{"VIDEO" if video else "IMAGE"}" and a direct public media_url'
                    )
                    if video:
                        call.notes.append(
                            "a video is usable once ads_get_ad_videos reports it ready"
                        )

    def _media(self, call: Call, asset: AssetRef, arg: str) -> dict[str, str]:
        """``{"image_hash": ...}`` or ``{"video_id": ...}`` for one asset."""
        if asset.image_hash:
            return {"image_hash": asset.image_hash}
        if asset.video_id:
            return {"video_id": asset.video_id}
        target = self._resolve(asset.local_path or "")
        if target in self._known:
            key, value = self._known[target]
            return {key: value}
        key = "video_id" if _is_video(asset) else "image_hash"
        return {key: self._ref(call, arg, self._uploads[target])}

    # -- creatives and ads -------------------------------------------------
    def creative_and_ad(self, set_index: int, ad_index: int, ad: AdPlan) -> None:
        ad_ref = f"ad_sets[{set_index}].ads[{ad_index}]"
        creative = ad.creative
        if creative.mode is not CreativeMode.EXISTING_POST:
            self._creative(f"{ad_ref}.creative", ad, creative)
        self._pending_ads.append((set_index, ad_ref, ad))

    def _creative(self, ref: str, ad: AdPlan, creative: CreativePlan) -> None:
        call = self._add("ads_create_creative", ref, "creative")
        args: dict[str, Any] = {"ad_account_id": self.account_id, "name": ad.name}
        if creative.page_id:
            args["page_id"] = creative.page_id
        if creative.instagram_account_id:
            args["instagram_user_id"] = creative.instagram_account_id
        if creative.destination_url:
            args["link_url"] = creative.destination_url
        if creative.display_link:
            args["display_link"] = creative.display_link
        ctas = sorted({v.cta_type for v in creative.variants if v.cta_type})
        if ctas:
            args["call_to_action_type"] = ctas[0]
            if len(ctas) > 1:
                call.needs.append(
                    f"the variants name different calls to action {ctas}, and a creative has "
                    "one button: choose it"
                )

        mode = creative.mode
        pinned = [a for a in creative.assets if a.placement]
        if mode is CreativeMode.CAROUSEL:
            args["cards"] = [self._card(call, i, card) for i, card in enumerate(creative.cards)]
            self._one_copy(args, creative.variants)
        elif mode is CreativeMode.SINGLE_VIDEO:
            args.update(self._media(call, creative.assets[0], "video_id"))
            if creative.thumbnail:
                args.update(self._media(call, creative.thumbnail, "image_hash"))
            else:
                call.needs.append(
                    "a thumbnail: Meta requires image_hash or image_url with a video. Add "
                    "`thumbnail` to the plan's creative, or pass an image_url of one of the "
                    "frames ads_get_ad_videos lists"
                )
            self._one_copy(args, creative.variants)
        elif mode is CreativeMode.SINGLE_IMAGE:
            args.update(self._media(call, creative.assets[0], "image_hash"))
            self._one_copy(args, creative.variants)
        elif pinned:
            self._placement_customizations(call, args, creative)
        elif len(creative.assets) > 1:
            args["multi_media"] = [
                self._media(call, asset, f"multi_media[{i}]")
                for i, asset in enumerate(creative.assets)
            ]
            self._variants(args, creative.variants)
        else:
            # One asset, several texts: a single image or video with variants.
            args.update(self._media(call, creative.assets[0], "media"))
            if "video_id" in args:
                call.needs.append("a thumbnail: Meta requires image_hash or image_url with a video")
            self._variants(args, creative.variants)

        if creative.advantage.enhancements:
            args["degrees_of_freedom_spec"] = _json(
                {
                    "creative_features_spec": {
                        name: {"enroll_status": "OPT_IN" if enabled else "OPT_OUT"}
                        for name, enabled in sorted(creative.advantage.enhancements.items())
                    }
                }
            )
        call.args = args

    @staticmethod
    def _one_copy(args: dict[str, Any], variants: list[CopyVariant]) -> None:
        variant = variants[0]
        args["message"] = variant.primary_text
        if variant.headline:
            args["headline"] = variant.headline
        if variant.description:
            args["description"] = variant.description

    @staticmethod
    def _variants(args: dict[str, Any], variants: list[CopyVariant]) -> None:
        """Up to five variants of each text; a single value goes in the singular field."""
        for source, plural, singular in (
            ("primary_text", "primary_texts", "message"),
            ("headline", "headlines", "headline"),
            ("description", "descriptions", "description"),
        ):
            values = list(dict.fromkeys(getattr(v, source) for v in variants if getattr(v, source)))
            if len(values) > 1:
                args[plural] = values
            elif values:
                args[singular] = values[0]

    def _card(self, call: Call, index: int, card: Any) -> dict[str, str]:
        out = self._media(call, card.asset, f"cards[{index}]")
        if card.link:
            out["link"] = card.link
        if card.headline:
            out["headline"] = card.headline
        if card.description:
            out["description"] = card.description
        return out

    def _placement_customizations(
        self, call: Call, args: dict[str, Any], creative: CreativePlan
    ) -> None:
        unpinned = [a for a in creative.assets if not a.placement]
        if len(unpinned) != 1:
            call.needs.append(
                f"{len(unpinned)} assets have no placement, and a placement-customised creative "
                "takes exactly one fallback. Pin the others, or plan two ads"
            )
        entries: list[dict[str, Any]] = []
        by_media: dict[str, dict[str, Any]] = {}
        for index, asset in enumerate(creative.assets):
            media = self._media(call, asset, f"placement_customizations[{index}]")
            key = _json(media)
            entry = by_media.get(key)
            if entry is None:
                entry = dict(media)
                by_media[key] = entry
                entries.append(entry)
            if asset.placement:
                platform, position = ASSET_PLACEMENTS[asset.placement]
                platforms = entry.setdefault("publisher_platforms", [])
                if platform not in platforms:
                    platforms.append(platform)
                entry.setdefault(f"{platform}_positions", []).append(position)
        args["placement_customizations"] = entries
        if len(creative.variants) > 1:
            call.notes.append(
                "a placement-customised creative shares one copy across its assets; the "
                "first variant is sent"
            )
        self._one_copy(args, creative.variants)

    def ads(self) -> None:
        for set_index, ad_ref, ad in self._pending_ads:
            call = self._add("ads_create_ad", ad_ref, "ad")
            creative = ad.creative
            if creative.mode is CreativeMode.EXISTING_POST:
                spec: dict[str, str] = (
                    {"source_instagram_media_id": creative.instagram_media_id}
                    if creative.instagram_media_id
                    else {"object_story_id": creative.post_id or ""}
                )
                if creative.instagram_account_id:
                    spec["instagram_user_id"] = creative.instagram_account_id
                call.notes.append(
                    "the post goes inline in the ad. It keeps its own text; for a button, add "
                    "call_to_action to this creative (see the campaign skill)"
                )
            else:
                spec = {"creative_id": self._ref(call, "creative", f"{ad_ref}.creative")}
            call.args = {
                "ad_account_id": self.account_id,
                "ad_set_id": self._ref(call, "ad_set_id", f"ad_sets[{set_index}]"),
                "ad_name": ad.name,
                "creative": _json(spec),
            }

    _pending_ads: list[tuple[int, str, AdPlan]]

    def run(self) -> CallPlan:
        self._pending_ads = []
        self.campaign()
        for index, ad_set in enumerate(self.doc.campaign.ad_sets):
            self.ad_set(index, ad_set)
        self.uploads()
        for index, ad_set in enumerate(self.doc.campaign.ad_sets):
            for ad_index, ad in enumerate(ad_set.ads):
                self.creative_and_ad(index, ad_index, ad)
        self.ads()
        if any(c.tool == "ads_create_creative" and c.done is None for c in self.plan.calls):
            self.plan.notes.append(
                "ads_create_creative also takes self_ai_disclosure (OPT_IN or OPT_OUT) for "
                "media created or edited with generative AI. It cannot be set afterwards "
                "and is the advertiser's decision: ask them, do not choose for them"
            )
        if self.account is None or self.account.currency_offset is None:
            self.plan.notes.append(
                "budgets are converted with the built-in currency table; cache the account "
                "(`cache-account`) so Meta's own offset is used"
            )
        return self.plan


def _is_video(asset: AssetRef) -> bool:
    from meta_ads_agent.models._common import looks_like_video

    return bool(asset.video_id or (asset.local_path and looks_like_video(asset.local_path)))


def _position(name: str) -> tuple[str, str]:
    """``instagram_stories`` -> ("instagram", "story"), in Meta's own vocabulary."""
    if name in ASSET_PLACEMENTS:
        return ASSET_PLACEMENTS[name]
    for platform in _PLATFORMS:
        if name.startswith(f"{platform}_"):
            return platform, name[len(platform) + 1 :]
    return name, name


def compile_calls(
    doc: CampaignPlanDocument,
    *,
    account: AccountContext | None = None,
    brand: BrandConfig | None = None,
    state: CampaignState | None = None,
    asset_base: Path | str | None = None,
    asset_lookup: AssetLookup | None = None,
) -> CallPlan:
    """The MCP calls that build *doc*, in order: campaign, ad sets, uploads, creatives, ads."""
    base = Path(asset_base) if asset_base else Path.cwd()
    return _Compiler(doc, account, brand, state, base, asset_lookup).run()
