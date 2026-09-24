"""``meta-ads-agent report compare|fatigue|pacing`` - insights arithmetic.

Read-only and offline. The agent reads insights through the official MCP,
saves them as JSON, and hands the file here; this prints the numbers the
report and optimise skills then interpret. Thresholds come from brand.yaml
when there is one, and every threshold used is printed next to the result,
so a reader can see which rule produced which label.

Exit codes:
  0  computed
  2  the input could not be read, or the options do not make sense together
"""

from __future__ import annotations

import datetime as _dt
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from meta_ads_agent.analysis import (
    assess_fatigue,
    compare_periods,
    load_rows,
    pace_daily,
    pace_lifetime,
)
from meta_ads_agent.analysis.compare import Comparison
from meta_ads_agent.analysis.fatigue import FatigueReport
from meta_ads_agent.analysis.insights import InsightRow, Totals
from meta_ads_agent.analysis.pacing import DailyPacing, LifetimePacing
from meta_ads_agent.cli.output import echo, emit_json, fail, heading
from meta_ads_agent.cli.validate_cmd import load_brand
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.models.brand import Thresholds
from meta_ads_agent.workspace import Workspace


def _thresholds(brand_path: str | None) -> Thresholds:
    brand = load_brand(brand_path, Workspace.locate(required=False))
    return brand.thresholds if brand else Thresholds()


def _rows(path: str) -> list[InsightRow] | None:
    try:
        return load_rows(Path(path).expanduser())
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return None


