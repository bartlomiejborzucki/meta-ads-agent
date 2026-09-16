# Metrics and comparisons

## Reading a change correctly

Two conditions before a change is treated as signal:

1. **It exceeds a noise band.** 10-15% on a rate metric is a reasonable
   default. It is a default, not a law - configurable per advertiser.
2. **It rests on enough volume.** `min_conversions_for_decision` (default 30)
   and `min_clicks_for_decision` (default 500) in `brand.yaml`.

Either alone produces false alarms. A 40% cost-per-result swing on 3 results is
arithmetic, not information.

Always show spend alongside a percentage. The same percentage on 40 PLN and on
40,000 PLN describes two completely different events, and the percentage cannot
tell them apart.

## The metric chain

CPM, CTR, and CPC are not independent. Understanding which moved first is most
of a diagnosis.

```
CPM        auction cost per 1,000 impressions
  ×
CTR        proportion of impressions that click
  =
CPC        cost per click            (CPC = CPM / 1000 / CTR)
  ÷
CVR        proportion of clicks that convert
  =
CPA        cost per result
```

So:

- **CPA up, CVR flat, CPC up** - the problem is upstream of the page.
- **CPC up, CTR flat, CPM up** - the auction got more expensive, not the
  creative worse.
- **CPC up, CPM flat, CTR down** - the creative is losing attention.
- **CPA up, CPC flat, CVR down** - the page, the offer, the audience quality,
  or tracking.

That chain turns "CPA is up" into a specific next question, which is the whole
value of computing it.

## Metric definitions that trip people up

**Clicks.** "Clicks (all)" includes reactions, comments, shares, and profile
taps. "Link clicks" is clicks on the link. CTR computed from the wrong one
looks fine and means nothing. Always say which you used.

**Reach vs impressions.** Reach is unique people; impressions are total views.
Frequency is impressions ÷ reach.

**Landing page views vs link clicks.** A large gap means people click and do not
arrive - a slow page, a redirect chain, or broken tracking. It is one of the
highest-value comparisons in the set and it is usually not looked at.

**Results.** Meaningless without naming the event. "40 results" could be
purchases or page views.

**ROAS.** Requires conversion value. If value is not passed, ROAS is not
available - report that, not zero. Zero reads as a result.

**Cost per result.** Spend ÷ results, for the optimised event. If different ad
sets optimise for different events, their costs per result are not comparable.

## Attribution

Meta attributes a conversion to an ad within a window - a click window and
sometimes a view window. The window determines which conversions appear in
which period.

Three rules:

1. **Report the window** where Meta exposes it.
2. **Never compare across different windows.** If the setting changed
   mid-period, the comparison is invalid. Say so instead of publishing it.
3. **Recent periods understate.** Conversions arrive after the click, so the
   last few days of any window are incomplete. A fresh period always looks
   worse than it will.

**Modelled conversions.** Some reported conversions are statistical estimates
rather than observed events. They are not wrong, but they carry more
uncertainty, so a small difference in a modelled number deserves more caution
than the same difference in spend - which is observed.

## Period selection

| Comparison | Reasonable for |
| --- | --- |
| Today vs yesterday | delivery sanity checks only. Far too noisy for decisions. |
| Last 7 vs previous 7 | weekly rhythm; includes both weekend days each time |
| Last 14 vs previous 14 | more stable; starts to hide recent changes |
| Last 30 vs previous 30 | trend; too slow to catch a new problem |
| Custom | a specific change - align the boundary to the change date |

Equal lengths, always. Complete periods, always - an incomplete current period
looks worse by construction.

Comparing around a known change is more informative than comparing calendar
periods: align the boundary to the day the budget moved, and the before/after
actually means something.

### What makes a comparison unfair

- A campaign live for only part of one period
- A budget changed mid-period
- An ad set paused or activated mid-period
- A holiday, a sale, or a seasonal event in one period only
- An attribution setting change
- A creative refresh mid-period

Check `ads_account_get_activity_logs` for the period before presenting any
delta. Most "mysterious" changes have a timestamped human cause.

## Breakdowns

`ads_get_ad_entities` supports breakdowns. The useful ones:

| Breakdown | Answers |
| --- | --- |
| By campaign / ad set / ad | where a change originated |
| By placement | whether one surface is dragging the average |
| By day | when it started - often the most informative single view |
| By age, gender, region | who moved, when the audience is broad |
| By device or platform | whether one surface behaves differently |

Prefer one query with a breakdown over many queries. It is faster, it is
consistent, and it does not hit the rate limit.

## Aggregation

Do not average rates across entities. CTR averaged over five ad sets is not the
account CTR - weight by impressions, or recompute from totals.

```
correct    total link clicks / total impressions
wrong      mean of each ad set's CTR
```

The same applies to CPA, CPM, and ROAS: recompute from the underlying sums.
Averaging rates gives a number that is wrong in a direction you cannot predict.
