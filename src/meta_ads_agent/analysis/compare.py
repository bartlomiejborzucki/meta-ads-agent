"""Period comparison: equal windows, sums not averages, noise and volume stated.

What the report skill described in prose and the model computed by hand,
now arithmetic in one place (ADR-008). The module decides nothing about
*why* a metric moved. It says, per metric: the two values, the change, and
whether the change clears the noise band on enough volume to be treated as
signal. The chain CPM x CTR -> CPC / CVR -> CPA is then read off those
classifications into the specific next question the skill documents - which
is a rule table, not a judgement, so it lives here too.

Classifications:

``signal``        beyond the noise band, and both windows meet the volume floor
``noise``         within the noise band
``insufficient``  below a volume floor in either window - a change here is
                  arithmetic, not information
``observed``      a count (spend, impressions): shown, never "signal", because a
                  count moving is a fact rather than an estimate of anything
``unavailable``   no value in one window (no results event, no clicks, ...)
"""

from __future__ import annotations

import datetime as _dt
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

# The report reference's default: "10-15% on a rate metric is a reasonable
# default. It is a default, not a law." The low end, so fewer real changes
# are dismissed as noise; brand.yaml overrides it.
DEFAULT_NOISE_BAND_PCT = Decimal(10)

# Which floor protects which metric. Click-based rates need clicks; anything
# with results in it needs results.
_CLICK_METRICS = ("ctr", "cpc")
_RESULT_METRICS = ("results", "cvr", "cpa")
_COUNT_METRICS = ("spend", "impressions", "link_clicks")
_RATE_METRICS = ("cpm", *_CLICK_METRICS, *_RESULT_METRICS)
METRICS = (*_COUNT_METRICS, *_RATE_METRICS)


@dataclass(frozen=True, slots=True)
class MetricChange:
    metric: str
    previous: Decimal | None
    current: Decimal | None
    pct: Decimal | None
    classification: str

    @property
    def direction(self) -> str:
        """``up``, ``down`` or ``flat`` - flat unless the change is signal."""
        if self.classification != "signal" or self.pct is None:
            return "flat"
        return "up" if self.pct > 0 else "down"


@dataclass(slots=True)
class Comparison:
    current_window: Window
    previous_window: Window
    current: Totals
    previous: Totals
    changes: dict[str, MetricChange]
    currency: str | None
    noise_band_pct: Decimal
    min_clicks: int
    min_results: int
    result_event: str | None
    notes: list[str] = field(default_factory=list)
    chain: str | None = None

    @property
    def comparable(self) -> bool:
        """False when a window is missing days of data - the comparison is unfair."""
        return not any(n.startswith("INCOMPLETE") for n in self.notes)


def compare_periods(
    rows: list[InsightRow],
    *,
    days: int | None = None,
    end: _dt.date | None = None,
    boundary: _dt.date | None = None,
    result_event: str | None = None,
    currency: str | None = None,
    noise_band_pct: Decimal | float = DEFAULT_NOISE_BAND_PCT,
    min_clicks: int = 500,
    min_results: int = 30,
    attribution_days: int | None = None,
    as_of: _dt.date | None = None,
) -> Comparison:
    """Compare two equal-length windows of daily rows.

    Either ``days`` ending at ``end`` (default: the last date in the data), or
    ``days`` starting at ``boundary`` - the day a known change happened, so
    before and after actually mean something.
    """
    daily = daily_rows(rows)
    if not daily:
        raise ValidationError(
            "no daily rows: request insights with time_increment=1, so each row is one day"
        )
    if days is None or days < 1:
        raise ValidationError("say how long each window is, e.g. --days 7")

    if boundary is not None:
        current = Window(boundary, boundary + _dt.timedelta(days=days - 1))
    else:
        current = window_ending(end or max(r.date_stop for r in daily), days)
    previous = current.before()

    band = Decimal(str(noise_band_pct))
    now = Totals.of([r for r in daily if current.contains(r)], event=result_event)
    before = Totals.of([r for r in daily if previous.contains(r)], event=result_event)

    changes = {
        metric: _change(
            metric, before, now, band=band, min_clicks=min_clicks, min_results=min_results
        )
        for metric in METRICS
    }
    result = Comparison(
        current_window=current,
        previous_window=previous,
        current=now,
        previous=before,
        changes=changes,
        currency=currency,
        noise_band_pct=band,
        min_clicks=min_clicks,
        min_results=min_results,
        result_event=result_event,
    )
    _coverage_notes(result, daily)
    _attribution_notes(result, attribution_days=attribution_days, as_of=as_of)
    if result_event is None:
        result.notes.append(
            "NO RESULT EVENT: results, CVR and CPA need --result-event naming the "
            "optimised action type; they are reported unavailable, not zero"
        )
    result.chain = read_chain(changes)
    return result


