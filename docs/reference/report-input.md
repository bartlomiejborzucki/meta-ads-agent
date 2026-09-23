# Insights input for `meta-ads-agent report`

`report compare`, `report fatigue` and `report pacing` read one JSON file of
insights rows. They never contact Meta: the agent reads insights through the
official MCP, writes the rows to a file, and passes the path.

## Shape

Either a list of rows, or an object with the rows under `data` - the shape the
Marketing API's Insights edge returns:

```json
{
  "data": [
    {
      "date_start": "2026-09-01",
      "date_stop": "2026-09-01",
      "campaign_id": "120210000000001",
      "adset_id": "120210000000045",
      "ad_id": "120210000000123",
      "ad_name": "angle-a-time-saved",
      "spend": "100.00",
      "impressions": "10000",
      "reach": "8200",
      "inline_link_clicks": "180",
      "actions": [
        {"action_type": "offsite_conversion.fb_pixel_lead", "value": "6"}
      ]
    }
  ]
}
```

| Field | Needed for | Notes |
| --- | --- | --- |
| `date_start`, `date_stop` | everything | ISO dates. **One day per row** (`time_increment=1`); multi-day rows are ignored except as described for `reach` below |
| `spend` | everything | display amount in the account currency, as Meta returns it - not minor units |
| `impressions` | rates | |
| `inline_link_clicks` | CTR, CPC, CVR, fatigue | link clicks, **not** clicks (all). `link_clicks` is accepted as a synonym |
| `actions` | results, CVR, CPA | results are the `value` of the action whose `action_type` is `--result-event`. An event absent from a row's actions counts as zero; a row with no `actions` at all makes results unknown, never zero |
| `results` | results, when there are no `actions` | a plain count, if the agent already has one |
| `ad_id`, `adset_id`, `campaign_id` | fatigue (ad and ad set), coverage notes | |
| `ad_name`, `adset_name`, `campaign_name` | display only | |
| `reach` | fatigue frequency | only from a row whose dates cover **exactly** the current window - see below |

Numbers may be strings or JSON numbers. Unknown fields are ignored.

## Why reach needs its own row

Reach is unique people. The person reached on Monday and again on Tuesday is
one person, so daily reach cannot be summed into a window's reach, and a
frequency computed that way is too low by an unknowable amount. For the
fatigue frequency condition, add one more row per ad with `date_start` and
`date_stop` spanning the current window (the same query without
`time_increment`). Without it the condition is reported as `unknown`.

## From the official MCP

Meta does not publish the response schema of its MCP insights tools, so this
project cannot promise their field names match the Marketing API's. The
metrics are the same; when names differ, map them onto the fields above
rather than guessing. That mapping has not yet been checked against a live
session - see the README's "Never run against Meta".

## Thresholds

The rules come from `brand.yaml` under `thresholds` when a workspace or
`--brand-file` provides one, and from the defaults otherwise. Every result
prints the rules it used.

| Threshold | Default | Used by |
| --- | --- | --- |
| `noise_band_pct` | 10 | compare: a rate change smaller than this is `noise` |
| `min_clicks_for_decision` | 500 | compare (CTR, CPC), fatigue (each window) |
| `min_conversions_for_decision` | 30 | compare (results, CVR, CPA) |
| `ctr_decline_pct_for_fatigue` | 30 | fatigue: the CTR condition |
| `target_frequency_ceiling` | not set | fatigue: the frequency condition; `unknown` until set |
