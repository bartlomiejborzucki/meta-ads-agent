"""Validate a campaign plan before any mutation begins.

Scope discipline (ADR-007): this validator enforces **platform constraints**
only - things Meta rejects, or that make an ad undeliverable. It does not
enforce media-buying opinions. A plan that is unusual but valid produces
warnings at most, and still executes.

Everything that could make a write fail halfway is checked here, because a
half-built campaign is the expensive failure. "Ambiguous required field" is an
error, not a warning: better to ask than to create three objects and stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from meta_ads_agent.capabilities import Provider, Registry, load_registry
from meta_ads_agent.errors import CapabilityError, CurrencyError
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import (
    AdSetPlan,
    Budget,
    CampaignPlanDocument,
    CreativeMode,
)
from meta_ads_agent.money import Money, offset_for
from meta_ads_agent.state.assets import AssetKind, probe_asset
from meta_ads_agent.validation.account import AccountContext

# EU/EEA country codes. EU transparency (DSA) fields apply to ads delivered
# here, so a plan targeting any of them needs a beneficiary and payor.
EU_EEA_COUNTRIES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
        "IS",
        "LI",
        "NO",
    }
)

# Creative modes that need the API fallback. Derived from the capability
# registry at validation time, but mapped here because the plan speaks in modes
# and the registry speaks in capabilities.
_MODE_CAPABILITY: dict[CreativeMode, str] = {
    CreativeMode.SINGLE_IMAGE: "create_single_image_creative",
    CreativeMode.SINGLE_VIDEO: "create_video_creative",
    CreativeMode.EXISTING_POST: "create_existing_post_creative",
    CreativeMode.MULTI_VARIANT: "create_multi_variant_creative",
}


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation result.

    ``code`` is stable and greppable so a skill can reference a specific check
    and tests can assert on it without matching prose.
    """

    severity: Severity
    code: str
    message: str
    path: str = ""

    def __str__(self) -> str:
        where = f" [{self.path}]" if self.path else ""
        return f"{self.severity.value.upper()}: {self.code}{where}: {self.message}"


@dataclass(slots=True)
class ValidationReport:
    """The outcome of validating one plan."""

    findings: list[Finding] = field(default_factory=list)
    providers_used: dict[str, str] = field(default_factory=dict)

    def add(self, severity: Severity, code: str, message: str, path: str = "") -> None:
        self.findings.append(Finding(severity, code, message, path))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def ok(self) -> bool:
        """True when no error blocks execution. Warnings do not block."""
        return not self.errors

    @property
    def uses_fallback(self) -> bool:
        return Provider.API_FALLBACK.value in self.providers_used.values()

    def render(self) -> str:
        if not self.findings:
            return "Plan is valid. No findings."
        lines = [str(f) for f in sorted(self.findings, key=lambda f: (f.severity, f.code))]
        verdict = "VALID" if self.ok else "BLOCKED"
        summary = (
            f"{verdict}: {len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s), {len(self.infos)} note(s)"
        )
        return "\n".join([*lines, "", summary])


def validate_plan(
    doc: CampaignPlanDocument,
    *,
    account: AccountContext | None = None,
    brand: BrandConfig | None = None,
    registry: Registry | None = None,
    asset_base: Path | str | None = None,
    check_assets: bool = True,
) -> ValidationReport:
    """Validate *doc* against platform constraints and the account's reality.

    ``account`` is what the agent read from Meta. Without it the currency,
    identity, and dataset checks cannot run, and the report says so - a plan
    validated with no account context is not a plan cleared for execution.
    """
    report = ValidationReport()
    reg = registry or load_registry()
    plan = doc.campaign

    _check_account(doc, account, report)
    _check_currency(doc, account, report)
    _check_budgets(plan.budget, "campaign.budget", account, report)
    _check_special_categories(doc, brand, report)
    _check_dsa(doc, brand, report)
    _check_names_unique(doc, report)

    for index, ad_set in enumerate(plan.ad_sets):
        prefix = f"campaign.ad_sets[{index}]"
        _check_ad_set(ad_set, prefix, doc, account, report)

    _check_creative_routing(doc, reg, report)
    if check_assets:
        _check_assets(doc, asset_base, report)

    return report


