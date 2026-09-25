"""Name and UTM templates from ``brand.yaml``, applied to a plan.

Consistent names are what let a report group results later, and consistent
UTMs are what let the user's analytics do the same. Both are string templates
with the same tokens, and both were described as "substituted at plan time"
while nothing substituted them - the agent expanded them in prose, so two
campaigns built a week apart could disagree about what ``{date}`` means.

This module is the substitution, and it is strict. An unknown token, or a
token with no value at that level, is an error naming both - never an empty
string quietly left in a name.

Tokens:

``{brand}``      brand name (``brand.yaml``, else the plan's ``brand``)
``{objective}``  the campaign objective
``{offer}``      the plan's ``offer`` slug
``{date}``       the plan's ``created_at``, in ``naming.date_format`` - fixed
                 when the plan is written, so rendering twice gives one answer
``{audience}``   an ad set's targeting as countries and ages, e.g. ``PL 25-55``;
                 in an ad, its ad set's rendered name
``{variant}``    an ad's first copy variant's angle (ads and UTMs only)

A rendered plan is written back to ``plan.yaml`` and is then an ordinary plan:
rendering is idempotent, and names without tokens are left exactly as written.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from meta_ads_agent.errors import ValidationError
from meta_ads_agent.models.brand import BrandConfig, NamingConvention, UtmConvention
from meta_ads_agent.models.plan import AdPlan, AdSetPlan, CampaignPlanDocument, TargetingPlan

TOKENS = ("brand", "objective", "offer", "date", "audience", "variant")

# A `{token}` placeholder, as opposed to literal braces a user might want.
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")

_UTM_FIELDS = ("source", "medium", "campaign", "content", "term")


def has_placeholders(text: str | None) -> bool:
    return bool(text and _PLACEHOLDER.search(text))


def render(template: str, tokens: dict[str, str | None], *, where: str) -> str:
    """Substitute *tokens* into *template*, refusing anything unresolved."""
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        # A lone "{" or "}", or a format spec like {date:%Y}: Python's own
        # message ("Single '{' encountered") would reach the user as a crash.
        raise ValidationError(
            f"{where}: {template!r} is not a valid template ({exc}). Tokens are "
            "written {token}; write a literal brace as {{ or }}."
        ) from exc
    names = [name for _, name, spec, _ in parsed if name is not None]
    specs = [spec for _, name, spec, _ in parsed if name is not None and spec]
    if specs:
        raise ValidationError(
            f"{where}: {template!r} uses a format spec; tokens take none - "
            "{date} follows naming.date_format in brand.yaml"
        )
    unknown = sorted({n for n in names if n not in TOKENS})
    if unknown:
        raise ValidationError(
            f"{where}: unknown token(s) {', '.join('{' + n + '}' for n in unknown)} in "
            f"{template!r}. Known tokens: {', '.join('{' + t + '}' for t in TOKENS)}."
        )
    missing = sorted({n for n in names if not tokens.get(n)})
    if missing:
        raise ValidationError(
            f"{where}: {', '.join('{' + n + '}' for n in missing)} has no value here "
            f"(template {template!r}). Set it in the plan or brand.yaml, or write the "
            "name out in full."
        )
    return template.format(**{n: tokens[n] for n in names})


def audience_label(targeting: TargetingPlan) -> str:
    """``PL 25-55``, ``DE AT 18+``: the part of targeting a name can carry."""
    places = " ".join(targeting.countries) or "worldwide"
    if targeting.age_min and targeting.age_max:
        ages = f"{targeting.age_min}-{targeting.age_max}"
    elif targeting.age_min:
        ages = f"{targeting.age_min}+"
    elif targeting.age_max:
        ages = f"up to {targeting.age_max}"
    else:
        return places
    return f"{places} {ages}"


def with_utm(url: str, params: dict[str, str]) -> str:
    """Append *params* the URL does not already carry. Never overwrites one."""
    parts = urlsplit(url)
    present = {key for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
    missing = [(k, v) for k, v in params.items() if k not in present]
    if not missing:
        return url
    query = f"{parts.query}&{urlencode(missing)}" if parts.query else urlencode(missing)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def utm_params(
    convention: UtmConvention | None,
    overrides: dict[str, str],
    tokens: dict[str, str | None],
    *,
    where: str,
) -> dict[str, str]:
    """``utm_*`` parameters: brand defaults, then the ad set's own ``tracking.utm``.

    Override keys may be written ``source`` or ``utm_source``. An override set
    to an empty string removes that parameter. With no brand config there are
    no defaults: a UTM convention is the user's to choose, not ours.
    """
    templates: dict[str, str | None] = (
        {f"utm_{name}": getattr(convention, name) for name in _UTM_FIELDS} if convention else {}
    )
    for key, value in overrides.items():
        templates[key if key.startswith("utm_") else f"utm_{key}"] = value
    return {
        key: render(value, tokens, where=f"{where} {key}")
        for key, value in templates.items()
        if value
    }


@dataclass(slots=True)
class RenderResult:
    """The rendered plan, and what changed - for showing the user first."""

    document: CampaignPlanDocument
    changes: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def render_plan(doc: CampaignPlanDocument, brand: BrandConfig | None) -> RenderResult:
    """Render every templated name and apply UTMs to every destination URL."""
    rendered = doc.model_copy(deep=True)
    result = RenderResult(rendered)
    naming = brand.naming if brand else NamingConvention()
    utm = brand.utm if brand else None
    base: dict[str, str | None] = {
        "brand": (brand.name if brand else None) or doc.brand,
        "objective": doc.campaign.objective,
        "offer": doc.offer,
        "date": doc.created_at.strftime(naming.date_format),
    }

    campaign = rendered.campaign
    campaign.name = _rename(result, "campaign.name", campaign.name, base)
    for index, ad_set in enumerate(campaign.ad_sets):
        prefix = f"campaign.ad_sets[{index}]"
        set_tokens = {**base, "audience": audience_label(ad_set.targeting)}
        ad_set.name = _rename(result, f"{prefix}.name", ad_set.name, set_tokens)
        for ad_index, ad in enumerate(ad_set.ads):
            where = f"{prefix}.ads[{ad_index}]"
            tokens = {**set_tokens, "audience": ad_set.name, "variant": _variant(ad)}
            ad.name = _rename(result, f"{where}.name", ad.name, tokens)
            _apply_utm(result, ad, ad_set, utm, tokens, where=f"{where}.creative.destination_url")
    # Round-trip through the model, so a rendered value that breaks a
    # constraint (an empty name, a URL no longer valid) fails here, not later.
    result.document = CampaignPlanDocument.model_validate(rendered.model_dump(mode="json"))
    return result


def _rename(result: RenderResult, where: str, name: str, tokens: dict[str, str | None]) -> str:
    if not has_placeholders(name):
        return name
    new = render(name, tokens, where=where)
    result.changes.append((where, name, new))
    return new


def _apply_utm(
    result: RenderResult,
    ad: AdPlan,
    ad_set: AdSetPlan,
    convention: UtmConvention | None,
    tokens: dict[str, str | None],
    *,
    where: str,
) -> None:
    creative = ad.creative
    if not creative.destination_url:
        return  # an existing-post creative keeps the post's own link
    params = utm_params(convention, ad_set.tracking.utm, tokens, where=where)
    new = with_utm(creative.destination_url, params)
    if new != creative.destination_url:
        result.changes.append((where, creative.destination_url, new))
        creative.destination_url = new
    # A carousel card with its own link is a destination too: without this,
    # clicks on those cards reach analytics with no campaign attached.
    base = where.rsplit(".", 1)[0]
    for index, card in enumerate(creative.cards):
        if not card.link:
            continue
        linked = with_utm(card.link, params)
        if linked != card.link:
            result.changes.append((f"{base}.cards[{index}].link", card.link, linked))
            card.link = linked


def _variant(ad: AdPlan) -> str | None:
    variants = ad.creative.variants
    return variants[0].angle if variants else None
