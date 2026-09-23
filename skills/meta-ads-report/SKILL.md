---
name: meta-ads-report
description: >-
  Read-only performance reporting for Meta (Facebook/Instagram) ads: equal-length
  period comparisons (last 7 days vs previous 7, last 30 vs previous 30, custom
  ranges), spend, CPM, CTR, CPC, results, cost per result, ROAS, frequency, and
  attribution-aware analysis. Use for "how did last week go", "compare the last
  seven days with the previous seven", "weekly report", "what happened to
  spend", or any performance question that is not a diagnosis.
---

# Performance reporting

Read-only. A user asking how last week went has not asked you to change
anything. Read `meta-ads-core` first.

<!-- shared:preflight start - generated from packaging/shared/preflight.md by scripts/sync_skill_blocks.py - edit there -->
## Preflight: two checks, kept separate

These are independent questions with different answers and different
consequences, so never let one stand in for the other.

**1. Meta's official Ads MCP - the execution layer.** List the tools available
in this session and look for names beginning `ads_`. If there are none,
nothing in this skill can run against a real account: say so, and help the
user connect it - `connect-meta-mcp.md`, under `references/` in the
`meta-ads-core` skill, or
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-core/references/connect-meta-mcp.md>.
The local CLI is not a substitute; it deliberately does not cover what the MCP
covers.

**2. The local `meta-ads-agent` CLI - optional, separately installed, usually
absent.** The skills install without it, so assume it is missing until a probe
says otherwise:

```bash
meta-ads-agent --version
```

"command not found" is the expected answer for most users, not a fault, and
not something to work around. **Do not put a `meta-ads-agent ...` command in
front of someone before that probe has succeeded.** A command that fails at
their prompt costs more than the step it was meant to save, and it makes the
rest of your advice look equally unchecked. Say "that step needs the optional
CLI, which is not installed here" and carry on with what the MCP can do.

With the MCP connected and no CLI, all of this still works in full: audits,
reporting, Ad Library research, previews, tracking diagnosis, creative work,
optimisation diagnosis, and the MCP-side changes that follow it. Workspace
files under `.meta-ads/` can be written directly - the templates are in the
`meta-ads-core` skill's `assets/` directory.

Only these need the CLI: campaign plan validation (and therefore campaign
builds), local image and video upload, video / existing-post / multi-variant
creatives, and deletion.
<!-- shared:preflight end -->

For *why* something changed and what to do, use `meta-ads-optimize`. This skill
establishes what happened.

## A good report answers six questions

1. What happened?
2. What changed?
3. Why might it have changed?
4. What evidence supports that?
5. What should we look at next?
6. What action, if any, is justified?

Answer them in that order, and stop. A report that answers all six in a page is
more useful than one that dumps two hundred rows.

## Pull the data

```
ads_get_ad_entities                → metrics with filters, breakdowns, sorting,
                                     date ranges. The workhorse.
ads_insights_performance_trend     → how metrics moved over time
ads_insights_anomaly_signal        → Meta's own view of what deviated
ads_account_get_activity_logs      → whether a human changed something
```

Prefer one aggregated query with breakdowns over a loop of per-entity queries.
Meta rate-limits, and a loop over a large account will hit it.

Always check the activity log for the period. "Spend doubled" and "someone
raised the budget on Tuesday" are the same finding - and without the log you
would look for it in the creative.

## Compare equal-length periods

Last 7 days against the previous 7. Last 30 against the previous 30. Never 7
days against 9, and never a partial current period against a complete one -
today is incomplete and will always look worse.

State both ranges explicitly, in the account's timezone:

```
Current   2026-09-09 to 2026-09-15  (7 days)
Previous  2026-09-02 to 2026-09-08  (7 days)
Timezone  Europe/Warsaw
```

Watch for what makes a comparison unfair: a campaign that only ran for part of
one period, a budget changed mid-period, a paused ad set, a public holiday, a
period that spans a weekend differently. Say so rather than presenting the
delta as clean.

### The arithmetic

Equal windows, rates recomputed from sums, the noise band and the volume floors
are rules, not judgement, and easy to get quietly wrong by hand. When the
preflight found the local CLI, it computes all of them from saved insights
rows: [references/metrics-and-comparisons.md](references/metrics-and-comparisons.md)
has the command and what its labels mean. Report its labels as they are; the
*why* is still yours, from the activity log and breakdowns. With no CLI, follow
the same reference by hand and show the sums you computed rates from - this
skill needs nothing but the MCP.

