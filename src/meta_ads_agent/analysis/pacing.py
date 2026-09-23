"""Budget pacing: what was spent against what the budget allowed.

Numbers only. Whether underspend is a problem (a narrow audience, a low bid
cap, a learning phase) or a relief is a question for the optimise skill,
whose playbook already says that raising a budget that is not being spent is
the most common wasted action. This module makes that visible: utilisation,
the days that spent far under or over the daily figure, and for a lifetime
budget, where spend is heading by the end date.

Meta may spend more than a daily budget on a given day and balances it over
the week, so a single day above the budget is not an error, and nothing here
calls it one. It is reported so a spike that coincides with a budget edit,
or with nothing at all, can be looked at.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from decimal import Decimal

from meta_ads_agent.analysis.insights import InsightRow, Window, daily_rows
from meta_ads_agent.errors import ValidationError


@dataclass(frozen=True, slots=True)
class DaySpend:
    date: _dt.date
    spend: Decimal

    def utilisation(self, daily_budget: Decimal) -> Decimal:
        return self.spend / daily_budget * 100


@dataclass(slots=True)
class DailyPacing:
    budget: Decimal
    currency: str | None
    window: Window
    days: list[DaySpend]
    spend: Decimal
    allowed: Decimal
    notes: list[str] = field(default_factory=list)

    @property
    def utilisation_pct(self) -> Decimal:
        return self.spend / self.allowed * 100 if self.allowed else Decimal(0)

    def days_below(self, pct: Decimal) -> list[DaySpend]:
        return [d for d in self.days if d.utilisation(self.budget) < pct]

    def days_above(self, pct: Decimal) -> list[DaySpend]:
        return [d for d in self.days if d.utilisation(self.budget) > pct]


@dataclass(slots=True)
class LifetimePacing:
    budget: Decimal
    currency: str | None
    start: _dt.date
    end: _dt.date
    as_of: _dt.date
    spend: Decimal
    notes: list[str] = field(default_factory=list)

    @property
    def total_days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def elapsed_days(self) -> int:
        return max(0, min(self.total_days, (self.as_of - self.start).days + 1))

    @property
    def expected_to_date(self) -> Decimal:
        """Straight-line: the share of the budget the elapsed share of days implies."""
        return self.budget * self.elapsed_days / self.total_days

    @property
    def pace_pct(self) -> Decimal | None:
        """Spend so far as a percentage of the straight-line expectation."""
        expected = self.expected_to_date
        return self.spend / expected * 100 if expected else None

    @property
    def projected_total(self) -> Decimal | None:
        """At the current average daily rate, what the budget will have spent by the end."""
        if not self.elapsed_days:
            return None
        return self.spend / self.elapsed_days * self.total_days

    @property
    def remaining(self) -> Decimal:
        return self.budget - self.spend

    @property
    def daily_rate_to_finish(self) -> Decimal | None:
        """What each remaining day would need to spend to use the budget exactly."""
        left = self.total_days - self.elapsed_days
        return self.remaining / left if left > 0 else None


def _spend_by_day(rows: list[InsightRow], window: Window | None = None) -> list[DaySpend]:
    daily = daily_rows(rows)
    if not daily:
        raise ValidationError(
            "no daily rows: request insights with time_increment=1, so each row is one day"
        )
    totals: dict[_dt.date, Decimal] = {}
    for row in daily:
        if window is None or window.contains(row):
            totals[row.date_start] = totals.get(row.date_start, Decimal(0)) + row.spend
    return [DaySpend(day, spend) for day, spend in sorted(totals.items())]


def pace_daily(
    rows: list[InsightRow],
    *,
    daily_budget: Decimal,
    currency: str | None = None,
    start: _dt.date | None = None,
    end: _dt.date | None = None,
) -> DailyPacing:
    """Spend per day against a daily budget, over the days in the data (or a range)."""
    if daily_budget <= 0:
        raise ValidationError("a daily budget must be positive")
    days = _spend_by_day(rows)
    window = Window(start or days[0].date, end or days[-1].date)
    in_window = [d for d in days if window.start <= d.date <= window.end]
    spend = sum((d.spend for d in in_window), Decimal(0))
    result = DailyPacing(
        budget=daily_budget,
        currency=currency,
        window=window,
        days=in_window,
        spend=spend,
        allowed=daily_budget * window.days,
    )
    have = {d.date for d in in_window}
    missing = [d for d in window.dates() if d not in have]
    if missing:
        result.notes.append(
            f"{len(missing)} day(s) in {window} have no spend row (first {missing[0]}). "
            "No row usually means no delivery - worth knowing before reading the average."
        )
    return result


def pace_lifetime(
    rows: list[InsightRow],
    *,
    budget: Decimal,
    start: _dt.date,
    end: _dt.date,
    as_of: _dt.date,
    currency: str | None = None,
) -> LifetimePacing:
    """Spend to date against a lifetime budget's straight-line schedule."""
    if budget <= 0:
        raise ValidationError("a lifetime budget must be positive")
    if end < start:
        raise ValidationError(f"end {end} is before start {start}")
    window = Window(start, min(end, as_of))
    spend = sum((d.spend for d in _spend_by_day(rows, window)), Decimal(0))
    result = LifetimePacing(budget, currency, start, end, as_of, spend)
    if as_of < start:
        result.notes.append(f"as of {as_of} the schedule has not started")
    result.notes.append(
        "Straight-line expectation. Meta does not pace a lifetime budget evenly - "
        "it shifts spend toward days it expects to perform - so a gap is a question, "
        "not a verdict."
    )
    return result