# -- account -----------------------------------------------------------------
def _check_account(
    doc: CampaignPlanDocument, account: AccountContext | None, report: ValidationReport
) -> None:
    if account is None:
        report.add(
            Severity.WARNING,
            "account.not_read",
            "No account context supplied, so currency, identity, dataset, and "
            "eligibility checks were skipped. Read the ad account from Meta and "
            "re-validate before creating anything.",
        )
        return

    if account.id != doc.ad_account_id:
        report.add(
            Severity.ERROR,
            "account.mismatch",
            f"plan targets {doc.ad_account_id} but the supplied account context "
            f"is for {account.id}",
            "ad_account_id",
        )

    if account.is_active is False:
        report.add(
            Severity.ERROR,
            "account.not_active",
            f"account status is {account.account_status}"
            + (f" (disable_reason {account.disable_reason})" if account.disable_reason else "")
            + ". Writes will fail or the ads will not deliver.",
        )
    if account.is_queryable is False:
        report.add(
            Severity.ERROR, "account.not_queryable", "Meta reports this account is not queryable"
        )
    if account.is_ads_mcp_enabled is False:
        report.add(
            Severity.WARNING,
            "account.mcp_not_enabled",
            "Meta reports this account is not enabled for the Ads MCP. Access is "
            "rolling out gradually; MCP writes may be rejected.",
        )
    if account.has_payment_method is False:
        report.add(
            Severity.ERROR,
            "account.no_payment_method",
            "the account has no payment method. Objects can be created but the "
            "ads will never deliver, which is a confusing failure to debug later.",
        )
    if not account.timezone_name:
        report.add(
            Severity.WARNING,
            "account.timezone_unknown",
            "account timezone is unknown, so schedule times and daily-budget "
            "boundaries cannot be interpreted with confidence",
        )


def _check_currency(
    doc: CampaignPlanDocument, account: AccountContext | None, report: ValidationReport
) -> None:
    plan_currency = doc.campaign.currency
    if plan_currency is None:
        return  # the plan model already guarantees a budget exists somewhere

    try:
        offset_for(plan_currency)
    except CurrencyError as exc:
        report.add(Severity.ERROR, "currency.unknown_scale", str(exc), "budget.currency")
        return

    if account is None or account.currency is None:
        report.add(
            Severity.WARNING,
            "currency.unverified",
            f"plan budgets are in {plan_currency}, which was not verified against "
            "the account. A budget in the wrong currency is a silent overspend.",
            "budget.currency",
        )
        return

    if account.currency != plan_currency:
        report.add(
            Severity.ERROR,
            "currency.mismatch",
            f"plan budgets are in {plan_currency} but the account bills in "
            f"{account.currency}. Meta interprets budgets in the account's "
            "currency, so this would spend the wrong amount.",
            "budget.currency",
        )

    if account.currency_offset is not None and account.currency_offset != offset_for(plan_currency):
        report.add(
            Severity.WARNING,
            "currency.offset_differs",
            f"Meta reports a currency offset of {account.currency_offset} for "
            f"{account.currency}, but the ISO minor-unit scale is "
            f"{offset_for(plan_currency)}. Meta's value wins - pass it through "
            "when converting budgets.",
            "budget.currency",
        )


def _check_budgets(
    budget: Budget | None,
    path: str,
    account: AccountContext | None,
    report: ValidationReport,
) -> None:
    if budget is None:
        return
    offset = (
        account.currency_offset
        if account and account.currency_offset and account.currency == budget.currency
        else None
    )
    try:
        money = Money.from_display(budget.amount, budget.currency, offset=offset)
    except CurrencyError as exc:
        report.add(Severity.ERROR, "budget.not_representable", str(exc), path)
        return

    if money.minor <= 0:
        report.add(
            Severity.ERROR,
            "budget.zero",
            f"{budget.amount} {budget.currency} rounds to zero minor units",
            path,
        )
        return

    report.add(
        Severity.INFO,
        "budget.resolved",
        f"{budget.type.value} budget at {budget.level.value} level: "
        f"{money.format()} ({money.minor} minor units)",
        path,
    )


