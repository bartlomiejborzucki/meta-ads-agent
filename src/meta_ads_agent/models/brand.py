"""Brand workspace configuration.

Structured account facts live here. Free-form brand voice lives in
``.meta-ads/voice.md`` and is deliberately *not* modelled: tone is prose, the
creative skill reads it, and the campaign execution layer has no business
caring about it.

Nothing here is required. Every field has a sensible absence, because most of
it is discoverable from Meta and duplicating it invites drift. Configure a
field when you want to pin a default or when Meta cannot tell us (brand voice,
banned phrases, DSA beneficiary).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from meta_ads_agent.models._common import (
    AccountId,
    CountryCode,
    CurrencyCode,
    HttpUrl,
    MetaEnum,
    MetaId,
    StrictModel,
)


class NamingConvention(StrictModel):
    """Templates for generated object names.

    Tokens are substituted at plan time: ``{brand}``, ``{objective}``,
    ``{audience}``, ``{variant}``, ``{offer}``, ``{date}``. Consistent names are
    what make a report groupable later, so the same tokens feed UTM templates.
    """

    campaign: str = "{brand} | {objective} | {date}"
    ad_set: str = "{audience}"
    ad: str = "{variant}"
    date_format: str = "%Y-%m-%d"


class UtmConvention(StrictModel):
    """UTM parameters appended to destination URLs that lack them."""

    source: str = "meta"
    medium: str = "paid_social"
    campaign: str | None = "{offer}_{date}"
    content: str | None = "{variant}"
    term: str | None = None


class DsaDefaults(StrictModel):
    """EU transparency fields.

    Required for advertising reaching the EU. There is no safe way to invent
    these - a wrong beneficiary is a compliance problem, not a typo - so they
    are either configured here, read from the account's defaults, or the user is
    asked. See skills/meta-ads-campaign/references/special-categories-and-dsa.md.
    """

    beneficiary: str | None = None
    payor: str | None = None
    applies_to_eu_delivery: bool = True


class Thresholds(StrictModel):
    """User business rules.

    These are *this advertiser's* policy, not platform constraints and not
    media-buying folklore - the third category in ADR-007. The optimize and
    report skills treat a configured threshold as binding and an unconfigured
    one as absent, never as a default opinion.
    """

    max_cpa_display: float | None = Field(
        default=None, description="Cost per result above which a result is unacceptable"
    )
    min_roas: float | None = None
    target_frequency_ceiling: float | None = Field(
        default=None,
        description="Frequency above which this advertiser considers an audience saturated",
    )
    min_conversions_for_decision: int = Field(
        default=30,
        ge=1,
        description=(
            "Volume floor before a performance comparison is treated as signal. "
            "Below this the honest answer is 'insufficient evidence'."
        ),
    )
    min_clicks_for_decision: int = Field(default=500, ge=1)
    ctr_decline_pct_for_fatigue: float = Field(
        default=30.0,
        gt=0,
        description=(
            "How far CTR must fall below an entity's OWN baseline before "
            "fatigue is one of the candidate explanations. A default, not a law."
        ),
    )


class AccountDefaults(StrictModel):
    """Defaults used to pre-fill a campaign plan.

    Meta remains authoritative for currency and timezone: these are a cache so
    a plan can be drafted before an account read completes, and the validator
    flags a mismatch rather than trusting them.
    """

    ad_account_id: AccountId | None = None
    currency: CurrencyCode | None = None
    timezone: str | None = None
    page_id: MetaId | None = None
    instagram_account_id: MetaId | None = None
    dataset_id: MetaId | None = Field(
        default=None, description="Pixel or dataset id used for conversion optimisation"
    )
    conversion_event: MetaEnum | None = None
    countries: list[CountryCode] = Field(default_factory=list)
    cta_type: MetaEnum | None = None
    objective: MetaEnum | None = None


class BrandConfig(StrictModel):
    """``.meta-ads/brand.yaml``."""

    schema_version: int = 1
    name: str = Field(min_length=1, description="Brand name, used in generated object names")
    website: HttpUrl | None = None
    default_destination_url: HttpUrl | None = None
    one_liner: str | None = Field(
        default=None, max_length=300, description="Fallback positioning line for copy"
    )
    account: AccountDefaults = Field(default_factory=AccountDefaults)
    naming: NamingConvention = Field(default_factory=NamingConvention)
    utm: UtmConvention = Field(default_factory=UtmConvention)
    dsa: DsaDefaults = Field(default_factory=DsaDefaults)
    thresholds: Thresholds = Field(default_factory=Thresholds)

    banned_phrases: list[str] = Field(
        default_factory=list,
        description="Phrases the creative skill must never produce, verbatim",
    )
    claims_policy: str | None = Field(
        default=None,
        description=(
            "What this brand may and may not claim. The creative skill treats "
            "this as binding and never invents supporting evidence."
        ),
    )
    special_ad_category: list[MetaEnum] = Field(
        default_factory=list,
        description=(
            "Declare when this advertiser's ads fall into a Meta special ad "
            "category. Misdeclaring is an account-suspension risk; leaving it "
            "empty is not automatically safe."
        ),
    )
    advantage_defaults: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Default opt-in/out for Meta's automatic creative enhancements. "
            "Surfaced in every plan so the user is never silently enrolled."
        ),
    )
    profile: Annotated[str, Field(pattern="^(conservative|standard|experimental)$")] = "standard"
    notes: str | None = None

    @model_validator(mode="after")
    def _check_destination(self) -> BrandConfig:
        if self.default_destination_url is None and self.website is not None:
            # A website is a reasonable implicit destination, but make it
            # explicit rather than inferring it silently at ad-build time.
            object.__setattr__(self, "default_destination_url", self.website)
        return self


class Offer(StrictModel):
    """``.meta-ads/offers/<slug>.yaml`` - a reusable brief.

    Kept small on purpose. An offer brief that takes twenty minutes to fill in
    does not get filled in.
    """

    schema_version: int = 1
    name: str = Field(min_length=1)
    landing_page: HttpUrl
    audience: str = Field(min_length=1, description="Who this is for, in plain language")
    problem: str = Field(min_length=1, description="The problem it solves")
    outcome: str = Field(min_length=1, description="What changes for the buyer")
    proof: list[str] = Field(
        default_factory=list,
        description=(
            "Evidence that may be used in copy. The creative skill may cite "
            "only what appears here; it must never invent results or numbers."
        ),
    )
    price: str | None = None
    restrictions: list[str] = Field(
        default_factory=list, description="What must not be said or promised"
    )
    cta: MetaEnum | None = None
    creative_notes: str | None = None
