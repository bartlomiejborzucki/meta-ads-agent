"""Checks on money and time: budgets, bids, and schedules."""

from __future__ import annotations

from meta_ads_agent.errors import CurrencyError
from meta_ads_agent.models.plan import AdSetPlan, Budget
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
