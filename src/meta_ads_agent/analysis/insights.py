"""Insight rows as read from Meta, and the sums every comparison is built on.

The input is the Marketing API's documented Insights row: one object per
entity per day (``time_increment=1``), with ``date_start``, ``date_stop``,
``spend``, ``impressions``, ``inline_link_clicks``, ``actions`` and so on. The
official MCP's insights tools return the same metrics; where a response is
shaped differently, the agent reshapes it into these field names rather than
this module guessing at every variant. The accepted shape is documented in
``docs/reference/report-input.md``.

Two rules from the report skill are enforced here, because they are the ones
most easily broken by hand:

* **Rates are recomputed from sums, never averaged.** CTR over five ad sets
  is total link clicks over total impressions, not the mean of five CTRs.
* **Reach does not add up across days.** The same person reached on Monday
  and Tuesday is one person, so a frequency is only reported from a row that
  covers the whole window itself - never from summed daily reach.

Spend is Meta's display amount in the account currency (``"123.45"``), not
minor units; it is kept as a Decimal and never through a float.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from meta_ads_agent.errors import ValidationError


class InsightRow(BaseModel):
    """One row. Unknown fields are ignored: Meta adds fields, we do not model them."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    date_start: _dt.date
    date_stop: _dt.date
    spend: Decimal = Decimal(0)
    impressions: int = 0
    reach: int | None = None
    frequency: Decimal | None = None
    clicks: int | None = Field(default=None, description="Clicks (all). Not used for CTR.")
    link_clicks: int = Field(default=0, alias="inline_link_clicks")
    results: Decimal | None = Field(
        default=None,
        description="Result count for the optimised event, when the agent already has it",
    )
    actions: list[dict[str, Any]] = Field(default_factory=list)
    campaign_id: str | None = None
    adset_id: str | None = None
    ad_id: str | None = None
    campaign_name: str | None = None
    adset_name: str | None = None
    ad_name: str | None = None

    @field_validator("spend", "frequency", "results", mode="before")
    @classmethod
    def _decimal(cls, value: object, info: ValidationInfo) -> object:
        # Meta sends numbers as strings. A float would route 0.1 through binary.
        if value is None or value == "":
            # Meta sends null for a metric with nothing to report. For spend
            # that is zero; for the optional fields it is "not known".
            return Decimal(0) if info.field_name == "spend" else None
        if isinstance(value, float):
            return str(value)
        return value

    @field_validator("impressions", "reach", "clicks", "link_clicks", mode="before")
    @classmethod
    def _count(cls, value: object, info: ValidationInfo) -> object:
        if value is None or value == "":
            return 0 if info.field_name in ("impressions", "link_clicks") else None
        if isinstance(value, str):
            return int(Decimal(value))
        return value

    @model_validator(mode="before")
    @classmethod
    def _link_clicks_alias(cls, data: Any) -> Any:
        # Accept the plainer name as well as Meta's.
        if isinstance(data, dict) and "link_clicks" in data and "inline_link_clicks" not in data:
            data = {**data, "inline_link_clicks": data["link_clicks"]}
        return data

    @model_validator(mode="after")
    def _ordered(self) -> InsightRow:
        if self.date_stop < self.date_start:
            raise ValueError(f"date_stop {self.date_stop} is before date_start {self.date_start}")
        return self

    @property
    def days(self) -> int:
        return (self.date_stop - self.date_start).days + 1

    @property
    def is_daily(self) -> bool:
        return self.date_start == self.date_stop

    def result_count(self, event: str | None) -> Decimal | None:
        """Results for *event*, from ``actions``; or the row's own ``results``.

        ``None`` means "not known" - different from zero, which is a result.
        """
        if event:
            matched = [a for a in self.actions if a.get("action_type") == event]
            if matched:
                return sum((_to_decimal(a.get("value")) for a in matched), Decimal(0))
            return Decimal(0) if self.actions else self.results
        return self.results

    @property
    def level(self) -> str:
        """The most specific entity the row describes: ad, adset, campaign or account."""
        if self.ad_id:
            return "ad"
        if self.adset_id:
            return "adset"
        if self.campaign_id:
            return "campaign"
        return "account"

    def entity(self, level: str) -> str | None:
        return {"campaign": self.campaign_id, "adset": self.adset_id, "ad": self.ad_id}[level]

    def entity_name(self, level: str) -> str | None:
        return {"campaign": self.campaign_name, "adset": self.adset_name, "ad": self.ad_name}[level]


def _to_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"not a number in actions: {value!r}") from exc


def load_rows(source: Path | str | Any) -> list[InsightRow]:
    """Rows from a path, a JSON string, a list, or ``{"data": [...]}``."""
    payload: Any = source
    if isinstance(source, Path):
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValidationError(f"{source} not found") from exc
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{source} is not valid JSON: {exc}") from exc
    elif isinstance(source, str):
        try:
            payload = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"insights input is not valid JSON: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("rows"))
    if not isinstance(payload, list):
        raise ValidationError(
            'insights input must be a list of rows, or {"data": [...]} as Graph returns it'
        )
    rows: list[InsightRow] = []
    for index, raw in enumerate(payload):
        try:
            rows.append(InsightRow.model_validate(raw))
        except Exception as exc:
            raise ValidationError(f"insights row {index} is not usable: {exc}") from exc
    return rows


