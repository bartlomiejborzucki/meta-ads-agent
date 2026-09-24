"""How small a difference an A/B test can see, and how long it has to run.

Creating a test splits live delivery (``update_active``), so it should not be
created unless it can answer its question. That is arithmetic, and the
optimise and experiments skills should not be doing it by feel: a test of
two creatives at 40 conversions a week per cell cannot resolve a 10% lift in
any duration anyone would accept, and saying so before the split is the
useful thing.

Two-sided comparison of two proportions (each cell against the control),
with the normal approximation:

    n per cell = (z[1 - alpha/2] + z[power])^2 * (p1(1 - p1) + p2(1 - p2)) / (p2 - p1)^2

where p1 is the control's rate and p2 = p1 * (1 + lift). With more than two
cells each comparison is made against the control, and alpha is divided
among them (Bonferroni) - conservative, and stated in the result.

A rate is whatever the test measures: conversions per click, clicks per
impression. The unit counted per day is its denominator. Meta's own test
reports its own confidence; this is for deciding whether to run one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from meta_ads_agent.errors import ValidationError

_Z = NormalDist()


@dataclass(frozen=True, slots=True)
class PowerInputs:
    baseline_rate: float
    units_per_day_per_cell: float
    cells: int = 2
    alpha: float = 0.05
    power: float = 0.8

    def __post_init__(self) -> None:
        if not 0 < self.baseline_rate < 1:
            raise ValidationError("the baseline rate must be between 0 and 1, e.g. 0.03 for 3%")
        if self.units_per_day_per_cell <= 0:
            raise ValidationError("units per day per cell must be positive")
        if self.cells < 2:
            raise ValidationError("a test needs at least two cells")
        if not 0 < self.alpha < 1 or not 0 < self.power < 1:
            raise ValidationError("alpha and power are probabilities between 0 and 1")

    @property
    def comparisons(self) -> int:
        return self.cells - 1

    @property
    def adjusted_alpha(self) -> float:
        """Alpha per comparison with the control (Bonferroni)."""
        return self.alpha / self.comparisons


def sample_size_per_cell(inputs: PowerInputs, lift: float) -> int:
    """Units each cell needs to detect a relative *lift* (0.10 for +10%)."""
    if lift == 0:
        raise ValidationError("a lift of zero cannot be detected by any sample")
    p1 = inputs.baseline_rate
    p2 = p1 * (1 + lift)
    if not 0 < p2 < 1:
        raise ValidationError(f"a {lift:+.0%} lift on {p1:.2%} is not a possible rate")
    z = _Z.inv_cdf(1 - inputs.adjusted_alpha / 2) + _Z.inv_cdf(inputs.power)
    return math.ceil(z**2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (p2 - p1) ** 2)


def days_needed(inputs: PowerInputs, lift: float) -> float:
    return sample_size_per_cell(inputs, lift) / inputs.units_per_day_per_cell


def minimum_detectable_lift(inputs: PowerInputs, days: float) -> float | None:
    """The smallest positive relative lift *days* of volume can detect.

    None when even a doubling is out of reach - the test cannot answer
    anything a person would act on, and should not be created.
    """
    if days <= 0:
        raise ValidationError("the test must run for a positive number of days")
    available = inputs.units_per_day_per_cell * days
    ceiling = min(1.0, (1 / inputs.baseline_rate) - 1 - 1e-9)
    if sample_size_per_cell(inputs, ceiling) > available:
        return None
    low, high = 1e-6, ceiling
    for _ in range(100):
        mid = (low + high) / 2
        if sample_size_per_cell(inputs, mid) <= available:
            high = mid
        else:
            low = mid
    return high