## Attribution

Report which attribution window the numbers represent, where Meta exposes it.

**Never compare periods measured under different attribution settings.** If the
window changed, the comparison is not valid and the honest output is to say
that rather than to publish a delta.

Two more caveats worth stating when they apply:

- **Conversion lag.** Recent conversions are still arriving. The last few days
  of any window understate results, so a fresh period always looks worse than
  it will.
- **Modelled conversions.** Some reported conversions are statistical
  estimates, not observed events. Treat small differences in modelled numbers
  with more caution than the same difference in spend.

## Metrics, and what they depend on

| Metric | Read it for | Note |
| --- | --- | --- |
| Spend | always show it | context for every other number |
| Impressions, reach | delivery volume | reach is people, impressions are views |
| Frequency | impressions ÷ reach | saturation signal, not a fatigue verdict on its own |
| CPM | auction cost | rises with competition and with narrow audiences |
| Clicks, CTR | creative resonance | link clicks and all clicks are different metrics; say which |
| CPC | click efficiency | CPM ÷ CTR - so it moves when either does |
| Landing page views | whether clicks arrive | a gap against link clicks points at the page or at tracking |
| Results | the optimised event | name which event |
| Cost per result | efficiency | the number that usually matters |
| Conversion value, ROAS | revenue efficiency | only where value is passed |

**Do not derive a metric whose inputs are missing without saying so.** No
conversion value means no ROAS - report "not available", not a zero. A zero
reads as a result.

## Volume before conclusions

`brand.yaml.thresholds.min_conversions_for_decision` and
`min_clicks_for_decision` are the user's own floors. Below them, a percentage
change is noise wearing a decimal point.

```
Ad set "PL retargeting": 3 results, previous period 5.
  -40% cost per result.
  INSUFFICIENT EVIDENCE - 3 results is below the 30-result floor. This
  difference is consistent with random variation.
```

Two conditions for calling a change real: it moved more than a noise band
(10-15% is a reasonable default for a rate metric), **and** it rests on enough
volume. Both. Either alone produces false alarms.

Always show spend next to a percentage. A 60% CPA increase on 40 PLN of spend
is not the same event as a 60% increase on 40,000 PLN, and the percentage looks
identical.

## Format

```markdown
# Last 7 days — Acme
2026-09-09 to 2026-09-15 vs 2026-09-02 to 2026-09-08 (Europe/Warsaw)
Attribution: 7-day click, 1-day view

## Headline
Spend 8,420.00 PLN (+12%). Leads 96 (-8%). Cost per lead 87.71 PLN (+22%).

## What changed
| | Current | Previous | Δ |
|---|---|---|---|
| Spend | 8,420.00 PLN | 7,520.00 PLN | +12% |
| Leads | 96 | 104 | -8% |
| Cost per lead | 87.71 PLN | 72.31 PLN | +22% |
| CPM | 41.20 PLN | 33.90 PLN | +22% |
| CTR | 1.42% | 1.44% | -1% |
| Frequency | 2.1 | 1.8 | +17% |

## Where it came from
Campaign "Acme | OUTCOME_LEADS" accounts for the whole increase.
CTR is flat while CPM rose 22% — the creative is holding, the auction cost is
not. (FACT: ads_get_ad_entities, campaign breakdown.)

## Changes made in the period
2026-09-10 — daily budget raised 5,000 → 7,000 PLN by <user>
(ads_account_get_activity_logs)

## Next
Whether the CPM rise is the budget increase pushing into a more expensive
audience, or a market-wide shift. `ads_insights_auction_ranking_benchmarks`
and `ads_insights_industry_benchmark` would separate those.

## Action
None yet. Diagnose before changing anything — use meta-ads-optimize.
```

## Discipline

- Read-only. No mutations, no exceptions.
- Label FACT / INTERPRETATION / RECOMMENDATION.
- Name the tool and the date range behind every number.
- Say "insufficient evidence" when it is.
- Do not invent benchmarks. `ads_insights_industry_benchmark` provides real
  ones; a number you recall is a number you made up.
- Do not bury the answer. Headline first.

Metric definitions and comparison mechanics:
[references/metrics-and-comparisons.md](references/metrics-and-comparisons.md).
