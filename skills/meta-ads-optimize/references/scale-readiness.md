# Before proposing more budget

A budget increase is the change most likely to be proposed on thin evidence:
cost per result looked good for a few days, so more of it must be better.
Run this checklist first, and show it with the proposal. Each item is
`PASS`, `FAIL` or `UNKNOWN`, with the evidence beside it.

None of this is a Meta rule. Items 1 to 4 apply the user's own thresholds
from `brand.yaml`; the rest are practitioner heuristics, and say so
(ADR-007).

| # | Question | How to answer it | FAIL means |
| --- | --- | --- | --- |
| 1 | Is there enough volume to judge? | results in the last 7 days against `min_conversions_for_decision` | below the floor: the cost per result is arithmetic, not evidence |
| 2 | Is cost per result inside the user's ceiling? | 7-day CPA against `max_cpa_display`, or ROAS against `min_roas` | more budget buys more of something already too expensive |
| 3 | Is it stable? | `report compare --days 7`: CPA `noise` or improving | CPA worsening as `signal`: scaling now amplifies a decline |
| 4 | Is the audience far from saturation? | frequency against `target_frequency_ceiling` (`report fatigue`) | above the ceiling: more budget mostly buys repetition |
| 5 | Is the budget the constraint? | `report pacing`: most days at or near the cap | spend below the cap: the constraint is elsewhere (audience, bid, creative), and more budget will not be spent |
| 6 | Is it out of learning? | the ad set's learning status from Meta, and the activity log | a recent edit or an unfinished learning phase: wait, or the next numbers are unstable for reasons other than the budget |
| 7 | Is tracking healthy? | `ads_get_dataset_stats`: the optimised event arriving every day | results may be under-counted, and so may be the case for scaling |

Unset thresholds are `UNKNOWN`, not `PASS`: an absent ceiling is not
permission. A `FAIL` does not forbid a proposal - the user decides - but the
proposal must lead with it.

```
SCALE READINESS - ad set 120210000000045 "PL broad 25-55"
  1 volume        PASS     84 leads in 7 days (floor 30)
  2 ceiling       PASS     CPA 62.00 PLN (ceiling 80.00 PLN)
  3 stability     PASS     CPA -4.1% vs prior 7 days: noise
  4 saturation    UNKNOWN  no frequency ceiling set in brand.yaml
  5 constraint    PASS     at the 50.00 PLN cap on 6 of 7 days
  6 learning      PASS     no edits in 14 days; Meta reports learning complete
  7 tracking      PASS     Lead events on all 7 days

  Ready, with one unknown. Proposal follows.
```

## The size of the step

That smaller steps are steadier is a heuristic: a large change pushes an ad
set back into learning harder. Say so when proposing, offer the smaller step
as the alternative, and follow the user if they prefer one larger change.
Never split one approved change into several unapproved ones.
