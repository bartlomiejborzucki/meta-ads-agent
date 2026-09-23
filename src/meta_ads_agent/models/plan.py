"""The campaign plan: the source of truth for *intent*.

A plan is written, validated, and reviewed before any write reaches Meta. Once
validated it - not the conversation - is what execution reads. Re-parsing prose
when a structured artifact already exists is how agents drift from what the
user approved.

Deliberate design choices:

* **No hardcoded objective or optimization-goal enums.** Meta's valid values
  change with every API version. Fields are shape-checked (UPPER_SNAKE_CASE)
  and verified against the live platform via the field-metadata tool. See
  ADR-007.
* **Budgets are display amounts plus a currency**, converted to minor units by
  :mod:`meta_ads_agent.money` at the boundary. A plan a human reviews must show
  ``70.00 PLN``, not ``7000``.
* **Status is constrained to PAUSED at plan level.** There is no field for
  "create this active". Activation is a separate, approved operation on
  reviewed objects. See ADR-004.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from meta_ads_agent.models._common import (
    AccountId,
    CountryCode,
    CurrencyCode,
    HttpUrl,
    MetaEnum,
    MetaId,
    PostId,
    StrictModel,
)


class BudgetLevel(StrEnum):
    """Where the budget is set.

    Meta rejects a budget on both levels at once, so this is a platform
    constraint, not a preference. Which one to choose is a media-buying
    judgement and belongs in the campaign skill.
    """

    CAMPAIGN = "campaign"
    AD_SET = "ad_set"


class BudgetType(StrEnum):
    DAILY = "daily"
    LIFETIME = "lifetime"


class CreativeMode(StrEnum):
    """Creative shapes supported in this release.

    ``carousel`` is intentionally absent: see the capability registry. Adding a
    value here without a validator and an execution path would let a plan
    validate and then fail at write time.
    """

    SINGLE_IMAGE = "single_image"
    SINGLE_VIDEO = "single_video"
    EXISTING_POST = "existing_post"
    MULTI_VARIANT = "multi_variant"


class Budget(StrictModel):
    """A budget as a human reads it. Converted to minor units at the boundary."""

    level: BudgetLevel
    type: BudgetType
    amount: Decimal = Field(gt=0, description="Display amount, e.g. 70 for 70.00 PLN")
    currency: CurrencyCode = Field(
        description=(
            "Must match the ad account's currency. The validator compares it "
            "against the account read from Meta - a budget number without a "
            "currency is how a PLN plan becomes a USD charge."
        )
    )

    @field_validator("amount", mode="before")
    @classmethod
    def _no_binary_floats(cls, value: object) -> object:
        # Route floats through str so 0.1 means 0.1. Money does the same.
        return str(value) if isinstance(value, float) else value


class Schedule(StrictModel):
    start: _dt.datetime | None = Field(
        default=None, description="Ad set start. Interpreted in the account timezone."
    )
    end: _dt.datetime | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Schedule:
        if self.start and self.end and (self.start.tzinfo is None) != (self.end.tzinfo is None):
            # Comparing them raises TypeError, which pydantic does not turn
            # into a validation error - validate-plan would crash instead.
            raise ValueError(
                "schedule start and end must both carry a UTC offset, or neither should"
            )
        if self.start and self.end and self.end <= self.start:
            raise ValueError("schedule end must be after start")
        return self


class TargetingPlan(StrictModel):
    """Audience intent.

    Kept close to Meta's own vocabulary without mirroring its whole schema.
    Rich targeting specs pass through ``raw`` so an advanced user is not
    blocked by our model, with the tradeoff that ``raw`` is not validated
    beyond being a mapping.
    """

    countries: list[CountryCode] = Field(min_length=1)
    age_min: int | None = Field(default=None, ge=13, le=65)
    age_max: int | None = Field(default=None, ge=13, le=65)
    genders: Literal["all", "male", "female"] = "all"
    interests: list[str] = Field(default_factory=list)
    custom_audience_ids: list[MetaId] = Field(default_factory=list)
    excluded_custom_audience_ids: list[MetaId] = Field(default_factory=list)
    advantage_audience: bool | None = Field(
        default=None,
        description=(
            "Meta's audience expansion. None means 'leave Meta's default'. "
            "Set explicitly when a hard demographic bound must be respected, "
            "and say so in the plan so the user is not silently enrolled."
        ),
    )
    raw: dict[str, object] = Field(
        default_factory=dict,
        description="Escape hatch merged into the targeting spec. Not validated.",
    )

    @model_validator(mode="after")
    def _age_order(self) -> TargetingPlan:
        if self.age_min and self.age_max and self.age_max < self.age_min:
            raise ValueError(f"age_max ({self.age_max}) is below age_min ({self.age_min})")
        return self


class PlacementPlan(StrictModel):
    """Placement intent.

    ``automatic`` is Meta's default and usually right. Manual placements exist
    because some creative only works in some surfaces, and because the preview
    skill needs to know which placements to render.
    """

    mode: Literal["automatic", "manual"] = "automatic"
    positions: list[str] = Field(
        default_factory=list,
        description="Only with mode=manual, e.g. facebook_feed, instagram_reels",
    )

    @model_validator(mode="after")
    def _manual_needs_positions(self) -> PlacementPlan:
        if self.mode == "manual" and not self.positions:
            raise ValueError("mode=manual requires at least one placement position")
        if self.mode == "automatic" and self.positions:
            raise ValueError(
                "positions are only meaningful with mode=manual; remove them or set mode=manual"
            )
        return self


class TrackingPlan(StrictModel):
    dataset_id: MetaId | None = Field(
        default=None, description="Pixel or dataset id for conversion optimisation"
    )
    conversion_event: MetaEnum | None = Field(
        default=None, description="e.g. PURCHASE, LEAD, COMPLETE_REGISTRATION"
    )
    custom_conversion_id: MetaId | None = None
    attribution_window: str | None = Field(
        default=None,
        description=(
            "Recorded so a later report can say which window its numbers "
            "represent. Never compare periods across different windows."
        ),
    )
    utm: dict[str, str] = Field(default_factory=dict)


class DsaFields(StrictModel):
    """EU Digital Services Act transparency fields.

    First-class, not an afterthought. These identify who paid for an ad and who
    benefits, and they must never be invented. Absent values are resolved from
    brand config or the account's defaults, or the user is asked.
    """

    beneficiary: str | None = None
    payor: str | None = None


class AdvantagePlan(StrictModel):
    """Meta's automatic creative enhancements.

    Surfaced explicitly because Meta may alter a creative after it is created.
    A user should never discover that from a preview. ``None`` means "leave
    Meta's default", which is itself stated in the plan rather than implied.
    """

    enhancements: dict[str, bool] = Field(default_factory=dict)
    note: str | None = None


class CopyVariant(StrictModel):
    """One copy variant.

    ``angle`` is the concept - the reason someone would care. Two variants with
    the same angle and different wording are one idea, not two, and the
    creative skill is required to say so.
    """

    angle: str = Field(min_length=1, description="The distinct concept being tested")
    primary_text: str = Field(min_length=1)
    headline: str | None = None
    description: str | None = None
    cta_type: MetaEnum | None = None


class AssetRef(StrictModel):
    """A creative asset, by local path or by remote id.

    A local path is resolved through the asset manifest: fingerprinted,
    uploaded once, and reused on every later run. A remote id is used as-is.
    """

    local_path: str | None = None
    image_hash: str | None = None
    video_id: MetaId | None = None
    placement: str | None = Field(
        default=None, description="Restrict this asset to one placement, e.g. instagram_stories"
    )

    @model_validator(mode="after")
    def _exactly_one_source(self) -> AssetRef:
        provided = [
            name
            for name, value in (
                ("local_path", self.local_path),
                ("image_hash", self.image_hash),
                ("video_id", self.video_id),
            )
            if value
        ]
        if len(provided) != 1:
            raise ValueError(
                "an asset needs exactly one of local_path, image_hash, or video_id; "
                f"got {provided or 'none'}"
            )
        return self


class CreativePlan(StrictModel):
    mode: CreativeMode
    destination_url: HttpUrl | None = None
    display_link: str | None = None
    page_id: MetaId | None = Field(
        default=None, description="Facebook Page identity. Required for every ad."
    )
    instagram_account_id: MetaId | None = None
    post_id: PostId | None = Field(default=None, description="Only with mode=existing_post")
    assets: list[AssetRef] = Field(default_factory=list)
    variants: list[CopyVariant] = Field(default_factory=list)
    advantage: AdvantagePlan = Field(default_factory=AdvantagePlan)

    @model_validator(mode="after")
    def _mode_requirements(self) -> CreativePlan:
        if self.mode is CreativeMode.EXISTING_POST:
            if not self.post_id:
                raise ValueError("mode=existing_post requires post_id")
            if self.assets or self.variants:
                raise ValueError(
                    "mode=existing_post promotes the post as published; remove "
                    "assets and variants. Supplying them would create a new "
                    "dark post and lose the original post's engagement."
                )
            return self

        if not self.post_id and not self.assets:
            raise ValueError(f"mode={self.mode.value} requires at least one asset")
        if self.post_id:
            raise ValueError(
                f"post_id is only valid with mode=existing_post, not {self.mode.value}"
            )
        if not self.variants:
            raise ValueError(f"mode={self.mode.value} requires at least one copy variant")
        if not self.destination_url:
            raise ValueError(f"mode={self.mode.value} requires a destination_url")

        if self.mode is CreativeMode.SINGLE_IMAGE and any(a.video_id for a in self.assets):
            raise ValueError("mode=single_image cannot use a video asset")
        if self.mode is CreativeMode.SINGLE_VIDEO and not any(
            a.video_id or (a.local_path and _looks_like_video(a.local_path)) for a in self.assets
        ):
            raise ValueError("mode=single_video needs a video asset")
        if self.mode is not CreativeMode.MULTI_VARIANT and len(self.variants) > 1:
            raise ValueError(
                f"mode={self.mode.value} takes one copy variant. Use "
                "mode=multi_variant for several, or plan separate ads."
            )
        return self


def _looks_like_video(path: str) -> bool:
    return path.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"))


class AdPlan(StrictModel):
    name: str = Field(min_length=1)
    creative: CreativePlan
    status: Literal["PAUSED"] = Field(
        default="PAUSED",
        description="Always PAUSED. Activation is a separate approved operation.",
    )


class AdSetPlan(StrictModel):
    name: str = Field(min_length=1)
    optimization_goal: MetaEnum | None = Field(
        default=None,
        description=(
            "Must be valid for the campaign objective. Not checked against a "
            "local list - discover the current pairing with the field-metadata "
            "tool."
        ),
    )
    billing_event: MetaEnum | None = None
    bid_amount: Decimal | None = Field(
        default=None, gt=0, description="Display amount in the plan's currency"
    )
    bid_strategy: MetaEnum | None = None
    budget: Budget | None = Field(
        default=None, description="Omit when the budget is set at campaign level"
    )
    schedule: Schedule = Field(default_factory=Schedule)
    targeting: TargetingPlan
    placements: PlacementPlan = Field(default_factory=PlacementPlan)
    tracking: TrackingPlan = Field(default_factory=TrackingPlan)
    ads: list[AdPlan] = Field(min_length=1)
    status: Literal["PAUSED"] = "PAUSED"

    @model_validator(mode="after")
    def _budget_level(self) -> AdSetPlan:
        if self.budget and self.budget.level is not BudgetLevel.AD_SET:
            raise ValueError(
                "an ad-set budget must declare level=ad_set; a campaign-level "
                "budget belongs on the campaign"
            )
        return self


class CampaignPlan(StrictModel):
    name: str = Field(min_length=1)
    objective: MetaEnum = Field(
        description=(
            "Current Meta objective, e.g. OUTCOME_SALES. Shape-checked only; "
            "the valid set changes with the API version."
        )
    )
    conversion_location: str | None = Field(
        default=None, description="Where the conversion happens, e.g. website, app, messaging"
    )
    buying_type: MetaEnum = "AUCTION"
    budget: Budget | None = Field(
        default=None, description="Present for campaign-level (CBO) budgets only"
    )
    schedule: Schedule = Field(default_factory=Schedule)
    special_ad_categories: list[MetaEnum] = Field(
        default_factory=list,
        description=(
            "Declare when applicable. An empty list asserts none apply, which "
            "is a claim the user is making - not a safe default."
        ),
    )
    dsa: DsaFields = Field(default_factory=DsaFields)
    ad_sets: list[AdSetPlan] = Field(min_length=1)
    status: Literal["PAUSED"] = "PAUSED"

    @model_validator(mode="after")
    def _budget_exactly_one_level(self) -> CampaignPlan:
        if self.budget and self.budget.level is not BudgetLevel.CAMPAIGN:
            raise ValueError(
                "a campaign budget must declare level=campaign; an ad-set "
                "budget belongs on the ad set"
            )
        ad_set_budgets = [a.name for a in self.ad_sets if a.budget]
        if self.budget and ad_set_budgets:
            raise ValueError(
                "budget is set at campaign level and also on ad set(s) "
                f"{ad_set_budgets}. Meta rejects both at once - choose one level."
            )
        if not self.budget and not ad_set_budgets:
            raise ValueError(
                "no budget anywhere. Set one on the campaign (CBO) or on every ad set (ABO)."
            )
        if not self.budget:
            missing = [a.name for a in self.ad_sets if not a.budget]
            if missing:
                raise ValueError(
                    f"ad set(s) {missing} have no budget and the campaign has none either"
                )
        return self

    @model_validator(mode="after")
    def _one_currency(self) -> CampaignPlan:
        currencies = {b.currency for b in self._budgets()}
        if len(currencies) > 1:
            raise ValueError(
                f"plan mixes currencies {sorted(currencies)}. An ad account has "
                "exactly one currency."
            )
        return self

    def _budgets(self) -> list[Budget]:
        budgets = [self.budget] if self.budget else []
        budgets.extend(a.budget for a in self.ad_sets if a.budget)
        return [b for b in budgets if b]

    @property
    def currency(self) -> str | None:
        budgets = self._budgets()
        return budgets[0].currency if budgets else None

    @property
    def budget_level(self) -> BudgetLevel:
        return BudgetLevel.CAMPAIGN if self.budget else BudgetLevel.AD_SET

    def total_ads(self) -> int:
        return sum(len(a.ads) for a in self.ad_sets)


class CampaignPlanDocument(StrictModel):
    """``.meta-ads/campaigns/<slug>/plan.yaml``.

    The wrapper carries the context needed to validate and execute the plan:
    which account, which brand, which offer, and a slug that names the state
    directory. Keeping it separate from :class:`CampaignPlan` means the plan
    itself stays a clean description of the desired structure.
    """

    schema_version: int = 1
    slug: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")] = Field(
        description="Directory-safe identifier for this campaign's workspace"
    )
    created_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    ad_account_id: AccountId
    brand: str | None = Field(default=None, description="Brand name this plan belongs to")
    offer: str | None = Field(default=None, description="Offer slug this plan promotes")
    notes: str | None = None
    campaign: CampaignPlan
