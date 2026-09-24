---
name: meta-ads-experiments
description: >-
  Design, size, run and read Meta (Facebook/Instagram) A/B tests and lift
  studies: what to test, whether the account has the volume to detect it, how
  long it must run, and what the result does and does not show. Use for "A/B
  test these creatives", "split test audiences", "is this test significant",
  "run a conversion lift study", or "which variant won".
---

# Experiments

Read `meta-ads-core` first. Its safety policy governs everything here.

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

```
ads_experiment_list_tests            → tests that exist, and their state
ads_experiment_check_eligibility     → whether a test is possible here at all
ads_experiment_abtest_create_test    → an A/B test between campaigns or ad sets
ads_experiment_abtest_get_test       → a test's setup and results
ads_experiment_abtest_update_test    → change or end a running test
ads_experiment_lift_create_test      → a holdout lift study
ads_experiment_lift_get_test         → a lift study's results
```

## Why a test, rather than looking at the numbers

Two ads in one ad set are not a test. Meta shifts delivery toward whichever
starts better, so the loser gets less spend, a different audience, and fewer
chances - its worse numbers are partly caused by the comparison. A
multi-variant creative is the same: a delivery optimisation, not a measurement.
A real A/B test splits the audience so each cell reaches comparable people.

That is also why creating one is not free: it splits live delivery.

## Approval

| Step | Class |
| --- | --- |
| Listing tests, checking eligibility, reading results | `read` |
| Creating an A/B test or a lift study | `update_active` - explicit approval, with the design below shown first |
| Changing or ending a running test | `update_active` - and say what ending early does to the result |

## Design, in this order

1. **One question.** "Does angle B beat angle A on cost per lead?" is a test.
   "Which of these five things works?" is five tests, run badly at once.
2. **One variable.** Creative, *or* audience, *or* placement, *or*
   optimisation. Two variables at once cannot say which one did it.
3. **One metric, named in advance,** with its event - cost per lead on
   `LEAD`, not "performance". Choosing the metric after seeing results is how
   a noise result becomes a finding.
4. **Eligibility.** `ads_experiment_check_eligibility` before proposing
   anything the user then has to hear is impossible.
5. **Size it.** Below.

## Sizing: can this test answer its question?

A test at 40 conversions a week per cell cannot resolve a 10% difference in
any duration anyone would accept, and the time to say so is before the split,
not after a month of inconclusive delivery.

When the preflight found the CLI, compute it. The baseline rate and daily
volume come from the account's recent insights - `report compare` gives both:

```bash
# what could a 14-day test see?
meta-ads-agent report power --baseline-rate 0.031 --units-per-day 420 --days 14

# how long to see a 15% lift, across three cells?
meta-ads-agent report power --baseline-rate 0.031 --units-per-day 420 --lift 0.15 --cells 3
```

The rate is the metric's own: conversions per click, clicks per impression.
The units are its denominator per day **per cell** - the account's volume
divided by the number of cells. With more than two cells alpha is divided
among the comparisons, which the output states.

Without the CLI, say that the test has not been sized, and why that matters,
rather than estimating by feel.

Then decide with the user:

- **It can see the effect in an acceptable time** - propose it.
- **It needs months** - say so, and offer what can be learned instead: a
  larger expected effect, fewer cells, a higher-volume metric (clicks rather
  than purchases), or no test.
- **It cannot see even a doubling** - do not propose it. A test that cannot
  answer is spend without information.

## Proposing it

```
A/B TEST PROPOSAL

Question      Does angle B ("error risk") beat angle A ("time saved")?
Variable      creative only - same audience, placements, budget, optimisation
Metric        cost per lead (LEAD), decided now
Cells         2, 50/50
Duration      14 days
Can detect    a lift of 22% or more (baseline 3.1% CVR, ~420 clicks/day/cell;
              meta-ads-agent report power)
Not able to   detect the 5-10% differences that would usually matter less
Cost          it splits the live ad set's delivery for 14 days

Creating it needs your approval.
```

## Running it

Leave it alone. Every edit to a cell mid-test - a budget, a creative, a
targeting tweak - changes what is being measured. If something must change,
say that the test is compromised, and offer to end it rather than pretend.

## Reading it

Meta's test result states its own confidence. Report it as Meta gives it, and
alongside it:

- the metric named in advance, not the one that looks best now;
- the volume each cell reached, against what sizing said it needed;
- the absolute difference as well as the relative one;
- what the test does **not** show - a winner on cost per lead in Poland in
  October is not a winner everywhere forever.

An inconclusive result is a result: the difference, if any, is smaller than
the test could see. It is not "B is slightly better".

## Lift studies

A lift study holds out part of the audience entirely and measures what the
ads *caused*, rather than what they were attributed. It answers "is this
spend doing anything?", which no attribution report can. It needs volume and
eligibility, both checked first, and its holdout means some people are
deliberately not shown ads - say that plainly when proposing it.

## Never

- Call two ads in one ad set, or a multi-variant creative, a test.
- Create a test that sizing says cannot answer its question.
- Pick the metric, or the end date, after seeing the results.
- Edit a running test's cells and still report it as clean.

Design and reading details:
[references/test-design.md](references/test-design.md).