def _check_special_categories(
    doc: CampaignPlanDocument, brand: BrandConfig | None, report: ValidationReport
) -> None:
    declared = doc.campaign.special_ad_categories
    if brand and brand.special_ad_category and not declared:
        report.add(
            Severity.ERROR,
            "special_category.not_declared",
            f"brand config declares special ad categories "
            f"{brand.special_ad_category} but this plan declares none. "
            "Misdeclaring a special category risks account suspension.",
            "campaign.special_ad_categories",
        )
    elif not declared:
        report.add(
            Severity.INFO,
            "special_category.none_declared",
            "the plan asserts no special ad category applies. Confirm that is "
            "true for this offer - credit, employment, housing, social issues, "
            "elections, and politics all require declaration.",
            "campaign.special_ad_categories",
        )


def _check_dsa(
    doc: CampaignPlanDocument, brand: BrandConfig | None, report: ValidationReport
) -> None:
    targeted = {
        country for ad_set in doc.campaign.ad_sets for country in ad_set.targeting.countries
    }
    eu_targeted = sorted(targeted & EU_EEA_COUNTRIES)
    if not eu_targeted:
        return

    beneficiary = doc.campaign.dsa.beneficiary or (brand.dsa.beneficiary if brand else None)
    payor = doc.campaign.dsa.payor or (brand.dsa.payor if brand else None)

    missing = [
        name for name, value in (("beneficiary", beneficiary), ("payor", payor)) if not value
    ]
    if missing:
        report.add(
            Severity.ERROR,
            "dsa.missing_fields",
            f"targeting {', '.join(eu_targeted)} requires EU transparency "
            f"field(s) {', '.join(missing)}. These name who paid for the ad and "
            "who benefits - they must come from the advertiser or the account's "
            "defaults, never be invented.",
            "campaign.dsa",
        )
    else:
        report.add(
            Severity.INFO,
            "dsa.present",
            f"EU delivery to {', '.join(eu_targeted)} with beneficiary "
            f"{beneficiary!r} and payor {payor!r}",
            "campaign.dsa",
        )


def _check_names_unique(doc: CampaignPlanDocument, report: ValidationReport) -> None:
    """Duplicate names are legal on Meta but make later reporting ambiguous."""
    ad_set_names = [a.name for a in doc.campaign.ad_sets]
    duplicates = {n for n in ad_set_names if ad_set_names.count(n) > 1}
    if duplicates:
        report.add(
            Severity.WARNING,
            "naming.duplicate_ad_sets",
            f"ad set name(s) {sorted(duplicates)} appear more than once. Meta "
            "allows it, but a later report cannot tell them apart.",
            "campaign.ad_sets",
        )
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        ad_names = [a.name for a in ad_set.ads]
        dupes = {n for n in ad_names if ad_names.count(n) > 1}
        if dupes:
            report.add(
                Severity.WARNING,
                "naming.duplicate_ads",
                f"ad name(s) {sorted(dupes)} repeat within this ad set",
                f"campaign.ad_sets[{index}].ads",
            )


