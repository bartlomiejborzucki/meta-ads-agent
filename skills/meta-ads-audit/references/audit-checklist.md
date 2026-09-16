# Audit checklist

Work through it in order. Record FACT / INTERPRETATION / RECOMMENDATION as you
go, and note anything you could not check.

## Foundation — `ads_get_ad_accounts`

- [ ] Account name and id
- [ ] `currency` — every number below is meaningless without it
- [ ] `timezone_name` — daily budgets reset on this clock, not yours
- [ ] `account_status` (1 = active) and `disable_reason`
- [ ] `has_payment_method` — false explains "nothing delivers"
- [ ] `is_queryable`, `is_ads_mcp_enabled`
- [ ] Account spending limit, if visible, and how close spend is to it
- [ ] Business and `business_country_code` — relevant to EU/DSA obligations

## Identity

- [ ] Facebook Page available and used (`ads_get_user_pages`,
      `ads_get_ad_account_pages`)
- [ ] Instagram account linked (`ads_get_ig_accounts`) — absent means no IG
      placements
- [ ] Whether live ads use a consistent identity, or several

## Structure — `ads_get_ad_entities`

- [ ] Campaign count, and how many are active
- [ ] Objectives in use, and whether they match the user's stated goal
- [ ] Budget level: campaign (CBO) or ad set (ABO). Both is a configuration
      error.
- [ ] Ad sets per campaign; ads per ad set
- [ ] Campaigns with no active ad sets
- [ ] Ad sets with no active ads
- [ ] Ad sets with overlapping audiences competing in the same auction
- [ ] Special ad categories declared where the offer implies one
- [ ] EU/DSA beneficiary and payor present where delivery reaches the EU/EEA

## Delivery

- [ ] `ads_get_errors` — every delivery-blocking error, by entity
- [ ] Ads in review, rejected, or limited
- [ ] `ads_get_opportunity_score` — report as Meta's opinion, attributed

## Signals — do not confuse configuration with evidence

- [ ] `ads_get_datasets` — which datasets exist
- [ ] `ads_get_dataset_details` — Conversions API configured?
- [ ] `ads_get_dataset_stats` — **are events actually arriving?** Up to 28 days
- [ ] `ads_get_dataset_quality` — Event Match Quality, match-key coverage,
      freshness
- [ ] `ads_get_customconversions` — custom conversions defined
- [ ] Every optimised-for event has recent volume. One that does not is a
      finding.

## Audiences

- [ ] `ads_get_ad_account_custom_audiences` — inventory by subtype
- [ ] Sizes and statuses for audiences in use (`ads_get_custom_audience`)
- [ ] Audiences too small to deliver
- [ ] Stale customer lists
- [ ] Audiences targeted by live ad sets that no longer populate
- [ ] **Never read, export, or log customer-list contents**

## Performance — last 30 days

- [ ] Spend, impressions, reach, frequency
- [ ] CPM, clicks, CTR, CPC
- [ ] Results and cost per result for the optimised event
- [ ] Attribution window, where available
- [ ] Which campaigns take most of the spend, and what they return
- [ ] Anything with spend and no results
- [ ] Anything with results and negligible spend — possibly worth more budget,
      but that is a proposal, not a change

## Changes — `ads_account_get_activity_logs`

- [ ] Edits in the period under review
- [ ] Budget changes
- [ ] Targeting changes
- [ ] Status changes
- [ ] Who made them

Before theorising about creative fatigue or the auction, check whether a human
changed something. It is the cheapest explanation to rule in or out.

## Tracking depth

If tracking looks suspect, hand off to `meta-ads-tracking` rather than
guessing. Configuration is not delivery.

## Closing the audit

- [ ] Blocking problems, most costly first
- [ ] Configuration risks
- [ ] Observations
- [ ] **What could not be checked, and why**
- [ ] Nothing was mutated
