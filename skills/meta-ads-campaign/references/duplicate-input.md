# The source of a duplicated campaign

`meta-ads-agent duplicate-plan` reads one JSON file: the campaign the agent
read from Meta, in the Marketing API's field names. Meta does not publish the
MCP's response shapes, so when a response names a field differently, map it
onto these names rather than guessing.

```json
{
  "ad_account_id": "act_1234567890",
  "currency": "PLN",
  "campaign": {
    "id": "120210000000001",
    "name": "Acme | Webinar | Q3",
    "objective": "OUTCOME_LEADS",
    "buying_type": "AUCTION",
    "special_ad_categories": [],
    "daily_budget": "15000"
  },
  "ad_sets": [
    {
      "name": "PL broad 25-55",
      "daily_budget": "7000",
      "optimization_goal": "OFFSITE_CONVERSIONS",
      "billing_event": "IMPRESSIONS",
      "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
      "promoted_object": {"pixel_id": "1234567890", "custom_event_type": "LEAD"},
      "dsa_beneficiary": "Acme Sp. z o.o.",
      "dsa_payor": "Acme Sp. z o.o.",
      "targeting": {"geo_locations": {"countries": ["PL"]}, "age_min": 25},
      "ads": [
        {
          "name": "Image",
          "creative": {
            "object_story_spec": {
              "page_id": "1111111111",
              "link_data": {
                "link": "https://acme.example.com/webinar",
                "message": "Join us",
                "name": "Free webinar",
                "image_hash": "abc123",
                "call_to_action": {"type": "SIGN_UP"}
              }
            }
          }
        }
      ]
    }
  ]
}
```

| Field | Becomes | Note |
| --- | --- | --- |
| `currency` (or `--currency`) | every budget and bid's currency | required when any budget or bid is set: they arrive in minor units |
| `daily_budget`, `lifetime_budget` | a display-amount budget | on the campaign, or on each ad set; a campaign budget wins |
| `bid_amount` | a display-amount bid | |
| `targeting` | countries, ages, genders, custom audiences, Advantage audience | every other key is kept verbatim in `targeting.raw` |
| `publisher_platforms`, `*_positions` | manual placements | also kept in `targeting.raw` |
| `promoted_object` | the dataset and conversion event | |
| `dsa_beneficiary`, `dsa_payor` | the campaign's DSA fields | the first ad set that has them |
| `object_story_spec.link_data` | a single-image ad, or a carousel with `child_attachments` | |
| `object_story_spec.video_data` | a single-video ad | the link is the call to action's |
| `object_story_id`, `source_instagram_media_id` | an existing-post ad | |
| `asset_feed_spec` | refused | a multi-variant creative is planned by hand |
| `start_time`, `end_time`, `stop_time` | not copied | the source's dates are usually past |