def _q(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return "n/a"
    return str(value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _num(value: Decimal | None, places: int = 4) -> str | None:
    """JSON numbers as strings: exact, and never re-parsed through a float."""
    return None if value is None else _q(value, places)


def _money(value: Decimal | None, currency: str | None) -> str:
    return _q(value) + (f" {currency}" if currency and value is not None else "")


# -- compare -----------------------------------------------------------------
def run_compare(
    path: str,
    *,
    days: int,
    end: _dt.date | None,
    boundary: _dt.date | None,
    result_event: str | None,
    currency: str | None,
    attribution_days: int | None,
    brand_path: str | None,
    as_json: bool,
) -> int:
    rows = _rows(path)
    if rows is None:
        return 2
    t = _thresholds(brand_path)
    try:
        result = compare_periods(
            rows,
            days=days,
            end=end,
            boundary=boundary,
            result_event=result_event,
            currency=currency,
            noise_band_pct=Decimal(str(t.noise_band_pct)),
            min_clicks=t.min_clicks_for_decision,
            min_results=t.min_conversions_for_decision,
            attribution_days=attribution_days,
        )
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    if as_json:
        emit_json(_comparison_json(result))
        return 0

    heading("Period comparison")
    echo(f"  previous  {result.previous_window}")
    echo(f"  current   {result.current_window}")
    echo(
        f"  rules     noise band {_q(result.noise_band_pct, 1)}%, floors "
        f"{result.min_clicks} link clicks / {result.min_results} results"
        + (f", results = {result.result_event}" if result.result_event else "")
    )
    echo("")
    echo(f"  {'metric':<12} {'previous':>14} {'current':>14} {'change':>9}  reading")
    for change in result.changes.values():
        places = 0 if change.metric in ("impressions", "link_clicks") else 2
        echo(
            f"  {change.metric:<12} {_q(change.previous, places):>14} "
            f"{_q(change.current, places):>14} "
            f"{(_q(change.pct, 1) + '%') if change.pct is not None else 'n/a':>9}  "
            f"{change.classification}"
        )
    if currency:
        echo(f"  (spend, CPC, CPM and CPA in {currency}; CTR and CVR in percent)", "dim")
    if result.chain:
        echo("")
        echo(f"  chain     {result.chain}")
    for note in result.notes:
        echo(f"  ! {note}", "yellow")
    return 0


def _totals_json(totals: Totals) -> dict[str, Any]:
    return {
        "spend": _num(totals.spend, 2),
        "impressions": totals.impressions,
        "link_clicks": totals.link_clicks,
        "results": _num(totals.results, 2),
        "ctr_pct": _num(totals.ctr),
        "cpc": _num(totals.cpc),
        "cpm": _num(totals.cpm),
        "cvr_pct": _num(totals.cvr),
        "cpa": _num(totals.cpa),
        "frequency": _num(totals.frequency),
        "days_with_data": totals.days_with_data,
    }


def _comparison_json(result: Comparison) -> dict[str, Any]:
    return {
        "previous_window": {
            "start": str(result.previous_window.start),
            "end": str(result.previous_window.end),
        },
        "current_window": {
            "start": str(result.current_window.start),
            "end": str(result.current_window.end),
        },
        "currency": result.currency,
        "result_event": result.result_event,
        "rules": {
            "noise_band_pct": _num(result.noise_band_pct, 2),
            "min_link_clicks": result.min_clicks,
            "min_results": result.min_results,
        },
        "previous": _totals_json(result.previous),
        "current": _totals_json(result.current),
        "changes": {
            name: {
                "previous": _num(c.previous),
                "current": _num(c.current),
                "pct": _num(c.pct, 2),
                "classification": c.classification,
                "direction": c.direction,
            }
            for name, c in result.changes.items()
        },
        "chain": result.chain,
        "comparable": result.comparable,
        "notes": result.notes,
    }


# -- fatigue -----------------------------------------------------------------
def run_fatigue(
    path: str,
    *,
    days: int,
    end: _dt.date | None,
    currency: str | None,
    brand_path: str | None,
    as_json: bool,
) -> int:
    rows = _rows(path)
    if rows is None:
        return 2
    t = _thresholds(brand_path)
    try:
        report = assess_fatigue(
            rows,
            days=days,
            end=end,
            ctr_decline_pct=Decimal(str(t.ctr_decline_pct_for_fatigue)),
            frequency_ceiling=(
                Decimal(str(t.target_frequency_ceiling)) if t.target_frequency_ceiling else None
            ),
            min_clicks=t.min_clicks_for_decision,
        )
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    if as_json:
        emit_json(_fatigue_json(report, currency))
        return 0

    heading(f"Fatigue signals, current window {report.window}")
    echo(
        f"  rules     CTR decline {_q(report.ctr_decline_pct, 0)}% vs the ad's own best "
        f"earlier window; frequency ceiling "
        f"{_q(report.frequency_ceiling, 1) if report.frequency_ceiling else 'not set'}; "
        f"floor {report.min_clicks} link clicks per window"
    )
    for ad in report.ads:
        echo("")
        echo(f"  ad {ad.ad_id}" + (f"  {ad.ad_name!r}" if ad.ad_name else ""))
        if ad.status != "assessed":
            echo(f"    INSUFFICIENT EVIDENCE - {ad.reason}", "yellow")
            continue
        echo(
            f"    CTR       {_q(ad.current.ctr)}% now, "
            f"{_q(ad.baseline.ctr if ad.baseline else None)}%"
            f" in its best prior window ({ad.baseline_window}), "
            f"{_q(ad.ctr_change_pct, 1)}%"
        )
        for condition in ad.conditions:
            echo(
                f"    {condition.name:<21} {_q(condition.value, 2):>8}  {condition.status.upper()}"
            )
        if ad.decline_started:
            echo(
                f"    spend since decline  {_money(ad.spend_since_decline, currency)} "
                f"from {ad.decline_started}"
            )
        echo(f"    days with delivery   {ad.days_with_delivery} in the data")
    for adset_id, group in report.siblings.items():
        echo("")
        echo(
            f"  ad set {adset_id}: declined {group['declined'] or 'none'}, "
            f"held up {group['held_up'] or 'none'}"
        )
    for note in report.notes:
        echo(f"  ! {note}", "yellow")
    return 0


def _fatigue_json(report: FatigueReport, currency: str | None) -> dict[str, Any]:
    return {
        "window": {"start": str(report.window.start), "end": str(report.window.end)},
        "currency": currency,
        "rules": {
            "ctr_decline_pct": _num(report.ctr_decline_pct, 2),
            "frequency_ceiling": _num(report.frequency_ceiling, 2),
            "min_link_clicks": report.min_clicks,
        },
        "ads": [
            {
                "ad_id": ad.ad_id,
                "ad_name": ad.ad_name,
                "adset_id": ad.adset_id,
                "status": ad.status,
                "reason": ad.reason,
                "current": _totals_json(ad.current),
                "baseline": _totals_json(ad.baseline) if ad.baseline else None,
                "baseline_window": (
                    {"start": str(ad.baseline_window.start), "end": str(ad.baseline_window.end)}
                    if ad.baseline_window
                    else None
                ),
                "ctr_change_pct": _num(ad.ctr_change_pct, 2),
                "conditions": {
                    c.name: {
                        "value": _num(c.value),
                        "threshold": _num(c.threshold),
                        "status": c.status,
                    }
                    for c in ad.conditions
                },
                "spend_since_decline": _num(ad.spend_since_decline, 2),
                "decline_started": str(ad.decline_started) if ad.decline_started else None,
                "days_with_delivery": ad.days_with_delivery,
            }
            for ad in report.ads
        ],
        "siblings": report.siblings,
        "notes": report.notes,
    }


# -- pacing ------------------------------------------------------------------
def run_pacing(
    path: str,
    *,
    daily_budget: Decimal | None,
    lifetime_budget: Decimal | None,
    start: _dt.date | None,
    end: _dt.date | None,
    as_of: _dt.date | None,
    currency: str | None,
    as_json: bool,
) -> int:
    if (daily_budget is None) == (lifetime_budget is None):
        fail("give exactly one of --daily-budget or --lifetime-budget")
        return 2
    rows = _rows(path)
    if rows is None:
        return 2
    try:
        if daily_budget is not None:
            daily = pace_daily(
                rows, daily_budget=daily_budget, currency=currency, start=start, end=end
            )
            return _print_daily(daily, as_json)
        if start is None or end is None:
            fail("a lifetime budget needs --start and --end, the schedule it is paced over")
            return 2
        assert lifetime_budget is not None
        lifetime = pace_lifetime(
            rows,
            budget=lifetime_budget,
            start=start,
            end=end,
            as_of=as_of or max(r.date_stop for r in rows),
            currency=currency,
        )
        return _print_lifetime(lifetime, as_json)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2


# Reported, not judged: a day at half its budget, or well over it, is worth a
# look and nothing more. Meta may overspend a daily budget on some days.
_LOW_DAY_PCT = Decimal(50)
_HIGH_DAY_PCT = Decimal(150)


def _print_daily(p: DailyPacing, as_json: bool) -> int:
    low, high = p.days_below(_LOW_DAY_PCT), p.days_above(_HIGH_DAY_PCT)
    if as_json:
        emit_json(
            {
                "kind": "daily",
                "currency": p.currency,
                "window": {"start": str(p.window.start), "end": str(p.window.end)},
                "daily_budget": _num(p.budget, 2),
                "spend": _num(p.spend, 2),
                "allowed": _num(p.allowed, 2),
                "utilisation_pct": _num(p.utilisation_pct, 2),
                "days": [
                    {
                        "date": str(d.date),
                        "spend": _num(d.spend, 2),
                        "utilisation_pct": _num(d.utilisation(p.budget), 2),
                    }
                    for d in p.days
                ],
                "days_below_50_pct": [str(d.date) for d in low],
                "days_above_150_pct": [str(d.date) for d in high],
                "notes": p.notes,
            }
        )
        return 0
    heading(f"Daily budget pacing, {p.window}")
    echo(f"  budget       {_money(p.budget, p.currency)} per day")
    echo(f"  spent        {_money(p.spend, p.currency)} of {_money(p.allowed, p.currency)}")
    echo(f"  utilisation  {_q(p.utilisation_pct, 1)}%")
    if low:
        echo(f"  under 50%    {', '.join(str(d.date) for d in low)}")
    if high:
        echo(f"  over 150%    {', '.join(str(d.date) for d in high)}")
    for note in p.notes:
        echo(f"  ! {note}", "yellow")
    return 0


def _print_lifetime(p: LifetimePacing, as_json: bool) -> int:
    if as_json:
        emit_json(
            {
                "kind": "lifetime",
                "currency": p.currency,
                "budget": _num(p.budget, 2),
                "schedule": {"start": str(p.start), "end": str(p.end)},
                "as_of": str(p.as_of),
                "elapsed_days": p.elapsed_days,
                "total_days": p.total_days,
                "spend": _num(p.spend, 2),
                "expected_to_date": _num(p.expected_to_date, 2),
                "pace_pct": _num(p.pace_pct, 2),
                "projected_total": _num(p.projected_total, 2),
                "remaining": _num(p.remaining, 2),
                "daily_rate_to_finish": _num(p.daily_rate_to_finish, 2),
                "notes": p.notes,
            }
        )
        return 0
    heading(f"Lifetime budget pacing, as of {p.as_of}")
    echo(f"  budget        {_money(p.budget, p.currency)}, {p.start}..{p.end}")
    echo(f"  elapsed       {p.elapsed_days} of {p.total_days} day(s)")
    echo(f"  spent         {_money(p.spend, p.currency)}")
    echo(f"  expected      {_money(p.expected_to_date, p.currency)} on a straight line")
    echo(f"  pace          {_q(p.pace_pct, 1)}% of expected")
    echo(f"  projected     {_money(p.projected_total, p.currency)} by {p.end} at the current rate")
    echo(f"  to finish     {_money(p.daily_rate_to_finish, p.currency)} per remaining day")
    for note in p.notes:
        echo(f"  ! {note}", "yellow")
    return 0


# -- power -------------------------------------------------------------------
def run_power(
    *,
    baseline_rate: float,
    units_per_day: float,
    cells: int,
    days: float | None,
    lift: float | None,
    alpha: float,
    power: float,
    as_json: bool,
) -> int:
    from meta_ads_agent.analysis.power import (
        PowerInputs,
        days_needed,
        minimum_detectable_lift,
        sample_size_per_cell,
    )

    try:
        inputs = PowerInputs(baseline_rate, units_per_day, cells, alpha, power)
        if days is not None:
            detectable = minimum_detectable_lift(inputs, days)
            per_cell = sample_size_per_cell(inputs, detectable) if detectable else None
            needed = None
        else:
            assert lift is not None
            detectable = None
            per_cell = sample_size_per_cell(inputs, lift)
            needed = days_needed(inputs, lift)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    rules = {
        "baseline_rate": baseline_rate,
        "units_per_day_per_cell": units_per_day,
        "cells": cells,
        "alpha": alpha,
        "alpha_per_comparison": inputs.adjusted_alpha,
        "power": power,
    }
    if as_json:
        emit_json(
            {
                "rules": rules,
                "days": days,
                "minimum_detectable_lift": detectable,
                "lift": lift,
                "days_needed": needed,
                "units_per_cell": per_cell,
                "answerable": days is None or detectable is not None,
            }
        )
        return 0

    heading("Test power")
    echo(
        f"  inputs    baseline {baseline_rate:.2%}, {units_per_day:g} units/day/cell, "
        f"{cells} cells, alpha {alpha:g}"
        + (f" ({inputs.adjusted_alpha:.4f} per comparison)" if cells > 2 else "")
        + f", power {power:g}"
    )
    if days is not None:
        if detectable is None:
            echo(f"  {days:g} days cannot detect even a doubling of the rate.", "yellow")
            echo("  A test this size would not answer anything worth acting on.")
        else:
            echo(f"  in {days:g} days it can detect a lift of {detectable:+.1%} or more")
            echo(f"            ({per_cell} units per cell)")
    else:
        assert lift is not None and needed is not None
        echo(f"  to detect {lift:+.1%} it needs {per_cell} units per cell: {needed:.1f} days")
    echo(
        "  Meta's own test reports its own confidence; this is for deciding whether to run one.",
        "dim",
    )
    return 0
