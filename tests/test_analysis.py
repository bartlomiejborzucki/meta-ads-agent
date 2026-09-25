"""Insights arithmetic: comparisons, fatigue signals, pacing.

Synthetic daily rows, built so each expected number can be worked out by
hand from the row generator below. Nothing here reaches Meta.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest

from meta_ads_agent.analysis import (
    assess_fatigue,
    compare_periods,
    load_rows,
    pace_daily,
    pace_lifetime,
)
from meta_ads_agent.analysis.insights import InsightRow, Totals
from meta_ads_agent.cli.main import main
from meta_ads_agent.errors import ValidationError

START = dt.date(2026, 9, 1)
LEAD = "offsite_conversion.fb_pixel_lead"


def day(n: int) -> dt.date:
    return START + dt.timedelta(days=n)


def row(
    n: int,
    *,
    spend: str = "100",
    impressions: int = 10000,
    clicks: int = 100,
    leads: int | None = 5,
    ad: str | None = "ad-a",
    adset: str | None = "set-1",
) -> dict[str, object]:
    out: dict[str, object] = {
        "date_start": str(day(n)),
        "date_stop": str(day(n)),
        "spend": spend,
        "impressions": str(impressions),
        "inline_link_clicks": str(clicks),
        "ad_id": ad,
        "adset_id": adset,
    }
    if leads is not None:
        out["actions"] = [{"action_type": LEAD, "value": str(leads)}]
    return out


def rows(raw: list[dict[str, object]]) -> list[InsightRow]:
    return load_rows(raw)


class TestInput:
    def test_graph_shape_and_string_numbers_are_read(self) -> None:
        (parsed,) = load_rows({"data": [row(0)]})
        assert parsed.spend == Decimal("100")
        assert parsed.impressions == 10000
        assert parsed.link_clicks == 100
        assert parsed.result_count(LEAD) == Decimal(5)

    def test_an_event_absent_from_actions_is_zero_not_unknown(self) -> None:
        (parsed,) = load_rows([row(0)])
        assert parsed.result_count("purchase") == 0

    def test_no_actions_at_all_is_unknown_not_zero(self) -> None:
        (parsed,) = load_rows([row(0, leads=None)])
        assert parsed.result_count(LEAD) is None

    def test_a_bad_row_names_its_index(self) -> None:
        with pytest.raises(ValidationError, match="row 1"):
            load_rows([row(0), {"date_start": "not a date", "date_stop": "2026-09-01"}])

    def test_rates_come_from_sums_not_from_averaging_rates(self) -> None:
        # 1% CTR on 100 impressions and 3% on 10,000: the mean says 2%, the
        # truth is (1 + 300) / 10,100.
        small = InsightRow.model_validate(row(0, impressions=100, clicks=1))
        large = InsightRow.model_validate(row(0, impressions=10000, clicks=300))
        ctr = Totals.of([small, large], event=None).ctr
        assert ctr is not None
        assert round(ctr, 4) == round(Decimal(301) / Decimal(10100) * 100, 4)
        assert round(ctr, 2) != Decimal("2.00")


class TestCompare:
    def test_windows_are_equal_length_and_adjacent(self) -> None:
        result = compare_periods(rows([row(n) for n in range(14)]), days=7, result_event=LEAD)
        assert (result.previous_window.start, result.previous_window.end) == (day(0), day(6))
        assert (result.current_window.start, result.current_window.end) == (day(7), day(13))

    def test_a_boundary_aligns_the_windows_to_a_change(self) -> None:
        result = compare_periods(rows([row(n) for n in range(20)]), days=5, boundary=day(10))
        assert result.previous_window.start == day(5)
        assert result.current_window.start == day(10)

    def test_a_small_move_is_noise(self) -> None:
        raw = [row(n) for n in range(7)] + [row(n, clicks=105) for n in range(7, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.changes["ctr"].classification == "noise"

    def test_a_large_move_on_enough_volume_is_signal(self) -> None:
        # 1,400 then 840 link clicks: both windows clear the 500-click floor.
        raw = [row(n, clicks=200) for n in range(7)] + [row(n, clicks=120) for n in range(7, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        change = result.changes["ctr"]
        assert change.classification == "signal"
        assert change.pct == Decimal(-40)
        assert change.direction == "down"

    def test_the_same_move_below_the_volume_floor_is_insufficient(self) -> None:
        raw = [row(n, clicks=10) for n in range(7)] + [row(n, clicks=6) for n in range(7, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.changes["ctr"].classification == "insufficient"
        # 35 leads per window clears the 30-result floor; CPA is measurable.
        assert result.changes["cpa"].classification != "insufficient"

    def test_without_a_result_event_results_are_unavailable_not_zero(self) -> None:
        result = compare_periods(rows([row(n) for n in range(14)]), days=7)
        assert result.changes["cpa"].classification == "unavailable"
        assert any(n.startswith("NO RESULT EVENT") for n in result.notes)

    def test_counts_are_observed_never_signal(self) -> None:
        raw = [row(n) for n in range(7)] + [row(n, spend="300") for n in range(7, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.changes["spend"].classification == "observed"
        assert result.changes["spend"].pct == Decimal(200)

    def test_the_chain_names_the_creative_when_ctr_falls_and_cpm_holds(self) -> None:
        raw = [row(n, clicks=200) for n in range(7)] + [row(n, clicks=120) for n in range(7, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.chain and "creative is losing attention" in result.chain

    def test_the_chain_names_the_auction_when_cpm_rises_and_ctr_holds(self) -> None:
        raw = [row(n) for n in range(7)] + [row(n, spend="150") for n in range(7, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.chain and "auction got more expensive" in result.chain

    def test_a_window_with_missing_days_is_flagged_incomplete(self) -> None:
        raw = [row(n) for n in range(14) if n != 3]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert not result.comparable
        assert any("INCOMPLETE previous window" in n for n in result.notes)

    def test_an_entity_live_in_only_part_of_the_period_is_flagged(self) -> None:
        raw = [row(n) for n in range(14)] + [row(n, ad="ad-b") for n in range(10, 14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert any("UNEVEN entity ad-b" in n for n in result.notes)

    def test_a_current_window_inside_attribution_is_flagged_recent(self) -> None:
        result = compare_periods(
            rows([row(n) for n in range(14)]),
            days=7,
            result_event=LEAD,
            attribution_days=7,
            as_of=day(15),
        )
        assert any(n.startswith("RECENT") for n in result.notes)

    def test_no_daily_rows_is_an_error_that_says_what_to_request(self) -> None:
        weekly = {**row(0), "date_stop": str(day(6))}
        with pytest.raises(ValidationError, match="time_increment=1"):
            compare_periods(rows([weekly]), days=7)


def fatigue_rows() -> list[dict[str, object]]:
    """ad-a holds 2% CTR for 14 days then drops to 1.2%; ad-b holds 2% throughout."""
    out = []
    for n in range(28):
        declining = n >= 21
        out.append(row(n, clicks=120 if declining else 200, ad="ad-a"))
        out.append(row(n, clicks=200, ad="ad-b"))
    return out


class TestFatigue:
    def test_ctr_is_judged_against_the_ads_own_best_window(self) -> None:
        report = assess_fatigue(rows(fatigue_rows()), days=7, min_clicks=500)
        ad = report.ad("ad-a")
        assert ad.status == "assessed"
        assert ad.baseline is not None and ad.baseline.ctr == Decimal(2)
        assert ad.current.ctr == Decimal("1.2")
        assert ad.ctr_change_pct == Decimal(-40)
        assert ad.declined

    def test_spend_since_the_decline_is_counted_from_when_it_began(self) -> None:
        ad = assess_fatigue(rows(fatigue_rows()), days=7, min_clicks=500).ad("ad-a")
        # The first fallen rolling window is day 21..27; 7 days at 100.
        assert ad.decline_started == day(21)
        assert ad.spend_since_decline == Decimal(700)

    def test_a_healthy_sibling_is_named(self) -> None:
        report = assess_fatigue(rows(fatigue_rows()), days=7, min_clicks=500)
        assert report.siblings["set-1"] == {
            "declined": ["ad-a"],
            "held_up": ["ad-b"],
            "insufficient": [],
        }
        assert not any(n.startswith("ALL DECLINED") for n in report.notes)

    def test_everything_declining_together_is_called_out(self) -> None:
        raw = [
            row(n, clicks=120 if n >= 21 else 200, ad=ad) for n in range(28) for ad in ("a", "b")
        ]
        report = assess_fatigue(rows(raw), days=7, min_clicks=500)
        assert any(n.startswith("ALL DECLINED in ad set set-1") for n in report.notes)

    def test_frequency_is_unknown_without_a_window_row_and_a_ceiling(self) -> None:
        ad = assess_fatigue(rows(fatigue_rows()), days=7, min_clicks=500).ad("ad-a")
        (frequency,) = [c for c in ad.conditions if c.name == "frequency"]
        assert frequency.status == "unknown"
        assert not ad.both_conditions_met

    def test_frequency_comes_from_a_row_covering_the_window(self) -> None:
        window_row = {
            "date_start": str(day(21)),
            "date_stop": str(day(27)),
            "impressions": "70000",
            "reach": "14000",
            "ad_id": "ad-a",
            "adset_id": "set-1",
        }
        report = assess_fatigue(
            rows([*fatigue_rows(), window_row]), days=7, min_clicks=500, frequency_ceiling=4
        )
        ad = report.ad("ad-a")
        (frequency,) = [c for c in ad.conditions if c.name == "frequency"]
        assert frequency.value == Decimal(5)
        assert frequency.status == "met"
        assert ad.both_conditions_met

    def test_below_the_floor_there_is_no_diagnosis(self) -> None:
        ad = assess_fatigue(rows(fatigue_rows()), days=7, min_clicks=5000).ad("ad-a")
        assert ad.status == "insufficient"
        assert ad.conditions == []
        assert "floor" in (ad.reason or "")


class TestPacing:
    def test_daily_utilisation_and_outlier_days(self) -> None:
        raw = [row(n, spend="70") for n in range(5)] + [row(5, spend="20"), row(6, spend="140")]
        p = pace_daily(rows(raw), daily_budget=Decimal(70), currency="PLN")
        assert p.spend == Decimal(510)
        assert p.allowed == Decimal(490)
        assert [d.date for d in p.days_below(Decimal(50))] == [day(5)]
        assert [d.date for d in p.days_above(Decimal(150))] == [day(6)]

    def test_a_day_with_no_row_is_noted(self) -> None:
        p = pace_daily(rows([row(0), row(2)]), daily_budget=Decimal(100))
        assert any("no spend row" in n for n in p.notes)

    def test_lifetime_pace_and_projection(self) -> None:
        # 3,000 over 30 days; 10 days in, 800 spent.
        raw = [row(n, spend="80") for n in range(10)]
        p = pace_lifetime(rows(raw), budget=Decimal(3000), start=day(0), end=day(29), as_of=day(9))
        assert p.expected_to_date == Decimal(1000)
        assert p.pace_pct == Decimal(80)
        assert p.projected_total == Decimal(2400)
        assert p.daily_rate_to_finish == Decimal(110)


class TestReportCommand:
    @pytest.fixture
    def insights(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
        path = tmp_path / "insights.json"
        path.write_text(json.dumps({"data": fatigue_rows()}))
        return path

    def test_compare_json(self, insights: Path, capsys: pytest.CaptureFixture[str]) -> None:
        argv = ["report", "compare", str(insights), "--days", "7", "--result-event", LEAD]
        assert main([*argv, "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["current_window"] == {"start": str(day(21)), "end": str(day(27))}
        assert payload["changes"]["ctr"]["classification"] == "signal"
        assert payload["rules"]["min_link_clicks"] == 500

    def test_fatigue_human_output_shows_the_rules(
        self, insights: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["report", "fatigue", str(insights), "--currency", "PLN"]) == 0
        out = capsys.readouterr().out
        assert "own best" in out
        assert "700.00 PLN" in out

    def test_pacing_needs_exactly_one_budget(
        self, insights: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as missing:
            main(["report", "pacing", str(insights)])
        assert missing.value.code == 2
        assert "--daily-budget" in capsys.readouterr().err
        with pytest.raises(SystemExit) as zero:
            main(["report", "pacing", str(insights), "--daily-budget", "0"])
        assert zero.value.code == 2
        assert "must be positive" in capsys.readouterr().err

    def test_lifetime_pacing_needs_its_schedule(
        self, insights: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["report", "pacing", str(insights), "--lifetime-budget", "5000"]) == 2
        assert "--start and --end" in capsys.readouterr().err

    def test_unreadable_input_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert main(["report", "compare", str(bad), "--days", "7"]) == 2
        assert "not valid JSON" in capsys.readouterr().err


class TestPower:
    def test_a_textbook_sample_size(self) -> None:
        from meta_ads_agent.analysis.power import PowerInputs, sample_size_per_cell

        # 5% baseline, +20% relative, alpha 0.05 two-sided, power 0.8: the
        # standard two-proportion formula gives 8,155 per group.
        assert sample_size_per_cell(PowerInputs(0.05, 1000), 0.20) == 8155

    def test_more_cells_divide_alpha_and_need_more_volume(self) -> None:
        from meta_ads_agent.analysis.power import PowerInputs, sample_size_per_cell

        two = sample_size_per_cell(PowerInputs(0.05, 1000, cells=2), 0.2)
        three = sample_size_per_cell(PowerInputs(0.05, 1000, cells=3), 0.2)
        assert PowerInputs(0.05, 1000, cells=3).adjusted_alpha == 0.025
        assert three > two

    def test_the_detectable_lift_is_the_one_the_volume_supports(self) -> None:
        from meta_ads_agent.analysis.power import (
            PowerInputs,
            minimum_detectable_lift,
            sample_size_per_cell,
        )

        inputs = PowerInputs(0.05, 1000)
        lift = minimum_detectable_lift(inputs, 14)
        assert lift is not None
        assert sample_size_per_cell(inputs, lift) <= 14000
        assert sample_size_per_cell(inputs, lift * 0.95) > 14000

    def test_too_little_volume_cannot_detect_anything_worth_acting_on(self) -> None:
        from meta_ads_agent.analysis.power import PowerInputs, minimum_detectable_lift

        assert minimum_detectable_lift(PowerInputs(0.02, 10), 7) is None

    @pytest.mark.parametrize(
        ("rate", "units", "cells"), [(0, 100, 2), (1.2, 100, 2), (0.05, 0, 2), (0.05, 100, 1)]
    )
    def test_impossible_inputs_are_refused(self, rate: float, units: float, cells: int) -> None:
        from meta_ads_agent.analysis.power import PowerInputs

        with pytest.raises(ValidationError):
            PowerInputs(rate, units, cells)

    def test_the_command_says_when_a_test_cannot_answer(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["report", "power", "--baseline-rate", "0.02", "--units-per-day", "10"]
        assert main([*argv, "--days", "7", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["answerable"] is False
        assert payload["minimum_detectable_lift"] is None

    def test_the_command_gives_days_for_a_lift(self, capsys: pytest.CaptureFixture[str]) -> None:
        argv = ["report", "power", "--baseline-rate", "0.05", "--units-per-day", "1000"]
        assert main([*argv, "--lift", "0.2", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["units_per_cell"] == 8155
        assert payload["days_needed"] == pytest.approx(8.155)


class TestRealExports:
    """1.0.1: what Meta's exports actually look like, as opposed to tidy fixtures."""

    def test_rows_at_two_levels_are_refused_rather_than_double_counted(self) -> None:
        campaign = [row(n, ad=None, adset=None) | {"campaign_id": "c1"} for n in range(14)]
        adsets = [row(n, ad=None, adset="s1") | {"campaign_id": "c1"} for n in range(14)]
        with pytest.raises(ValidationError, match="mixes adset, campaign rows"):
            compare_periods(rows(campaign + adsets), days=7)

    def test_a_level_can_be_chosen_from_a_mixed_export(self) -> None:
        campaign = [row(n, ad=None, adset=None) | {"campaign_id": "c1"} for n in range(14)]
        adsets = [row(n, ad=None, adset="s1") | {"campaign_id": "c1"} for n in range(14)]
        result = compare_periods(rows(campaign + adsets), days=7, level="campaign")
        assert result.current.spend == Decimal(700)  # not 1,400

    def test_pacing_refuses_a_mixed_export_too(self) -> None:
        mixed = [row(0, ad=None, adset=None) | {"campaign_id": "c1"}, row(0, ad="a")]
        with pytest.raises(ValidationError, match="mixes"):
            pace_daily(rows(mixed), daily_budget=Decimal(100))

    def test_a_day_without_actions_counts_as_zero_results(self) -> None:
        # Meta leaves `actions` out of a row with no actions that day.
        raw = [row(n) for n in range(14)]
        raw[3] = row(3, leads=None)
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.previous.results == Decimal(30)  # 6 days x 5
        assert result.changes["cpa"].classification != "unavailable"

    def test_an_export_with_no_actions_anywhere_still_reads_as_unknown(self) -> None:
        raw = [row(n, leads=None) for n in range(14)]
        result = compare_periods(rows(raw), days=7, result_event=LEAD)
        assert result.previous.results is None

    @pytest.mark.parametrize("field", ["spend", "impressions", "inline_link_clicks"])
    def test_a_null_metric_is_zero_not_a_rejected_file(self, field: str) -> None:
        (parsed,) = load_rows([row(0) | {field: None}])
        assert parsed.spend == (0 if field == "spend" else 100)
        assert parsed.impressions == (0 if field == "impressions" else 10000)

    def test_a_decline_exactly_at_the_threshold_has_a_start_date(self) -> None:
        # 2.0% -> 1.4% is exactly -30%.
        raw = [row(n, clicks=140 if n >= 21 else 200) for n in range(28)]
        ad = assess_fatigue(rows(raw), days=7, min_clicks=500, ctr_decline_pct=30).ad("ad-a")
        assert ad.declined
        assert ad.decline_started == day(21)
        assert ad.spend_since_decline == Decimal(700)

    def test_frequency_uses_the_window_rows_own_impressions(self) -> None:
        raw = [row(n) for n in range(28) if n != 25]  # a day missing from the dailies
        window = {
            "date_start": str(day(21)),
            "date_stop": str(day(27)),
            "impressions": "70000",
            "reach": "14000",
            "ad_id": "ad-a",
            "adset_id": "set-1",
        }
        ad = assess_fatigue(rows([*raw, window]), days=7, min_clicks=500).ad("ad-a")
        (frequency,) = [c for c in ad.conditions if c.name == "frequency"]
        assert frequency.value == Decimal(5)

    def test_pacing_refuses_an_end_before_its_start(self) -> None:
        with pytest.raises(ValidationError, match="before start"):
            pace_daily(
                rows([row(n) for n in range(7)]),
                daily_budget=Decimal(100),
                start=day(5),
                end=day(1),
            )

    def test_the_level_flag_reaches_the_command(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        campaign = [row(n, ad=None, adset=None) | {"campaign_id": "c1"} for n in range(14)]
        adsets = [row(n, ad=None, adset="s1") | {"campaign_id": "c1"} for n in range(14)]
        path = tmp_path / "mixed.json"
        path.write_text(json.dumps(campaign + adsets))
        assert main(["report", "compare", str(path), "--days", "7"]) == 2
        assert "--level" in capsys.readouterr().err
        argv = ["report", "compare", str(path), "--days", "7", "--level", "adset", "--json"]
        assert main(argv) == 0
        assert json.loads(capsys.readouterr().out)["current"]["spend"] == "700.00"
