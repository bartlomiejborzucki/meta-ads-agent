---
name: meta-ads-audit
description: >-
  Read-only audit of a Meta (Facebook/Instagram) ad account: status, currency,
  timezone, payment and eligibility, campaign structure, budgets, delivery,
  spend, pixels and datasets, conversion events, Page and Instagram identity,
  audiences, tracking health, recent performance, and configuration problems.
  Use for "audit my account", "what's broken", "review my setup", "why isn't
  this delivering", or before planning a campaign on an unfamiliar account.
---

# Meta Ads account audit

**Read-only. Never mutate an account during an audit.** A user asking what is
wrong has not asked you to fix it. Propose; do not apply.

Read `meta-ads-core` first for routing and the safety model.

## Order of work

Each step depends on the ones before it, so do not reorder them.

### 1. Account foundation

`ads_get_ad_accounts`

Record and report: name, id, `currency`, `timezone_name`, `account_status`,
`disable_reason`, `has_payment_method`, `is_queryable`, `is_ads_mcp_enabled`,
business, and country.

Currency and timezone are not trivia - every number after this point is
meaningless without them. A missing payment method or a reached spend limit
explains "nothing is delivering" faster than any performance analysis, so
surface it immediately rather than at the end.

### 2. Identity

`ads_get_user_pages` or `ads_get_ad_account_pages`, then `ads_get_ig_accounts`.

A Facebook Page is mandatory ad identity. No linked Instagram account means no
Instagram placements, which quietly changes where budget goes.

### 3. Structure

`ads_get_ad_entities` for campaigns, ad sets, and ads.

Report the shape, not every row: how many campaigns, how many are active, which
objectives, budget level (campaign/CBO vs ad set/ABO), how many ad sets per
campaign, how many ads per ad set.

Look for: campaigns with no active ad sets; ad sets with no active ads; budget
set at both levels; several ad sets targeting overlapping audiences; objectives
that do not match what the user says they want.

### 4. Delivery and errors

`ads_get_errors`, then `ads_get_opportunity_score`.

Delivery-blocking errors are the highest-value finding in most audits, because
they are specific, actionable, and often invisible in the performance numbers.
Report Meta's own score and recommendations as Meta's opinion, attributed.

### 5. Signals

`ads_get_datasets`, `ads_get_dataset_details`, `ads_get_dataset_stats`,
`ads_get_dataset_quality`, `ads_get_customconversions`.

**A pixel existing is not evidence that tracking works.** `stats` shows whether
events are actually arriving; `quality` shows Event Match Quality and freshness.
Report configuration and evidence as separate things.

If an ad set optimises for an event with no recent volume, that is a finding -
it will not deliver well, and no amount of creative work fixes it.

Deeper: use `meta-ads-tracking`.

### 6. Audiences

`ads_get_ad_account_custom_audiences`, then `ads_get_custom_audience` for
anything in use.

Check for: audiences too small to deliver, stale customer lists, audiences
referenced by live ad sets that no longer populate. Never read or export the
contents of a customer-list audience.

### 7. Recent performance

`ads_get_ad_entities` with metrics, or `ads_insights_performance_trend`.

Last 30 days at campaign level: spend, impressions, reach, frequency, CPM,
clicks, CTR, CPC, results, cost per result. Note the attribution window if it
is available; never compare numbers across different windows.

Use `meta-ads-report` for a real performance readout. The audit only needs
enough to spot structural problems.

### 8. Recent changes

`ads_account_get_activity_logs`

If something looks wrong, check whether someone changed it. "The CPA doubled"
and "someone widened the targeting on Tuesday" are the same finding, and
without the log you would guess creative fatigue.

## How to report

Three labels, never blurred:

- **FACT** - read from Meta. Name the tool and the date range.
- **INTERPRETATION** - your reading. Say what would change your mind.
- **RECOMMENDATION** - what you would do, and what it assumes.

```
FACT            The account bills in PLN, timezone Europe/Warsaw.
FACT            3 of 7 campaigns are active. Spend in the last 30 days:
                12,430.00 PLN (ads_get_ad_entities, 2026-08-17 to 2026-09-15).
FACT            Dataset 1234567890 received 0 PURCHASE events in the last 28
                days (ads_get_dataset_stats).
FACT            Ad set "PL retargeting" optimises for PURCHASE.
INTERPRETATION  That ad set is optimising for a signal Meta is not receiving,
                so its delivery is effectively unoptimised. I have not
                confirmed whether the pixel fires on the site - this is read
                from Meta's received-event counts only.
RECOMMENDATION  Verify the PURCHASE event fires before spending more here.
                Nothing needs to change in Ads Manager until that is known.
```

Structure the output as:

1. **Blocking problems** - things stopping delivery or making spend wasteful.
2. **Configuration risks** - things that will hurt but are not blocking.
3. **Observations** - worth knowing, no action implied.
4. **What I could not check** - and why.

That last section is not optional. An audit that hides its gaps invites a false
sense of coverage.

## Discipline

- **No mutations.** Not even "obviously safe" ones.
- **Do not dump metrics.** Ten findings a human can act on beats two hundred
  rows.
- **Say "insufficient evidence"** when spend or conversions are too thin to
  support a conclusion. `min_conversions_for_decision` and
  `min_clicks_for_decision` in `.meta-ads/brand.yaml` are the user's own
  floors - respect them.
- **Separate platform constraints from opinions.** "Special ad categories must
  be declared" is a rule. "You should use CBO" is a view - label it as one, or
  leave it out.
- **Do not invent benchmarks.** `ads_insights_industry_benchmark` gives real
  ones; anything else is a number you made up.

Checklist form: [references/audit-checklist.md](references/audit-checklist.md).