def _change(
    metric: str,
    before: Totals,
    now: Totals,
    *,
    band: Decimal,
    min_clicks: int,
    min_results: int,
) -> MetricChange:
    previous, current = _value(before, metric), _value(now, metric)
    pct = pct_change(previous, current)
    if metric in _COUNT_METRICS:
        classification = "observed"
    elif previous is None or current is None or pct is None:
        classification = "unavailable"
    elif (metric in _CLICK_METRICS and min(before.link_clicks, now.link_clicks) < min_clicks) or (
        metric in _RESULT_METRICS and min(before.results or 0, now.results or 0) < min_results
    ):
        classification = "insufficient"
    elif abs(pct) < band:
        classification = "noise"
    else:
        classification = "signal"
    return MetricChange(metric, previous, current, pct, classification)


def _value(totals: Totals, metric: str) -> Decimal | None:
    value = getattr(totals, metric)
    return None if value is None else Decimal(value)


def _coverage_notes(result: Comparison, daily: list[InsightRow]) -> None:
    """A window with missing days is the first thing that makes a comparison unfair."""
    have = {r.date_start for r in daily}
    for label, window in (("current", result.current_window), ("previous", result.previous_window)):
        missing = [d for d in window.dates() if d not in have]
        if missing:
            result.notes.append(
                f"INCOMPLETE {label} window {window}: no data for {len(missing)} of "
                f"{window.days} day(s) (first missing {missing[0]}). An entity live for "
                "part of a period, or a partial export, makes the comparison unfair."
            )
    # Per entity: live in one window but not the other.
    entities = {r.ad_id or r.adset_id or r.campaign_id for r in daily} - {None}
    for entity in sorted(e for e in entities if e):
        mine = {r.date_start for r in daily if entity in (r.ad_id, r.adset_id, r.campaign_id)}
        now_days = sum(1 for d in result.current_window.dates() if d in mine)
        before_days = sum(1 for d in result.previous_window.dates() if d in mine)
        if now_days != before_days:
            result.notes.append(
                f"UNEVEN entity {entity}: data on {before_days} day(s) before and "
                f"{now_days} after. Its share of the totals changed for a reason "
                "that is not performance."
            )


def _attribution_notes(
    result: Comparison, *, attribution_days: int | None, as_of: _dt.date | None
) -> None:
    if attribution_days is None:
        result.notes.append(
            "ATTRIBUTION NOT STATED: say which window these numbers use; never "
            "compare across different windows"
        )
        return
    today = as_of or _dt.date.today()
    open_days = (result.current_window.end - (today - _dt.timedelta(days=attribution_days))).days
    if open_days >= 0:
        result.notes.append(
            f"RECENT: the last {min(open_days + 1, result.current_window.days)} day(s) of the "
            f"current window are inside the {attribution_days}-day attribution window as of "
            f"{today}. Conversions are still arriving, so results and CPA understate."
        )


# The chain from the report reference. Each rule is read off the directions
# of the metrics that are signal; a metric that is not signal counts as flat.
_CHAIN_RULES: tuple[tuple[dict[str, str], str], ...] = (
    (
        {"cpa": "up", "cvr": "flat", "cpc": "up"},
        "CPA up with CVR flat and CPC up: the problem is upstream of the page.",
    ),
    (
        {"cpc": "up", "ctr": "flat", "cpm": "up"},
        "CPC up with CTR flat and CPM up: the auction got more expensive, not the creative worse.",
    ),
    (
        {"cpc": "up", "cpm": "flat", "ctr": "down"},
        "CPC up with CPM flat and CTR down: the creative is losing attention.",
    ),
    (
        {"cpa": "up", "cpc": "flat", "cvr": "down"},
        "CPA up with CPC flat and CVR down: the page, the offer, the audience "
        "quality, or tracking.",
    ),
)


def read_chain(changes: dict[str, MetricChange]) -> str | None:
    """The next question the metric chain points to, if a documented rule matches."""
    directions = {name: change.direction for name, change in changes.items()}
    matched = [
        text for rule, text in _CHAIN_RULES if all(directions.get(k) == v for k, v in rule.items())
    ]
    return " ".join(matched) or None
