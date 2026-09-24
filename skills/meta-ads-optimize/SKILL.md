---
name: meta-ads-optimize
description: >-
  Diagnose deteriorating Meta (Facebook/Instagram) ad performance and propose
  changes - creative fatigue, auction shifts, tracking breaks, audience
  saturation, budget pacing, learning phase - then apply approved changes such
  as pausing an ad or adjusting a budget. Use for "why is this getting worse",
  "should I pause this", "increase this budget", "what should I change",
  "creative fatigue check", or "how is my pacing".
---

# Optimisation: diagnose, then propose, then apply

**Analyse first. Never mutate as the first response to a performance
question.** Read `meta-ads-core` for the approval model.

<!-- shared:preflight start - generated from packaging/shared/preflight.md by scripts/sync_skill_blocks.py - edit there -->
## Preflight: two checks, kept separate

Independent questions; never let one answer stand in for the other.

**1. Meta's official Ads MCP - the execution layer.** Look for tools named
`ads_*` in this session. With none, nothing here can reach an account: say so
and help the user connect it - `connect-meta-mcp.md` under `references/` in the
`meta-ads-core` skill, or
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-core/references/connect-meta-mcp.md>.
The local CLI does not replace it.

**2. The local `meta-ads-agent` CLI - optional, usually absent.** Assume it is
missing until this succeeds:

```bash
meta-ads-agent --version
```

"command not found" is the normal answer, not a fault. **Show no
`meta-ads-agent ...` command before that probe has succeeded** - a command that
fails at the user's prompt costs more than the step it saves. Say "that step
needs the optional CLI, which is not installed here" and carry on.

The MCP alone covers audits, reporting, Ad Library research, previews,
tracking, creative, optimisation and the changes that follow; `.meta-ads/`
files can be written directly from the templates in `meta-ads-core`'s
`assets/`. Only these need the CLI: plan validation (so campaign builds),
local image and video upload, video / existing-post / multi-variant /
carousel creatives, deletion, and the `report` arithmetic (which has a
by-hand route).
<!-- shared:preflight end -->

Four separate things, in order, and do not collapse them:

```
DIAGNOSIS      what is happening, and what the evidence is
RECOMMENDATION what you would do, and why
PROPOSED       the exact change: entity, field, from, to
APPLIED        done, after explicit approval, and verified
```

## "CTR fell" is not a reason to pause an ad

It is one observation. Before concluding anything, rule out the cheaper
explanations - in this order, because each is cheaper to check than the last.

### 1. Did someone change something?

```
ads_account_get_activity_logs
```

Check this **first**, every time. "The CPA doubled" and "someone widened the
targeting on Tuesday" are the same finding. Skipping the log means theorising
about fatigue when the answer is a timestamped edit.

### 2. Is there enough data to say anything?

`brand.yaml.thresholds.min_conversions_for_decision` (default 30) and
`min_clicks_for_decision` (default 500). Below those floors, a percentage
change is noise.

Say **insufficient evidence** and say what you would need. That is a legitimate
answer, and more useful than a confident wrong one.

### 3. Is tracking still working?

```
ads_get_dataset_stats      → are events still arriving?
ads_get_dataset_quality    → has Event Match Quality dropped?
```

A tracking break looks exactly like a performance collapse: results fall, spend
does not. The difference is that the ads may be fine. Check before touching
them.

### 4. Is delivery blocked?

```
ads_get_errors
```

A rejected ad, an entity in review, or a reached spend limit explains a lot
without any analysis.

### 5. Did the auction change?

```
ads_insights_auction_ranking_benchmarks
ads_insights_industry_benchmark
ads_insights_anomaly_signal
```

CPM up with CTR flat means the auction got more expensive, not that the
creative got worse. Pausing a fine ad because the market moved is a common and
avoidable mistake.

### 6. Is the audience saturating?

Frequency, reach trend, audience size. Rising frequency with flat reach means
the same people are seeing it more.

### 7. Only now: is the creative fatiguing?

Requires several signals, judged against the entity's **own** history. See
below.

### 8. Other explanations worth naming

Seasonality, a landing-page change, a competitor's campaign, a stock or pricing
change, the learning phase after a recent edit, or a budget increase pushing
delivery into a more expensive audience.

## Creative fatigue

Fatigue is one hypothesis among several, and the most over-diagnosed. The
canonical error is "CTR down, CPM up, must be fatigue" - which is also what an
auction shift looks like.

**Require multiple independent signals.** Suggested starting conditions, both
required:

- frequency above the user's `target_frequency_ceiling`, **and**
- CTR down by more than `ctr_decline_pct_for_fatigue` (default 30%) against
  **this ad's own** earlier baseline

Plus supporting context: how much has it spent since the decline began, how old
is it, and are sibling ads with different creative still healthy?

Two rules that prevent most false positives:

**Baseline against the entity's own history, never a sibling's.** Different
creative has different natural CTR. Comparing ad A to ad B tells you they are
different ads.

