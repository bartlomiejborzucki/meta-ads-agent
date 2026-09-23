# Creative fatigue: signals and thresholds

Fatigue is the most over-diagnosed condition in paid social. The canonical
error is "CTR down, CPM up, must be fatigue" - which is also exactly what an
auction shift looks like, and an auction shift is not fixed by new creative.

Everything here is a **heuristic with reasoning attached**, configurable per
advertiser. Meta enforces none of it.

The signals below are arithmetic, and `meta-ads-agent report fatigue` computes
them when the CLI is available - own-baseline CTR, frequency from a window row,
spend since decline, siblings. The conclusion is not arithmetic, and stays with
you.

## Two conditions, both required

A starting point, not a law:

1. **Frequency above the advertiser's ceiling**
   (`brand.yaml.thresholds.target_frequency_ceiling`)
2. **CTR down more than the configured percentage against this ad's own
   earlier baseline** (`ctr_decline_pct_for_fatigue`, default 30%)

Requiring both cuts most false alarms, because each alone has a common
innocent explanation: high frequency on a small audience is normal, and a CTR
dip can be a weekday effect.

## Baseline against the entity's own history

**Never judge an ad against a sibling's CTR.** Different creative has different
natural CTR; comparing ad A to ad B tells you only that they are different ads.

Compare an ad's current window to its **own** best earlier window of the same
length. That is a claim about decline, which is what fatigue means.

## The healthy-sibling test

The single most useful check, and it is free.

| Observation | What it suggests |
| --- | --- |
| One ad declined, siblings in the same ad set held up | the creative is the variable - fatigue is plausible |
| **All** ads declined together | the audience, the auction, tracking, or seasonality - not the creative |
| Only the newest ad is weak | it may simply be worse, not fatigued |

Same ad set, same audience, same period. If everything fell at once, new
creative will not help, and shipping it wastes the budget and the time.

## Supporting signals

None is sufficient alone.

| Signal | Reading | Caution |
| --- | --- | --- |
| Frequency rising, reach flat | same people seeing it more | normal on a small audience |
| CPM rising | more expensive to reach this audience | usually the auction, not the ad |
| CTR declining vs own baseline | attention fading | check weekday effects |
| Cost per result rising | efficiency falling | could be anywhere in the chain |
| Spend since the decline began | how much it has cost so far | the number that decides urgency |
| Creative age | days live | weak on its own; ads do not expire on a clock |

## Age and spend

Ad lifespan correlates with **exposure**, not with days. An ad spending 50
PLN/day to a large audience and one spending 5,000 PLN/day to a small one
exhaust at very different rates.

So prefer spend-since-decline and frequency over "this ad is 21 days old".
Anyone quoting a fixed refresh cadence - "new creative every two weeks" - is
describing their own spend level.

## What is not fatigue

Rule these out first; each is cheaper to check and more common.

| Looks like fatigue | Actually | Check |
| --- | --- | --- |
| Results collapsed, spend unchanged | tracking broke | `ads_get_dataset_stats`, `ads_get_dataset_quality` |
| CPA jumped overnight | someone edited something | `ads_account_get_activity_logs` |
| CPM up, CTR flat | the auction got more expensive | `ads_insights_auction_ranking_benchmarks`, `ads_insights_industry_benchmark` |
| Everything worse for three days | seasonality, a holiday, a competitor | the day breakdown |
| Unstable right after a change | the learning phase | activity log, and wait |
| Clicks fine, conversions fell | the landing page or the offer | landing page views vs link clicks |
| Ad stopped delivering | rejected, in review, or a spend limit | `ads_get_errors` |

## Refresh the execution, or retire the angle?

Two different decisions.

**Refresh the execution** when the *reason to care* still works and the
specific ad is worn out. New image, new hook, same angle. Cheaper, and you
already know the angle resonates.

**Retire the angle** when the message itself is exhausted - several executions
of the same angle have each declined in turn. Then a new angle is the change
worth making.

The evidence that distinguishes them: has more than one execution of this angle
declined? One is an ad problem. Three is a message problem.

## What to report

```
FATIGUE ASSESSMENT — ad 120210000000123 "angle-a-time-saved"

Conditions
  Frequency                4.6   (your ceiling: 4.0)          MET
  CTR vs own baseline      -34%  (your threshold: -30%)        MET
                           1.42% now, 2.15% in its best prior 7-day window

Context
  Spend since decline      2,840.00 PLN over 9 days
  Creative age             23 days
  Healthy sibling          yes — "angle-b-error-risk" holds at 2.05% CTR
                           in the same ad set and period

Ruled out
  Activity log             no edits in the period
  Tracking                 LEAD events arriving normally, EMQ unchanged
  Delivery                 no errors
  Auction                  account CPM flat; this ad set's CPM +8%

INTERPRETATION
  Fatigue is the best-supported explanation. Both conditions are met against
  this ad's own history, a sibling with different creative is healthy in the
  same audience and period, and the cheaper explanations are ruled out.

RECOMMENDATION
  Refresh the execution rather than retiring the angle — this is the first
  execution of "time saved" to decline, so the message is not exhausted.

PROPOSED
  1. Pause ad 120210000000123 (risk: update_active — needs your approval)
  2. Build 2 new executions of the "time saved" angle, PAUSED
  Alternative: leave it running. It is still producing leads at 118.00 PLN
  against your 80.00 PLN ceiling, so the cost of waiting is roughly
  38.00 PLN per lead.
```

Note the shape: conditions with the user's own thresholds shown, context,
what was ruled out, then interpretation clearly separated from
recommendation - and an alternative with its cost.

## Insufficient evidence

Below the advertiser's volume floors, do not diagnose.

```
Ad 120210000000124: 180 impressions, 2 clicks, 0 results over 7 days.
INSUFFICIENT EVIDENCE — well below your 500-click floor. CTR at this volume
is not measurable. Let it accumulate, or check whether it is delivering at all
(ads_get_errors).
```

## Configuring the thresholds

```yaml
thresholds:
  target_frequency_ceiling: 4.0
  ctr_decline_pct_for_fatigue: 30.0
  min_conversions_for_decision: 30
  min_clicks_for_decision: 500
```

Defaults, chosen to be conservative rather than correct. A high-frequency
retargeting audience tolerates far more frequency than a cold prospecting one,
so an advertiser who knows their own numbers should set them.
