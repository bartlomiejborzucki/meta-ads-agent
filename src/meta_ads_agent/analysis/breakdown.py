"""Placement breakdown: what each placement cost against the whole.

The input is insights exported with ``breakdowns=publisher_platform,
platform_position``: one row per placement (per day, or per window). Every
placement's totals are summed and its rates recomputed from the sums, as in
``compare``; then its cost per result - or per link click, when results are
not known - is indexed against the whole at 100.

Readings, per placement:

``cheaper`` / ``costlier``  the index is outside the noise band, on enough
                            volume to say so
``in line``                 within the noise band
``insufficient``            below the volume floor - its index is arithmetic,
                            not information
``unavailable``             no cost to index (no clicks, or no results)

Nothing here says to exclude a placement. Meta optimises delivery across the
placements it is given, so a costlier placement can still be what lets the
cheaper ones work; that is a question for a test, and for the skill (ADR-008).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from decimal import Decimal

from meta_ads_agent.analysis.insights import (
    InsightRow,
    Totals,
    Window,
    actions_reported,
    one_level,
    window_ending,
)
from meta_ads_agent.errors import ValidationError


@dataclass(frozen=True, slots=True)
class PlacementLine:
    publisher_platform: str
    platform_position: str | None
    totals: Totals
    spend_share_pct: Decimal | None
    cost: Decimal | None
    index: Decimal | None
    reading: str

    @property
    def label(self) -> str:
        if self.platform_position:
            return f"{self.publisher_platform} / {self.platform_position}"
        return self.publisher_platform


@dataclass(slots=True)
class Breakdown:
    window: Window
    total: Totals
    cost_metric: str
    placements: list[PlacementLine]
    currency: str | None
    noise_band_pct: Decimal
    min_clicks: int
    min_results: int
    result_event: str | None
    notes: list[str] = field(default_factory=list)


def breakdown_by_placement(
    rows: list[InsightRow],
    *,
    days: int | None = None,
    end: _dt.date | None = None,
    result_event: str | None = None,
    currency: str | None = None,
    noise_band_pct: Decimal | float = Decimal(10),
    min_clicks: int = 500,
    min_results: int = 30,
    level: str | None = None,
) -> Breakdown:
    """Index each placement's cost against the whole, over one window.

    With ``days``, the window is the last ``days`` days ending at ``end``
    (default: the last date in the data); without, every row is used.
    """
    if not rows:
        raise ValidationError("no insights rows")
    unplaced = [r for r in rows if not r.publisher_platform]
    if unplaced:
        raise ValidationError(
            f"{len(unplaced)} of {len(rows)} row(s) have no publisher_platform. Export "
            "with breakdowns=publisher_platform,platform_position, and only those rows: "
            "a row without a placement is the same spend again."
        )
    rows = one_level(rows, level)

    if days is not None:
        window = window_ending(end or max(r.date_stop for r in rows), days)
    else:
        window = Window(min(r.date_start for r in rows), max(r.date_stop for r in rows))
    kept = [r for r in rows if window.contains(r)]
    if not kept:
        raise ValidationError(f"no rows inside {window}")

    reported = actions_reported(kept)
    total = Totals.of(kept, event=result_event, actions_reported=reported)
    use_cpa = result_event is not None and total.results is not None and total.results > 0
    cost_metric = "cpa" if use_cpa else "cpc"
    overall = total.cpa if use_cpa else total.cpc
    band = Decimal(str(noise_band_pct))

    groups: dict[tuple[str, str | None], list[InsightRow]] = {}
    for row in kept:
        key = (str(row.publisher_platform), row.platform_position)
        groups.setdefault(key, []).append(row)

    lines: list[PlacementLine] = []
    for (platform, position), group in groups.items():
        totals = Totals.of(group, event=result_event, actions_reported=reported)
        cost = totals.cpa if use_cpa else totals.cpc
        index = cost / overall * 100 if cost is not None and overall else None
        volume = (totals.results or Decimal(0)) if use_cpa else Decimal(totals.link_clicks)
        floor = min_results if use_cpa else min_clicks
        if index is None:
            reading = "unavailable"
        elif volume < floor:
            reading = "insufficient"
        elif abs(index - 100) < band:
            reading = "in line"
        else:
            reading = "costlier" if index > 100 else "cheaper"
        share = totals.spend / total.spend * 100 if total.spend else None
        lines.append(PlacementLine(platform, position, totals, share, cost, index, reading))
    lines.sort(key=lambda line: (-line.totals.spend, line.label))

    result = Breakdown(
        window=window,
        total=total,
        cost_metric=cost_metric,
        placements=lines,
        currency=currency,
        noise_band_pct=band,
        min_clicks=min_clicks,
        min_results=min_results,
        result_event=result_event,
    )
    if result_event is None:
        result.notes.append(
            "NO RESULT EVENT: placements are indexed on CPC, which says what attention "
            "cost, not what results cost. Pass --result-event for CPA."
        )
    elif not use_cpa:
        result.notes.append(
            f"NO RESULTS for {result_event} in this window: placements are indexed on CPC."
        )
    result.notes.append(
        "Meta optimises delivery across the placements it is given. A costlier "
        "placement may still be what makes the others cheap; removing one is a "
        "change to test, not a conclusion from this table."
    )
    return result