**A healthy sibling is the strongest evidence.** If one ad declined while
another in the same ad set, same audience, same period, held up, the audience
and the auction are probably fine and the creative is the variable. If *all*
of them declined together, it is not the creative.

**Compute the signals, do not estimate them.** When the preflight found the
CLI, save ad-level daily rows as JSON - plus, for frequency, one row per ad
covering exactly the current window, since daily reach does not add up - and
run:

```bash
meta-ads-agent report fatigue insights.json --days 7 --currency PLN
```

It reports each ad's CTR against its own best earlier window, the frequency
condition (or `unknown`, never assumed), spend since the decline began, days
with delivery, which siblings held up, and whether a whole ad set declined
together - with the user's thresholds printed alongside. Below the click floor
it says `INSUFFICIENT EVIDENCE` instead of a number. Ruling out tracking, edits,
the auction and seasonality is still the diagnosis above, and still yours.
Input shape: <https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/reference/report-input.md>.

Thresholds are **configurable defaults with reasoning**, not platform rules.
Anyone quoting "frequency above 4 means fatigue" as a law is describing their
own account. Details, with the uncertainty marked:
[references/fatigue-signals.md](references/fatigue-signals.md).

## Budget pacing

Analysis, not action.

```
ads_get_ad_entities   → daily budget, actual spend, schedule, results
```

Report: the daily budget, actual daily spend against it, days remaining on any
schedule, lifetime budget consumed against elapsed schedule, and cost per
result over the period. With the CLI, the arithmetic is one command:

```bash
meta-ads-agent report pacing insights.json --daily-budget 70 --currency PLN
meta-ads-agent report pacing insights.json --lifetime-budget 3000 \
  --start 2026-09-01 --end 2026-09-30 --currency PLN
```

It gives utilisation, the days far under or over the daily figure, and for a
lifetime budget the straight-line expectation, the projection at the current
rate, and what each remaining day would need. Budgets are display amounts in
the account currency, read from Meta.

- **Underspending** - the audience may be too narrow, the bid too low, delivery
  limited, or the creative not competitive. Raising the budget does not fix
  underspending; find the constraint first.
- **Overspending a lifetime budget early** - it will exhaust before the
  schedule ends.
- **Spending at the cap with acceptable cost per result** - the budget may be
  the binding constraint. That is the one case where an increase is the obvious
  proposal.

**Never increase a budget automatically.** Produce a proposal.

## Proposing a change

Every proposal names the entity, the field, and both values.

```
PROPOSED CHANGE
  Entity       ad set 120210000000045 "PL broad 25-55"
  Field        daily_budget
  From         50.00 PLN
  To           70.00 PLN  (+40%)
  Risk class   budget_increase — needs your explicit approval
  Why          7-day cost per lead is 62.00 PLN against your 80.00 PLN
               ceiling, spend has been at the cap for 6 of 7 days, and the
               ad set is the only one under the cap.
  Evidence     ads_get_ad_entities, 2026-09-09 to 2026-09-15, 84 leads
               (above your 30-result floor)
  Risk         A budget change re-enters the learning phase, so expect
               unstable cost per result for a few days. A larger jump
               increases that instability.
  Alternative  Raise it in two smaller steps, or leave it and test a new
               angle instead.
```

Always include the alternative, including "do nothing". A proposal with one
option is a decision presented as advice.

## Applying a change

Only after explicit, specific approval. Then:

1. **Re-read the entity from Meta.** State may have changed since you looked -
   including because Meta changed it.
2. If local and remote disagree, stop and report the mismatch.
3. Apply through `ads_update_entity`.
4. **Verify** by reading it back. Confirm the value Meta stored.
5. Record it in `.meta-ads/actions.jsonl` with before and after.
6. Tell the user what changed, and what to watch.

For pausing, name every entity you are about to pause with its id, current
status, and recent spend. "Pause the underperformers" is not a list - turn it
into one, get it confirmed, then act.

## Never

- Mutate as the first response to a performance question.
- Pause an ad on one metric.
- Change a budget without approval, both values, and the currency.
- Apply a change without verifying it afterwards.
- Present a heuristic as a platform rule.
- Conclude from a sample below the user's own floors.
- Blame fatigue before checking the activity log and tracking.

## The standing heuristics, marked as such

These are **defaults with reasoning**, configurable per advertiser. None is
enforced by Meta.

| Heuristic | Reasoning | Overridable |
| --- | --- | --- |
| Change one thing at a time | otherwise you cannot attribute the result | yes |
| Smaller budget steps are more stable | large changes re-enter learning harder | yes - `brand.yaml` |
| Wait out the learning phase after an edit | early numbers are unstable | yes |
| Pause rather than delete | deleted objects lose their optimisation history permanently | rarely worth overriding |
| Require volume before deciding | small samples produce confident nonsense | yes - `thresholds` |

Diagnostic walkthroughs:
[references/diagnosis-playbook.md](references/diagnosis-playbook.md).