@dataclass(frozen=True, slots=True)
class Window:
    """An inclusive date range."""

    start: _dt.date
    end: _dt.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, row: InsightRow) -> bool:
        return self.start <= row.date_start and row.date_stop <= self.end

    def dates(self) -> list[_dt.date]:
        return [self.start + _dt.timedelta(days=i) for i in range(self.days)]

    def before(self) -> Window:
        """The equal-length window immediately preceding this one."""
        end = self.start - _dt.timedelta(days=1)
        return Window(end - _dt.timedelta(days=self.days - 1), end)

    def __str__(self) -> str:
        return f"{self.start}..{self.end} ({self.days} day{'s' if self.days != 1 else ''})"


def window_ending(end: _dt.date, days: int) -> Window:
    if days < 1:
        raise ValidationError(f"a window needs at least one day, got {days}")
    return Window(end - _dt.timedelta(days=days - 1), end)


@dataclass(frozen=True, slots=True)
class Totals:
    """Sums over rows, and every rate recomputed from them."""

    spend: Decimal
    impressions: int
    link_clicks: int
    results: Decimal | None
    days_with_data: int
    reach: int | None = None
    window_impressions: int | None = None

    @classmethod
    def of(
        cls,
        rows: Sequence[InsightRow],
        *,
        event: str | None,
        window_reach_row: InsightRow | None = None,
        actions_reported: bool = False,
    ) -> Totals:
        """Sum *rows*.

        ``actions_reported`` says the export carries ``actions`` at all. Meta
        leaves ``actions`` out of a row with no actions that day, so in such an
        export a day without it had zero results - not an unknown number.
        """
        results_known = [
            Decimal(0)
            if (value := r.result_count(event)) is None and event and actions_reported
            else value
            for r in rows
        ]
        results: Decimal | None
        if rows and all(value is not None for value in results_known):
            results = sum((v for v in results_known if v is not None), Decimal(0))
        else:
            results = None
        return cls(
            spend=sum((r.spend for r in rows), Decimal(0)),
            impressions=sum(r.impressions for r in rows),
            link_clicks=sum(r.link_clicks for r in rows),
            results=results,
            days_with_data=len({d for r in rows for d in _dates(r)}),
            reach=window_reach_row.reach if window_reach_row else None,
            window_impressions=window_reach_row.impressions if window_reach_row else None,
        )

    @property
    def ctr(self) -> Decimal | None:
        """Link CTR in percent: link clicks over impressions."""
        return _ratio(self.link_clicks, self.impressions, 100)

    @property
    def cpc(self) -> Decimal | None:
        return _ratio(self.spend, self.link_clicks)

    @property
    def cpm(self) -> Decimal | None:
        return _ratio(self.spend, self.impressions, 1000)

    @property
    def cvr(self) -> Decimal | None:
        if self.results is None:
            return None
        return _ratio(self.results, self.link_clicks, 100)

    @property
    def cpa(self) -> Decimal | None:
        if self.results is None:
            return None
        return _ratio(self.spend, self.results)

    @property
    def frequency(self) -> Decimal | None:
        """Only from a row covering the window; summed daily reach double-counts.

        The covering row's own impressions are used, so a day missing from the
        daily rows cannot make the frequency look lower than it was.
        """
        if not self.reach:
            return None
        return _ratio(self.window_impressions or self.impressions, self.reach)


def _ratio(
    numerator: Decimal | int, denominator: Decimal | int | None, scale: int = 1
) -> Decimal | None:
    if not denominator:
        return None
    return Decimal(numerator) * scale / Decimal(denominator)


def _dates(row: InsightRow) -> Iterable[_dt.date]:
    return (row.date_start + _dt.timedelta(days=i) for i in range(row.days))


def daily_rows(rows: Iterable[InsightRow]) -> list[InsightRow]:
    return [r for r in rows if r.is_daily]


LEVELS = ("ad", "adset", "campaign", "account")


def one_level(rows: Sequence[InsightRow], level: str | None = None) -> list[InsightRow]:
    """The rows of a single level, so nothing is counted twice.

    An export holding a campaign's rows *and* its ad sets' rows describes the
    same spend twice; summing both doubles it. With *level* given, only rows
    of that level are kept. Without it, a single-level export passes as is,
    and a mixed one is refused with the levels it contains.
    """
    if level is not None:
        if level not in LEVELS:
            raise ValidationError(f"level must be one of {', '.join(LEVELS)}, got {level!r}")
        kept = [r for r in rows if r.level == level]
        if not kept:
            raise ValidationError(f"no {level}-level rows in the input")
        return kept
    present = sorted({r.level for r in rows}, key=LEVELS.index)
    if len(present) > 1:
        raise ValidationError(
            f"the input mixes {', '.join(present)} rows, which would count the same "
            "spend more than once. Pass --level to choose one, or export one level."
        )
    return list(rows)


def actions_reported(rows: Iterable[InsightRow]) -> bool:
    return any(r.actions or r.results is not None for r in rows)


def pct_change(before: Decimal | None, after: Decimal | None) -> Decimal | None:
    """Percentage change, or None from a zero or unknown baseline."""
    if before is None or after is None or before == 0:
        return None
    return (after - before) / before * 100
