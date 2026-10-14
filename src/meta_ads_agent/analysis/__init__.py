"""Arithmetic over insights: comparisons, fatigue signals, budget pacing.

Pure functions over rows the agent read from Meta. Nothing here reaches the
network, and nothing here concludes: each module returns numbers and states
what they rest on, and the report and optimise skills do the interpreting
(ADR-008).
"""

from meta_ads_agent.analysis.breakdown import Breakdown, PlacementLine, breakdown_by_placement
from meta_ads_agent.analysis.compare import Comparison, MetricChange, compare_periods
from meta_ads_agent.analysis.fatigue import AdFatigue, FatigueReport, assess_fatigue
from meta_ads_agent.analysis.insights import InsightRow, Totals, Window, load_rows
from meta_ads_agent.analysis.pacing import DailyPacing, LifetimePacing, pace_daily, pace_lifetime

__all__ = [
    "AdFatigue",
    "Breakdown",
    "Comparison",
    "DailyPacing",
    "FatigueReport",
    "InsightRow",
    "LifetimePacing",
    "MetricChange",
    "PlacementLine",
    "Totals",
    "Window",
    "assess_fatigue",
    "breakdown_by_placement",
    "compare_periods",
    "load_rows",
    "pace_daily",
    "pace_lifetime",
]
