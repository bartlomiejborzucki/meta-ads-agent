"""Checks on money and time: budgets, bids, and schedules."""

from __future__ import annotations

from decimal import Decimal

from meta_ads_agent.errors import CurrencyError
from meta_ads_agent.models.plan import AdSetPlan, Budget, BudgetType, CampaignPlan
from meta_ads_agent.money import Money
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.validation.report import Severity, ValidationReport


def check_budgets(
    budget: Budget | None,
    path: str,
    account: AccountContext | None,
    report: ValidationReport,
) -> None:
    if budget is None:
        return
    try:
        money = Money.from_display(
            budget.amount, budget.currency, offset=_account_offset(account, budget.currency)
        )
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

    minimum = account.min_daily_budget if account else None
    if (
        budget.type is BudgetType.DAILY
        and minimum
        and account
        and account.currency == budget.currency
        and money.minor < minimum
    ):
        floor = Money.from_minor(minimum, budget.currency, offset=money.offset)
        report.add(
            Severity.ERROR,
            "budget.below_minimum",
            f"daily budget {money.format()} is below this account's minimum of "
            f"{floor.format()}, as reported by Meta. The write would be rejected.",
            path,
        )

    report.add(
        Severity.INFO,
        "budget.resolved",
        f"{budget.type.value} budget at {budget.level.value} level: "
        f"{money.format()} ({money.minor} minor units)",
        path,
    )


def check_schedule(ad_set: AdSetPlan, prefix: str, report: ValidationReport) -> None:
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


def check_campaign_schedule(plan: CampaignPlan, report: ValidationReport) -> None:
    """A campaign-level lifetime budget needs an end, as an ad-set one does.

    Meta paces a lifetime budget over a known period. The end can be the
    campaign's own, or every ad set's - but something has to stop it.
    """
    budget = plan.budget
    if not budget or budget.type is not BudgetType.LIFETIME or plan.schedule.end:
        return
    open_ended = [a.name for a in plan.ad_sets if not a.schedule.end]
    if open_ended:
        report.add(
            Severity.ERROR,
            "schedule.lifetime_needs_end",
            "a campaign lifetime budget needs an end time on the campaign, or on "
            f"every ad set; ad set(s) {open_ended} have none",
            "campaign.schedule",
        )


# Bid strategies that cap each auction bid, and so need a bid_amount to cap
# with, and the one that must not be given one. Meta rejects both mistakes.
_STRATEGIES_NEEDING_BID = frozenset({"LOWEST_COST_WITH_BID_CAP", "COST_CAP"})
_STRATEGY_REFUSING_BID = "LOWEST_COST_WITHOUT_CAP"


def check_bid(
    ad_set: AdSetPlan,
    prefix: str,
    currency: str | None,
    account: AccountContext | None,
    report: ValidationReport,
) -> None:
    strategy = ad_set.bid_strategy
    if strategy in _STRATEGIES_NEEDING_BID and ad_set.bid_amount is None:
        report.add(
            Severity.ERROR,
            "bid.amount_missing",
            f"bid strategy {strategy} caps each bid, so it needs a bid_amount",
            f"{prefix}.bid_amount",
        )
    if strategy == _STRATEGY_REFUSING_BID and ad_set.bid_amount is not None:
        report.add(
            Severity.ERROR,
            "bid.amount_not_allowed",
            f"bid strategy {strategy} takes no bid_amount; remove it or choose a capped strategy",
            f"{prefix}.bid_amount",
        )
    if ad_set.bid_amount is None or currency is None:
        return
    # The same arithmetic a budget gets: a bid Meta cannot represent in minor
    # units would be rounded by somebody, and it should not be us, silently.
    try:
        money = Money.from_display(
            Decimal(ad_set.bid_amount), currency, offset=_account_offset(account, currency)
        )
    except CurrencyError as exc:
        report.add(Severity.ERROR, "bid.not_representable", str(exc), f"{prefix}.bid_amount")
        return
    if money.minor <= 0:
        report.add(
            Severity.ERROR,
            "bid.zero",
            f"{ad_set.bid_amount} {currency} rounds to zero minor units",
            f"{prefix}.bid_amount",
        )


def _account_offset(account: AccountContext | None, currency: str) -> int | None:
    """Meta's own minor-unit offset, when it is for this currency."""
    if account and account.currency_offset and account.currency == currency:
        return account.currency_offset
    return None
