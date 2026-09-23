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

from pathlib import Path

from meta_ads_agent.capabilities import Registry, load_registry
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.validation.checks_account import (
    EU_EEA_COUNTRIES,
    check_account,
    check_currency,
    check_dsa,
    check_objective,
    check_special_categories,
)
from meta_ads_agent.validation.checks_adset import check_ad_set, check_names_unique
from meta_ads_agent.validation.checks_budget import check_budgets, check_campaign_schedule
from meta_ads_agent.validation.checks_creative import check_creative_routing, check_local_assets
from meta_ads_agent.validation.report import Finding, Severity, ValidationReport

__all__ = ["EU_EEA_COUNTRIES", "Finding", "Severity", "ValidationReport", "validate_plan"]


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

    check_account(doc, account, report)
    check_currency(doc, account, report)
    check_objective(doc, account, report)
    check_budgets(plan.budget, "campaign.budget", account, report)
    check_campaign_schedule(plan, report)
    check_special_categories(doc, brand, report)
    check_dsa(doc, brand, report)
    check_names_unique(doc, report)

    for index, ad_set in enumerate(plan.ad_sets):
        prefix = f"campaign.ad_sets[{index}]"
        check_ad_set(ad_set, prefix, doc, account, report)

    check_creative_routing(doc, reg, report)
    if check_assets:
        check_local_assets(doc, asset_base, report)

    return report