# -- ad set ------------------------------------------------------------------
def _check_ad_set(
    ad_set: AdSetPlan,
    prefix: str,
    doc: CampaignPlanDocument,
    account: AccountContext | None,
    report: ValidationReport,
) -> None:
    _check_budgets(ad_set.budget, f"{prefix}.budget", account, report)

    if account and account.valid_optimization_goals and ad_set.optimization_goal:
        if ad_set.optimization_goal not in account.valid_optimization_goals:
            report.add(
                Severity.ERROR,
                "optimization_goal.invalid",
                f"{ad_set.optimization_goal} is not in the optimization goals "
                f"discovered for objective {doc.campaign.objective}",
                f"{prefix}.optimization_goal",
            )
    elif not ad_set.optimization_goal:
        report.add(
            Severity.WARNING,
            "optimization_goal.absent",
            "no optimization goal set, so Meta will pick a default. State it "
            "explicitly - the default may not match the objective's intent.",
            f"{prefix}.optimization_goal",
        )

    if (
        account
        and account.valid_objectives
        and doc.campaign.objective not in account.valid_objectives
    ):
        report.add(
            Severity.ERROR,
            "objective.invalid",
            f"{doc.campaign.objective} is not among the objectives discovered "
            f"for this account: {sorted(account.valid_objectives)}",
            "campaign.objective",
        )

    _check_tracking(ad_set, prefix, account, report)
    _check_schedule(ad_set, prefix, report)
    _check_audiences(ad_set, prefix, account, report)

    for ad_index, ad in enumerate(ad_set.ads):
        _check_creative(ad.creative, f"{prefix}.ads[{ad_index}].creative", account, report)


def _check_tracking(
    ad_set: AdSetPlan, prefix: str, account: AccountContext | None, report: ValidationReport
) -> None:
    tracking = ad_set.tracking
    goal = (ad_set.optimization_goal or "").upper()
    # Shape-based rather than an enum list: any goal mentioning conversions or
    # values needs a signal source, whatever Meta calls it this version.
    needs_dataset = bool(
        tracking.conversion_event
        or tracking.custom_conversion_id
        or "CONVERSION" in goal
        or "VALUE" in goal
    )

    if needs_dataset and not (tracking.dataset_id or tracking.custom_conversion_id):
        report.add(
            Severity.ERROR,
            "tracking.dataset_missing",
            "this ad set optimises for conversions but names no pixel/dataset "
            "or custom conversion. Meta cannot optimise against a signal it "
            "cannot see.",
            f"{prefix}.tracking",
        )

    if (
        tracking.dataset_id
        and account
        and account.available_dataset_ids
        and tracking.dataset_id not in account.available_dataset_ids
    ):
        report.add(
            Severity.ERROR,
            "tracking.dataset_unknown",
            f"dataset {tracking.dataset_id} was not found on this account",
            f"{prefix}.tracking.dataset_id",
        )

    if (
        tracking.conversion_event
        and account
        and account.available_conversion_events
        and tracking.conversion_event not in account.available_conversion_events
    ):
        report.add(
            Severity.WARNING,
            "tracking.event_not_seen",
            f"the account has not recently received a {tracking.conversion_event} "
            "event. Optimising for an event with no volume will not deliver. "
            "Check dataset stats before launching.",
            f"{prefix}.tracking.conversion_event",
        )

    if not tracking.attribution_window:
        report.add(
            Severity.INFO,
            "tracking.attribution_unset",
            "no attribution window recorded, so Meta's account default applies. "
            "Recording it lets a later report state which window its numbers "
            "represent.",
            f"{prefix}.tracking",
        )


def _check_schedule(ad_set: AdSetPlan, prefix: str, report: ValidationReport) -> None:
    budget = ad_set.budget
    if budget and budget.type.value == "lifetime":
        if not (ad_set.schedule.end or ad_set.schedule.start):
            report.add(
                Severity.ERROR,
                "schedule.lifetime_needs_end",
                "a lifetime budget needs a schedule; Meta cannot pace spend "
                "over an open-ended period",
                f"{prefix}.schedule",
            )
        elif not ad_set.schedule.end:
            report.add(
                Severity.ERROR,
                "schedule.lifetime_needs_end",
                "a lifetime budget needs an end time",
                f"{prefix}.schedule",
            )


