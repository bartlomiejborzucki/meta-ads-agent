"""Checks on what an ad says, and on how many pieces a creative is made of.

Two different kinds of rule live here, and ADR-007 keeps them apart:

* **The advertiser's own rules.** ``banned_phrases`` in ``brand.yaml`` is a
  list this advertiser wrote. It blocks, because they configured it to.
* **Platform limits** on a multi-variant creative: how many assets and texts
  Meta's ``multi_media`` takes.

There is deliberately no character limit here. Where a placement cuts a line
is read from the preview (``meta-ads-preview``), not from a remembered number.
"""

from __future__ import annotations

from collections.abc import Iterator

from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument, CreativeMode, CreativePlan
from meta_ads_agent.validation.report import Severity, ValidationReport

# What Meta's ads_create_creative documents (tool description read 2026-11-11):
# `multi_media` takes 2 to 10 assets, and up to five variants of each text. One
# asset with several texts is a single image or video with text variants, which
# it accepts under these objectives only.
MULTI_VARIANT_MAX_ASSETS = 10
MULTI_VARIANT_MAX_TEXTS = 5
TEXT_VARIANT_OBJECTIVES = frozenset(
    {"OUTCOME_AWARENESS", "OUTCOME_ENGAGEMENT", "OUTCOME_LEADS", "OUTCOME_SALES"}
)


def check_copy(
    doc: CampaignPlanDocument, brand: BrandConfig | None, report: ValidationReport
) -> None:
    banned = _normalised_phrases(brand.banned_phrases if brand else [])
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        for ad_index, ad in enumerate(ad_set.ads):
            path = f"campaign.ad_sets[{index}].ads[{ad_index}].creative"
            if banned:
                _check_banned(ad.creative, path, banned, report)
            _check_one_asset(ad.creative, path, report)
            if ad.creative.mode is CreativeMode.MULTI_VARIANT:
                _check_multi_variant(ad.creative, path, doc.campaign.objective, report)


def _check_one_asset(creative: CreativePlan, path: str, report: ValidationReport) -> None:
    """A single image or video is one asset.

    A validation error rather than a rule of the model: plans written by
    earlier releases must still load (docs/reference/compatibility.md), and
    those accepted several. They just cannot be built until it is one.
    """
    if creative.mode not in (CreativeMode.SINGLE_IMAGE, CreativeMode.SINGLE_VIDEO):
        return
    if len(creative.assets) <= 1:
        return
    hint = (
        " An image to show before the video plays goes in `thumbnail`."
        if creative.mode is CreativeMode.SINGLE_VIDEO
        else ""
    )
    report.add(
        Severity.ERROR,
        "creative.one_asset",
        f"mode={creative.mode.value} takes one asset, and this lists "
        f"{len(creative.assets)} - nothing says which the ad would show. Use "
        f"mode=multi_variant for several, or plan separate ads.{hint}",
        f"{path}.assets",
    )


def _normalise(text: str) -> str:
    """Case and spacing folded, so "Risk  free" and "risk free" are one phrase."""
    return " ".join(text.casefold().split())


def _normalised_phrases(phrases: list[str]) -> list[tuple[str, str]]:
    """(as written, normalised), skipping blanks - an empty phrase matches everything."""
    return [(p.strip(), _normalise(p)) for p in phrases if p and p.strip()]


def _texts(creative: CreativePlan, path: str) -> Iterator[tuple[str, str]]:
    """Every piece of ad text in a creative, with its path in the plan."""
    for index, variant in enumerate(creative.variants):
        for field in ("primary_text", "headline", "description"):
            value = getattr(variant, field)
            if value:
                yield f"{path}.variants[{index}].{field}", value
    for index, card in enumerate(creative.cards):
        for field in ("headline", "description"):
            value = getattr(card, field)
            if value:
                yield f"{path}.cards[{index}].{field}", value


def _check_banned(
    creative: CreativePlan, path: str, banned: list[tuple[str, str]], report: ValidationReport
) -> None:
    for where, text in _texts(creative, path):
        folded = _normalise(text)
        hits = [written for written, phrase in banned if phrase in folded]
        if hits:
            report.add(
                Severity.ERROR,
                "copy.banned_phrase",
                f"contains {', '.join(repr(h) for h in hits)}, which brand.yaml's "
                "banned_phrases says this brand never uses. Reword it, or change the "
                "list if the rule no longer holds.",
                where,
            )


def _check_multi_variant(
    creative: CreativePlan, path: str, objective: str, report: ValidationReport
) -> None:
    assets = len(creative.assets)
    if assets > MULTI_VARIANT_MAX_ASSETS:
        report.add(
            Severity.ERROR,
            "creative.multi_variant_limits",
            f"{assets} assets; Meta's multi-variant creative takes at most "
            f"{MULTI_VARIANT_MAX_ASSETS}. Split it into two ads.",
            f"{path}.assets",
        )
    for field in ("primary_text", "headline", "description"):
        distinct = {getattr(v, field) for v in creative.variants if getattr(v, field)}
        if len(distinct) > MULTI_VARIANT_MAX_TEXTS:
            report.add(
                Severity.ERROR,
                "creative.multi_variant_limits",
                f"{len(distinct)} different {field} values; Meta's multi-variant creative "
                f"takes at most {MULTI_VARIANT_MAX_TEXTS} of each text. Drop the weakest, "
                "or split it into two ads.",
                f"{path}.variants",
            )
    if assets == 1 and objective not in TEXT_VARIANT_OBJECTIVES:
        texts = max(
            len({getattr(v, f) for v in creative.variants if getattr(v, f)})
            for f in ("primary_text", "headline", "description")
        )
        if texts > 1:
            report.add(
                Severity.WARNING,
                "creative.text_variants_objective",
                f"{texts} text variants on one asset under {objective}. Meta's tool "
                "description (read 2026-11-11) says several text variants on a single image "
                "or video need an Awareness, Engagement, Leads or Sales objective, and that "
                "ads_create_ad rejects others, such as Traffic. Plan one ad per text.",
                f"{path}.variants",
            )
