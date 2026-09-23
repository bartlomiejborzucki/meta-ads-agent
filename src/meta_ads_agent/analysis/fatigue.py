"""Creative fatigue signals - the arithmetic, not the diagnosis.

The optimise skill's fatigue reference sets out two conditions and a set of
supporting signals. Deciding that an ad *is* fatigued means ruling out the
cheaper explanations (tracking, an edit, the auction, seasonality) and is
the skill's job. Computing the signals is not judgement, and doing it by
hand is where it goes wrong: comparing an ad with a sibling instead of its
own history, averaging CTRs, or quoting frequency from summed daily reach.

For each ad, over daily rows:

* **CTR against its own best earlier window** of the same length, among the
  windows that meet the click floor - never against another ad.
* **Frequency** for the current window, only from a row that covers exactly
  that window (reach is not additive over days); otherwise "not available".
* **Spend since the decline began**: from the start of the first rolling
  window after the baseline whose CTR fell past the threshold and stayed
  there, to the end of the data.
* **Days with delivery** in the data - not "creative age", which the data
  may not reach back to.
* **Siblings** in the same ad set, and whether each held up. If every ad in
  the set declined together, the creative is probably not the variable.

Below the volume floor in either window, an ad gets ``insufficient`` rather
than a number that looks like a finding.
"""

from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from meta_ads_agent.analysis.insights import (
    InsightRow,
    Totals,
    Window,
    daily_rows,
    pct_change,
    window_ending,
)
from meta_ads_agent.errors import ValidationError


@dataclass(frozen=True, slots=True)
class Condition:
    name: str
    value: Decimal | None
    threshold: Decimal | None
    status: str  # met | not_met | unknown

    @classmethod
    def evaluate(
        cls, name: str, value: Decimal | None, threshold: Decimal | None, *, met: bool | None
    ) -> Condition:
        status = "unknown" if met is None else ("met" if met else "not_met")
        return cls(name, value, threshold, status)


@dataclass(slots=True)
class AdFatigue:
    ad_id: str
    ad_name: str | None
    adset_id: str | None
    status: str  # assessed | insufficient
    current: Totals
    baseline: Totals | None
    baseline_window: Window | None
    ctr_change_pct: Decimal | None
    conditions: list[Condition] = field(default_factory=list)
    spend_since_decline: Decimal | None = None
    decline_started: _dt.date | None = None
    days_with_delivery: int = 0
    reason: str | None = None

    @property
    def declined(self) -> bool:
        return any(c.name == "ctr_vs_own_baseline" and c.status == "met" for c in self.conditions)

    @property
    def both_conditions_met(self) -> bool:
        return bool(self.conditions) and all(c.status == "met" for c in self.conditions)


@dataclass(slots=True)
class FatigueReport:
    window: Window
    ads: list[AdFatigue]
    ctr_decline_pct: Decimal
    frequency_ceiling: Decimal | None
    min_clicks: int
    siblings: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def ad(self, ad_id: str) -> AdFatigue:
        return next(a for a in self.ads if a.ad_id == ad_id)


def assess_fatigue(
    rows: list[InsightRow],
    *,
    days: int = 7,
    end: _dt.date | None = None,
    ctr_decline_pct: Decimal | float = 30,
    frequency_ceiling: Decimal | float | None = None,
    min_clicks: int = 500,
) -> FatigueReport:
    ad_rows = [r for r in rows if r.ad_id]
    daily = daily_rows(ad_rows)
    if not daily:
        raise ValidationError(
            "no daily ad-level rows: request insights at level=ad with time_increment=1"
        )
    window = window_ending(end or max(r.date_stop for r in daily), days)
    threshold = Decimal(str(ctr_decline_pct))
    ceiling = None if frequency_ceiling is None else Decimal(str(frequency_ceiling))

    by_ad: dict[str, list[InsightRow]] = defaultdict(list)
    for row in daily:
        by_ad[str(row.ad_id)].append(row)
    covering = {
        str(r.ad_id): r
        for r in ad_rows
        if r.date_start == window.start and r.date_stop == window.end and r.reach
    }

    report = FatigueReport(window, [], threshold, ceiling, min_clicks)
    for ad_id in sorted(by_ad):
        report.ads.append(
            _assess_one(
                ad_id,
                by_ad[ad_id],
                window,
                threshold=threshold,
                ceiling=ceiling,
                min_clicks=min_clicks,
                reach_row=covering.get(ad_id),
            )
        )
    _siblings(report)
    if ceiling is None:
        report.notes.append(
            "NO FREQUENCY CEILING: set thresholds.target_frequency_ceiling in brand.yaml; "
            "until then the frequency condition is unknown, never assumed met"
        )
    if not covering:
        report.notes.append(
            "NO WINDOW REACH: frequency needs one row per ad covering exactly "
            f"{window.start}..{window.end} (no time_increment). Summed daily reach "
            "double-counts people, so it is not used."
        )
    return report