def _check_audiences(
    ad_set: AdSetPlan, prefix: str, account: AccountContext | None, report: ValidationReport
) -> None:
    targeting = ad_set.targeting
    overlap = set(targeting.custom_audience_ids) & set(targeting.excluded_custom_audience_ids)
    if overlap:
        report.add(
            Severity.ERROR,
            "targeting.audience_included_and_excluded",
            f"audience(s) {sorted(overlap)} are both included and excluded, "
            "which leaves nobody to reach",
            f"{prefix}.targeting",
        )

    if account and account.available_custom_audience_ids:
        known = set(account.available_custom_audience_ids)
        unknown = sorted(
            set(targeting.custom_audience_ids + targeting.excluded_custom_audience_ids) - known
        )
        if unknown:
            report.add(
                Severity.ERROR,
                "targeting.audience_unknown",
                f"custom audience(s) {unknown} were not found on this account",
                f"{prefix}.targeting",
            )

    if targeting.advantage_audience is None and (
        targeting.age_min or targeting.age_max or targeting.interests
    ):
        report.add(
            Severity.INFO,
            "targeting.advantage_audience_unset",
            "age, gender, or interest constraints are set but advantage_audience "
            "is unspecified, so Meta's default applies and may expand beyond "
            "them. Set it explicitly if the bounds must hold.",
            f"{prefix}.targeting.advantage_audience",
        )


# -- creative ----------------------------------------------------------------
def _check_creative(creative, path: str, account: AccountContext | None, report) -> None:  # type: ignore[no-untyped-def]
    if not creative.page_id:
        report.add(
            Severity.ERROR,
            "creative.page_missing",
            "every ad needs a Facebook Page identity and none is set here or "
            "resolvable from brand config",
            f"{path}.page_id",
        )
    elif (
        account
        and account.available_page_ids
        and creative.page_id not in account.available_page_ids
    ):
        report.add(
            Severity.ERROR,
            "creative.page_unknown",
            f"Page {creative.page_id} is not among the Pages available to this account",
            f"{path}.page_id",
        )

    if (
        creative.instagram_account_id
        and account
        and account.available_instagram_account_ids
        and creative.instagram_account_id not in account.available_instagram_account_ids
    ):
        report.add(
            Severity.ERROR,
            "creative.instagram_unknown",
            f"Instagram account {creative.instagram_account_id} is not linked to this ad account",
            f"{path}.instagram_account_id",
        )

    if creative.destination_url:
        _check_destination(creative.destination_url, f"{path}.destination_url", report)

    if (
        account
        and account.valid_call_to_action_types
        and (cta_types := [v.cta_type for v in creative.variants if v.cta_type])
    ):
        invalid = sorted({c for c in cta_types if c not in account.valid_call_to_action_types})
        if invalid:
            report.add(
                Severity.ERROR,
                "creative.cta_invalid",
                f"call-to-action type(s) {invalid} are not valid for this "
                "objective according to the discovered field metadata",
                f"{path}.variants",
            )

    angles = [v.angle.strip().lower() for v in creative.variants]
    if len(angles) > 1 and len(set(angles)) == 1:
        report.add(
            Severity.WARNING,
            "creative.angles_not_distinct",
            f"all {len(angles)} variants share the angle {angles[0]!r}. Wording "
            "changes on one idea are one test, not several - label them honestly "
            "or give them genuinely different angles.",
            f"{path}.variants",
        )

    if creative.advantage.enhancements:
        enabled = sorted(k for k, v in creative.advantage.enhancements.items() if v)
        disabled = sorted(k for k, v in creative.advantage.enhancements.items() if not v)
        report.add(
            Severity.INFO,
            "creative.advantage_declared",
            "Meta automatic enhancements - enabled: "
            f"{enabled or 'none'}; disabled: {disabled or 'none'}. Anything not "
            "listed follows Meta's default and may alter the creative.",
            f"{path}.advantage",
        )
    else:
        report.add(
            Severity.INFO,
            "creative.advantage_default",
            "no automatic-enhancement preferences declared, so Meta's defaults "
            "apply and the delivered creative may differ from the preview. "
            "Declare them in brand config to make this explicit.",
            f"{path}.advantage",
        )


