# Diagnosis playbook

Worked sequences for the questions that come up most. Each follows the same
principle: **rule out the cheap explanations before the expensive ones**, and
check whether a human changed something before theorising about the platform.

## "Why is this campaign deteriorating?"

```
1. ads_account_get_activity_logs  — did someone change it? Always first.
2. ads_get_errors                 — is delivery blocked, rejected, in review?
3. ads_get_dataset_stats          — are conversion events still arriving?
   ads_get_dataset_quality        — has Event Match Quality dropped?
4. ads_get_ad_entities            — the metric chain, by day, by ad set, by ad
5. ads_insights_performance_trend — when did it start?
6. ads_insights_auction_ranking_benchmarks
   ads_insights_industry_benchmark — did the market move?
7. frequency and reach            — is the audience saturating?
8. per-ad CTR vs own baseline     — is one ad declining while siblings hold?
```

Then compute the chain (see `meta-ads-report/references/metrics-and-comparisons.md`):

| Pattern | Points at |
| --- | --- |
| CPM up, CTR flat | the auction, not the creative |
| CPM flat, CTR down | creative attention |
| CPC flat, CVR down | the page, the offer, audience quality, or tracking |
| Results gone, spend unchanged | tracking |
| Everything changed on one day | an edit, or an external event |

Report which explanations you ruled out and how. A diagnosis that only presents
its conclusion is not checkable.

## "Should I pause this ad?"

```
1. What does it cost per result, over what period, on what volume?
2. Is that volume above the advertiser's floors? If not: insufficient evidence.
3. Is its cost per result above the advertiser's ceiling
   (brand.yaml.thresholds.max_cpa_display)?
4. Is it declining against its OWN baseline, or has it always been this?
5. Are siblings healthier? On what volume?
6. What share of the ad set's spend does it take?
7. If you pause it, where does that budget go?
```

That last question is the one people skip. Under CBO, pausing one ad
redistributes budget within the campaign - so the question is not "is this ad
good" but "is it worse than where the money would otherwise go".

An ad that is expensive but the only one producing results at all is not a
pause candidate.

## "Increase this campaign budget from 50 to 70 PLN/day"

The request is specific, so the user has decided - but it still changes spend,
so confirm the facts before applying.

```
1. ads_get_ad_accounts   — confirm the currency. "70" is 70 of the account's
                           currency, and it is not necessarily zloty.
2. ads_get_ad_entities   — read the CURRENT budget from Meta. Do not trust
                           what the user remembers or what state says.
3. Which level is the budget on? Campaign (CBO) or ad set (ABO)?
4. Report: from 50.00 PLN to 70.00 PLN, +40%, daily, at <level>.
5. Confirm the entity id — if there are several, name them all.
6. Apply via ads_update_entity.
7. Read it back. Confirm Meta stored 70.00 PLN.
8. Record in .meta-ads/actions.jsonl with before and after.
9. Say what to watch: a budget change re-enters the learning phase, so cost
   per result will be unstable for a few days.
```

If the current budget turns out not to be 50 PLN, **stop and report that**
before changing anything. The user's mental model is wrong, and a +40% change
from a different base is not what they asked for.

## "Pause ads A and B"

Explicit and unambiguous, so it is its own approval. Still:

```
1. Resolve the names to exact ids (ads_get_ad_entities). If a name matches
   more than one ad, list the candidates and ask which.
2. Show each: id, name, current status, spend and results over 7 days.
3. If any is already paused, say so — do not report a no-op as an action.
4. Apply via ads_update_entity.
5. Read back to confirm the status.
6. Record both in the action log.
```

Do not ask "are you sure?" for a request this specific. The gate exists to
catch inference, not to add ceremony.

## "How is my pacing?"

```
1. ads_get_ad_entities — daily budget, spend by day, schedule, results
2. Actual daily spend vs the daily budget, per day
3. Lifetime budget: consumed vs elapsed schedule
4. Cost per result over the period
```

| Pattern | Reading |
| --- | --- |
| Spending at the cap, cost per result acceptable | the budget is the binding constraint. An increase is the obvious proposal. |
| Spending well under the cap | **do not raise the budget.** Something is limiting delivery: audience size, bid, a blocked ad, weak creative. Find it. |
| Lifetime budget ahead of schedule | it will exhaust early |
| Lifetime budget behind schedule | it will underspend |
| Spend spiky by day | scheduling, competition, or repeated edits |

Raising a budget that is not being spent is the most common wasted action in
optimisation, and it makes the underlying constraint harder to see.

## "Create three new ads based on the winning angle"

Which "winning" needs establishing first.

```
1. ads_get_ad_entities — per-ad results, cost per result, spend, over a period
   long enough to clear the advertiser's volume floors
2. Is the winner actually distinguishable from the others, given the volume?
   If two ads are within noise of each other, say so.
3. Read that ad's angle from the plan or creatives.json. The angle, not the
   wording.
4. Hand to meta-ads-creative: new EXECUTIONS of that angle, not rewordings of
   that ad.
5. Hand to meta-ads-campaign: build them PAUSED in the same ad set.
6. meta-ads-preview, then ask about activation.
```

Watch for the trap: if the "winner" won on 6 conversions, it may not be a
winner. Say that before building three ads on the assumption.

## "Everything is fine, what should I do next?"

A legitimate answer is "nothing, and here is why". If cost per result is within
the advertiser's target, volume is adequate, and nothing is declining, the
useful options are:

- Test a new angle, to find a better one - not because the current one is bad.
- Raise the budget, if spend is at the cap and cost per result holds.
- Broaden or add an audience, to find more of the same people.
- Fix a measurement gap, so the next decision has better evidence.

Do not invent a problem in order to have a recommendation. An account that is
working does not need changing, and changing it re-enters the learning phase
for no reason.
