"""Checks on ad sets: optimisation, tracking, audiences, and naming."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

from meta_ads_agent.models.plan import AdSetPlan, CampaignPlanDocument
from meta_ads_agent.naming import has_placeholders
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.validation.checks_budget import check_bid, check_budgets, check_schedule
from meta_ads_agent.validation.checks_creative import check_creative
from meta_ads_agent.validation.report import Severity, ValidationReport


def check_names_rendered(doc: CampaignPlanDocument, report: ValidationReport) -> None:
    """A name still holding ``{token}`` would reach Meta literally."""
    names = [("campaign.name", doc.campaign.name)]
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        names.append((f"campaign.ad_sets[{index}].name", ad_set.name))
        names.extend(
            (f"campaign.ad_sets[{index}].ads[{ad_index}].name", ad.name)
            for ad_index, ad in enumerate(ad_set.ads)
        )
    for path, name in names:
        if has_placeholders(name):
            report.add(
                Severity.ERROR,
                "naming.unrendered",
                f"{name!r} still contains template tokens. Run "
                "`meta-ads-agent render-plan --write` to expand them from brand.yaml.",
                path,
            )


def check_utm_applied(ad_set: AdSetPlan, prefix: str, report: ValidationReport) -> None:
    """``tracking.utm`` says what the URLs should carry. Check that they do."""
    if not ad_set.tracking.utm:
        return
    wanted = {
        k if k.startswith("utm_") else f"utm_{k}" for k, v in ad_set.tracking.utm.items() if v
    }
    for ad_index, ad in enumerate(ad_set.ads):
        url = ad.creative.destination_url
        if not url:
            continue
        present = {key for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)}
        missing = sorted(wanted - present)
        if missing:
            report.add(
                Severity.WARNING,
                "tracking.utm_not_applied",
                f"tracking.utm names {missing} but the destination URL does not carry "
                "them, so analytics will not see them. Run `meta-ads-agent render-plan "
                "--write`, or add them to the URL.",
                f"{prefix}.ads[{ad_index}].creative.destination_url",
            )


def check_names_unique(doc: CampaignPlanDocument, report: ValidationReport) -> None:
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


def check_ad_set(
    ad_set: AdSetPlan,
    prefix: str,
    doc: CampaignPlanDocument,
    account: AccountContext | None,
    report: ValidationReport,
) -> None:
    check_budgets(ad_set.budget, f"{prefix}.budget", account, report)

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

    check_tracking(ad_set, prefix, account, report)
    check_schedule(ad_set, prefix, report)
    check_bid(ad_set, prefix, doc.campaign.currency, account, report)
    check_audiences(ad_set, prefix, account, report)
    check_utm_applied(ad_set, prefix, report)

    for ad_index, ad in enumerate(ad_set.ads):
        check_creative(ad.creative, f"{prefix}.ads[{ad_index}].creative", account, report)


def check_tracking(
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


def check_audiences(
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