def _check_destination(url: str, path: str, report: ValidationReport) -> None:
    parts = urlsplit(url)
    if parts.scheme == "http":
        report.add(
            Severity.WARNING,
            "destination.not_https",
            f"{url} is plain http. Expect browser warnings and worse conversion "
            "rates; Meta may also restrict it.",
            path,
        )
    if parts.hostname and parts.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        report.add(
            Severity.ERROR,
            "destination.not_public",
            f"{url} points at localhost, which no ad viewer can reach",
            path,
        )
    if parts.hostname and "." not in parts.hostname:
        report.add(
            Severity.ERROR,
            "destination.no_public_host",
            f"{url} has no public hostname",
            path,
        )
    if any(token in url for token in ("{{", "}}", "<", ">")):
        report.add(
            Severity.ERROR,
            "destination.unresolved_template",
            f"{url} still contains template placeholders",
            path,
        )


# -- routing and assets ------------------------------------------------------
def _check_creative_routing(
    doc: CampaignPlanDocument, registry: Registry, report: ValidationReport
) -> None:
    """Resolve each creative mode to a provider, and say so.

    Recording the provider is what lets the agent explain, truthfully, that a
    step used the fallback because Meta's MCP does not expose the capability.
    """
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        for ad_index, ad in enumerate(ad_set.ads):
            path = f"campaign.ad_sets[{index}].ads[{ad_index}].creative"
            capability = _MODE_CAPABILITY[ad.creative.mode]
            try:
                route = registry.route(capability)
            except CapabilityError as exc:
                report.add(
                    Severity.ERROR,
                    "creative.mode_unsupported",
                    str(exc),
                    f"{path}.mode",
                )
                continue
            report.providers_used[capability] = route.provider.value
            if route.uses_fallback:
                report.add(
                    Severity.INFO,
                    "routing.fallback",
                    f"creative mode {ad.creative.mode.value} will use the Meta "
                    f"Business SDK fallback ({route.cli}) because Meta's "
                    "official Ads MCP does not currently expose it.",
                    path,
                )

    local_paths = [
        asset.local_path
        for ad_set in doc.campaign.ad_sets
        for ad in ad_set.ads
        for asset in ad.creative.assets
        if asset.local_path
    ]
    if local_paths:
        # Route only the kinds actually present, so the report does not claim a
        # video upload will happen for an image-only plan.
        needed = set()
        for local_path in local_paths:
            needed.add(
                "local_video_upload" if _looks_like_video_path(local_path) else "local_image_upload"
            )
        for capability in sorted(needed):
            route = registry.route(capability)
            report.providers_used[capability] = route.provider.value
        report.add(
            Severity.INFO,
            "routing.local_upload",
            "the plan references local files, so upload runs through the Meta "
            "Business SDK fallback - Meta's official Ads MCP lists uploaded "
            "media but has no local-file ingestion tool. Uploads are "
            "deduplicated by content fingerprint.",
        )


def _looks_like_video_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _check_assets(
    doc: CampaignPlanDocument, asset_base: Path | str | None, report: ValidationReport
) -> None:
    base = Path(asset_base) if asset_base else Path.cwd()
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        for ad_index, ad in enumerate(ad_set.ads):
            creative = ad.creative
            for asset_index, asset in enumerate(creative.assets):
                path = f"campaign.ad_sets[{index}].ads[{ad_index}].creative.assets[{asset_index}]"
                if not asset.local_path:
                    continue
                expected = AssetKind.VIDEO if creative.mode is CreativeMode.SINGLE_VIDEO else None
                resolved = Path(asset.local_path).expanduser()
                if not resolved.is_absolute():
                    resolved = base / resolved
                try:
                    probe = probe_asset(resolved, kind=expected)
                except Exception as exc:
                    report.add(Severity.ERROR, "asset.unusable", str(exc), path)
                    continue
                report.add(
                    Severity.INFO,
                    "asset.ok",
                    f"{probe.kind.value} {resolved.name}: {probe.size_bytes} bytes"
                    + (f", {probe.width}x{probe.height}" if probe.width else "")
                    + (f", {probe.duration_seconds:.1f}s" if probe.duration_seconds else "")
                    + f", {probe.fingerprint[:19]}...",
                    path,
                )
                for warning in probe.warnings:
                    report.add(Severity.WARNING, "asset.warning", warning, path)