def _assess_one(
    ad_id: str,
    rows: list[InsightRow],
    window: Window,
    *,
    threshold: Decimal,
    ceiling: Decimal | None,
    min_clicks: int,
    reach_row: InsightRow | None,
) -> AdFatigue:
    first = rows[0]
    current = Totals.of(
        [r for r in rows if window.contains(r)], event=None, window_reach_row=reach_row
    )
    delivered = sorted({r.date_start for r in rows if r.impressions > 0})
    result = AdFatigue(
        ad_id=ad_id,
        ad_name=first.ad_name,
        adset_id=first.adset_id,
        status="insufficient",
        current=current,
        baseline=None,
        baseline_window=None,
        ctr_change_pct=None,
        days_with_delivery=len(delivered),
    )

    candidates = _prior_windows(rows, window)
    eligible = [(w, t) for w, t in candidates if t.link_clicks >= min_clicks and t.ctr is not None]
    if current.link_clicks < min_clicks:
        result.reason = (
            f"{current.link_clicks} link clicks in the current window, below the "
            f"{min_clicks}-click floor. CTR at this volume is not measurable."
        )
        return result
    if not eligible:
        result.reason = (
            f"no earlier {window.days}-day window with at least {min_clicks} link clicks "
            "to serve as this ad's own baseline"
        )
        return result

    baseline_window, baseline = max(eligible, key=lambda item: item[1].ctr or Decimal(0))
    change = pct_change(baseline.ctr, current.ctr)
    result.status = "assessed"
    result.baseline, result.baseline_window, result.ctr_change_pct = (
        baseline,
        baseline_window,
        change,
    )

    declined = change is not None and change <= -threshold
    frequency = current.frequency
    result.conditions = [
        Condition.evaluate(
            "frequency",
            frequency,
            ceiling,
            met=None if frequency is None or ceiling is None else frequency > ceiling,
        ),
        Condition.evaluate(
            "ctr_vs_own_baseline", change, -threshold, met=None if change is None else declined
        ),
    ]
    if declined and baseline.ctr is not None:
        start = _decline_start(rows, baseline_window, window, baseline.ctr, threshold)
        if start is not None:
            result.decline_started = start
            result.spend_since_decline = sum(
                (r.spend for r in rows if r.date_start >= start), Decimal(0)
            )
    return result


def _prior_windows(rows: list[InsightRow], window: Window) -> list[tuple[Window, Totals]]:
    """Every same-length window ending before the current one starts."""
    earliest = min(r.date_start for r in rows)
    out: list[tuple[Window, Totals]] = []
    end = window.start - _dt.timedelta(days=1)
    while end - _dt.timedelta(days=window.days - 1) >= earliest:
        candidate = window_ending(end, window.days)
        out.append((candidate, Totals.of([r for r in rows if candidate.contains(r)], event=None)))
        end -= _dt.timedelta(days=1)
    return out


def _decline_start(
    rows: list[InsightRow],
    baseline: Window,
    current: Window,
    baseline_ctr: Decimal,
    threshold: Decimal,
) -> _dt.date | None:
    """Start of the first rolling window after the baseline that fell and stayed fallen."""
    floor = baseline_ctr * (1 - threshold / 100)
    start: _dt.date | None = None
    end = baseline.end + _dt.timedelta(days=current.days)
    while end <= current.end:
        rolling = window_ending(end, current.days)
        ctr = Totals.of([r for r in rows if rolling.contains(r)], event=None).ctr
        fallen = ctr is not None and ctr < floor
        # A recovery resets it: the decline that counts is the one still going.
        start = (start or rolling.start) if fallen else None
        end += _dt.timedelta(days=1)
    return start


def _siblings(report: FatigueReport) -> None:
    by_set: dict[str, list[AdFatigue]] = defaultdict(list)
    for ad in report.ads:
        if ad.adset_id:
            by_set[ad.adset_id].append(ad)
    for adset_id, ads in sorted(by_set.items()):
        assessed = [a for a in ads if a.status == "assessed"]
        report.siblings[adset_id] = {
            "declined": [a.ad_id for a in assessed if a.declined],
            "held_up": [a.ad_id for a in assessed if not a.declined],
            "insufficient": [a.ad_id for a in ads if a.status != "assessed"],
        }
        if len(assessed) > 1 and all(a.declined for a in assessed):
            report.notes.append(
                f"ALL DECLINED in ad set {adset_id}: every assessed ad fell together. "
                "The audience, the auction, tracking or seasonality is the likelier "
                "variable - new creative is unlikely to help."
            )
