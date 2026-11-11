"""Checks on the account and on campaign-wide obligations: currency, special
ad categories, and EU transparency fields."""

from __future__ import annotations

from meta_ads_agent.errors import CurrencyError
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.money import offset_for
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.validation.report import Severity, ValidationReport

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


def check_account(
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


def check_currency(
    doc: CampaignPlanDocument, account: AccountContext | None, report: ValidationReport
) -> None:
    plan_currency = doc.campaign.currency
    if plan_currency is None:
        return  # the plan model already guarantees a budget exists somewhere

    # Meta's own offset for the account's currency outranks the built-in table
    # (meta_ads_agent.money), so a currency the table lacks is only unknown
    # when the account did not supply one either.
    account_offset = (
        account.currency_offset if account and account.currency == plan_currency else None
    )
    table_offset: int | None = None
    try:
        table_offset = offset_for(plan_currency)
    except CurrencyError as exc:
        if account_offset is None:
            report.add(Severity.ERROR, "currency.unknown_scale", str(exc), "budget.currency")
            return
        report.add(
            Severity.INFO,
            "currency.scale_from_account",
            f"{plan_currency} is not in the built-in currency table; using the "
            f"offset Meta reported for the account ({account_offset}).",
            "budget.currency",
        )

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

    # Only when the two are the same currency: comparing the account's offset
    # with another currency's scale says nothing, and the mismatch is already
    # an error above.
    if account_offset is not None and table_offset is not None and account_offset != table_offset:
        report.add(
            Severity.WARNING,
            "currency.offset_differs",
            f"Meta reports a currency offset of {account_offset} for "
            f"{account.currency}, but the built-in scale for it is "
            f"{table_offset}. Meta's value wins - pass it through "
            "when converting budgets.",
            "budget.currency",
        )


# Special ad category names Meta's ads_create_campaign no longer takes, and what
# its description says to use instead (read 2026-11-11).
RETIRED_SPECIAL_CATEGORIES = {"CREDIT": "FINANCIAL_PRODUCTS_SERVICES"}


def check_special_categories(
    doc: CampaignPlanDocument, brand: BrandConfig | None, report: ValidationReport
) -> None:
    declared = doc.campaign.special_ad_categories
    missing = [c for c in (brand.special_ad_category if brand else []) if c not in declared]
    if missing:
        report.add(
            Severity.ERROR,
            "special_category.not_declared",
            f"brand config declares special ad categories "
            f"{brand.special_ad_category if brand else []} but this plan "
            + (f"declares only {declared}" if declared else "declares none")
            + f" - missing {missing}. "
            "Misdeclaring a special category risks account suspension.",
            "campaign.special_ad_categories",
        )
    retired = sorted(set(declared) & RETIRED_SPECIAL_CATEGORIES.keys())
    if retired:
        report.add(
            Severity.WARNING,
            "special_category.retired",
            "; ".join(
                f"{name} is retired - use {RETIRED_SPECIAL_CATEGORIES[name]}" for name in retired
            )
            + ". From ads_create_campaign's description, read 2026-11-11; Meta's "
            "current list is in ads_get_field_context.",
            "campaign.special_ad_categories",
        )
    if missing:
        return
    if not declared:
        report.add(
            Severity.INFO,
            "special_category.none_declared",
            "the plan asserts no special ad category applies. Confirm that is "
            "true for this offer - credit, employment, housing, social issues, "
            "elections, and politics all require declaration.",
            "campaign.special_ad_categories",
        )


def check_dsa(
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


def check_objective(
    doc: CampaignPlanDocument, account: AccountContext | None, report: ValidationReport
) -> None:
    """The objective belongs to the campaign, so it is reported once."""
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
