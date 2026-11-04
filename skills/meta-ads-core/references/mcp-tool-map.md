# Meta Ads MCP tool map

**Recorded 2026-11-04 from the tool list and tool descriptions a connected
session exposed** (read, not called), on top of Meta's published reference of
2026-09-16. Where a behaviour was confirmed by a real build on 2026-11-03 it
says so.

This is a dated map, not a contract. Meta can rename, add, or remove tools
without telling us. Trust in this order:

1. What the connected server actually exposes.
2. `ads_get_field_context` for current field metadata and enum values.
3. A platform VALIDATION error. If it lists supported fields, that list wins.
4. This file.

Full inventory with classification, kept outside the skills because it is a
research record rather than operating guidance:
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/research/current-meta-capabilities.md>.

## Discovery

| Tool | Use it for |
| --- | --- |
| `ads_get_ad_accounts` | Accounts, with `currency` and `timezone`. **Read this first.** Community-reported eligibility fields: `is_ads_mcp_enabled`, `is_queryable`, `has_payment_method`. |
| `ads_get_user_pages` | Every Page the user can advertise with |
| `ads_get_ad_account_pages` | Pages already used on this account |
| `ads_get_pages_for_business` | Pages owned by a business |
| `ads_get_ig_accounts` | Instagram identities linked to the account |
| `ads_get_ig_media` | Advertisable posts, reels and stories. Pages of up to 25 with full media URLs - pass `limit` and `filters` (date range, media type, product type) |
| `ads_get_field_context` | Field metadata: types, filterability, enum values, supported levels |

`ads_get_field_context` is how you discover current objectives, optimisation
goals, and CTA types. Use it instead of a remembered list.

## Structure and lifecycle

| Tool | Notes |
| --- | --- |
| `ads_create_campaign` | Creates PAUSED - or, where Meta has turned on draft mode for the account, stages a **draft** (`status=DRAFT`). Never override either. `campaign_spend_cap` in minor units. |
| `ads_create_ad_set` | Same. Budget here for ABO, on the campaign for CBO - never both. |
| `ads_create_ad` | Same. `creative` can be a `creative_id`, a post (`object_story_id`, or `source_instagram_media_id` with `instagram_user_id`), or an inline spec. |
| `ads_update_entity` | Risk depends on the target's status. `status: DELETED` deletes, permanently. In draft mode an edit is staged (`is_draft: true`) until published, except a pause-only update of a published object, which applies live. `discard_draft_changes` previews, then discards with a `confirmation_token`. |
| `ads_activate_entity` | Starts spending, **and publishes drafts**. Explicit approval, after preview and QA. Name the exact objects in `object_ids`; `publish_as_active` only when the user asked to turn something on. Never call it to "confirm" a pause. |
| `ads_get_ad_entities` | Search campaigns / ad sets / ads, **and** the primary insights tool. `object_state=draft` lists staged drafts in `ad_drafts`. |
| `ads_get_errors` | Delivery-blocking errors for an account or entity. |

Draft mode is rolling out per account (2026-11-04). The tool descriptions
disagree about the status a published new campaign takes - `ads_create_campaign`
says "published objects go live ACTIVE", `ads_activate_entity` says publication
"preserves staged status unless `publish_as_active`". Treat every publish as the
moment spending can start: the `activate` class in
[safety-policy.md](safety-policy.md).

Delete exists (`status: DELETED`), and pausing is still the better answer
almost every time.

## Creatives and media

| Tool | Notes |
| --- | --- |
| `ads_create_creative` | Single image, single video (`video_id` + a thumbnail), static carousel (`cards`, 2-10), multi-media (`multi_media`, 2-10 assets, up to 5 text variants), placement-customised (`placement_customizations`, 2-10, one fallback), Page post (`object_story_id`), Instagram post (`source_instagram_media_id`). Its CTA list has no `VIEW_INSTAGRAM_PROFILE`. |
| `ads_creative_upload_media` | Upload an image or video from a public URL, or a local file through Meta's upload app - only in hosts with interactive MCP Apps. Video is usable once `ads_get_ad_videos` says `ready`. |
| `ads_creative_upload_local_image`, `ads_finalize_local_ad_image_upload`, `ads_delete_local_ad_image` | The upload app's own steps; the app drives them |
| `ads_creative_update` | Rename, label, set ACTIVE. Content is immutable. |
| `ads_creative_delete` | `delete`. Only a creative no ad uses. |
| `ads_creative_update_image_elements`, `ads_creative_create_image_variations` | Meta's generative edits of an existing ad image; each result is a new image, attached to nothing |
| `ads_get_async_result` | Collect a long-running job, e.g. image variations |
| `ads_get_creatives` | List creatives, with `effective_object_story_id` and `effective_instagram_media_id` |
| `ads_get_creative_ads` | Which ads use a creative - check before changing one |
| `ads_get_ad_images` | Images already uploaded |
| `ads_get_ad_videos` | Videos already uploaded, with processing status |
| `ads_get_ad_preview` | Render a placement preview and a `preview_url`. Use it before every activation. |
| `ads_get_ad_preview_screenshot` | Documented as app-only. Do not call it; open `preview_url` in a browser tool instead. |
| `ads_boost_ig_post` | Campaign, ad set and ad from one Instagram post. Plan first with `confirmed=false`; everything is created PAUSED. Its defaults (US targeting, a small daily budget) are not your plan's - set every field. |

An Instagram post as an ad (seen 2026-11-03): pass it **inline** in
`ads_create_ad`'s `creative` - `source_instagram_media_id`, `instagram_user_id`,
`call_to_action`. A `creative_id` made from the same post with
`ads_create_creative` failed at the ad with `ObjectStorySpecRedundant` (1443051).
Placement-customised and multi-media creatives go the other way: create them
first, then pass `{"creative_id": ...}`.

## Insights and diagnosis

| Tool | Use it for |
| --- | --- |
| `ads_get_ad_entities` | Metrics with filters, breakdowns, sorting, date ranges |
| `ads_insights_performance_trend` | How CPC, CPM, cost per result, ROAS, CTR, CVR moved |
| `ads_insights_anomaly_signal` | Meta's own view of what deviated |
| `ads_insights_auction_ranking_benchmarks` | Auction and quality ranking |
| `ads_insights_industry_benchmark` | Ad set performance vs similar advertisers |
| `ads_insights_performance_vs_peers` | Performance against peer advertisers |
| `ads_insights_advertiser_context` | Business/funnel summary, for optimisation-goal choice |
| `ads_get_opportunity_score` | **Account** score 0-100 with recommendations. Not the per-campaign score Ads Manager shows - the two can differ (100 vs 53 for one campaign on 2026-11-04). |
| `ads_account_get_activity_logs` | **Who changed what, and when** |

`ads_account_get_activity_logs` separates "performance drifted" from "somebody
edited the ad set on Tuesday". Use it in every regression investigation before
theorising about fatigue or the auction.

## Signals

| Tool | Use it for |
| --- | --- |
| `ads_get_datasets` | Pixels and app datasets |
| `ads_get_dataset_details` | Configuration, including Conversions API setup |
| `ads_get_dataset_stats` | **Event volume** over up to 28 days |
| `ads_get_dataset_quality` | Event Match Quality, match-key coverage, freshness |
| `ads_get_customconversions` | Custom conversions on the account |
| `ads_pixel_event_read` | Event rules on a pixel |
| `ads_pixel_event_create`, `ads_pixel_event_update` | Change event rules. Created inactive. `update_active`. |
| `ads_pixel_event_delete` | `delete` - prefer deactivating |
| `ads_pixel_parameter_read` | Parameter extractors |
| `ads_pixel_parameter_create`, `ads_pixel_parameter_update` | Change extractors. `update_active`. |
| `ads_pixel_parameter_delete` | `delete` |

A pixel object existing proves nothing. `stats` and `quality` are the evidence.

## Audiences

`ads_get_ad_account_custom_audiences`, `ads_get_custom_audience`,
`ads_get_custom_audience_adsets`, `ads_create_custom_audience`,
`ads_update_custom_audience`, `ads_update_custom_audience_users`,
`ads_delete_custom_audience`.

`ads_update_custom_audience_users` uploads hashed PII - see the `pii_upload`
class in [safety-policy.md](safety-policy.md). Check
`ads_get_custom_audience_adsets` before changing or deleting an audience: live
ad sets may target it.

## Catalogs

34 tools. MCP-only; no fallback exists or is planned. Every change below is
read by live catalog ads without any campaign being touched - name the live
ad sets that use the object before asking.

| Area | Read | Change (`update_active`) | Delete (`delete`) |
| --- | --- | --- | --- |
| Businesses and catalogs | `ads_catalog_get_businesses`, `ads_catalog_list_catalogs`, `ads_catalog_list_dpa_eligible_catalogs`, `ads_catalog_get_diagnostics`, `ads_catalog_get_dynamic_ads_health`, `ads_catalog_get_data_sources`, `ads_catalog_list_partner_integrations` | `ads_catalog_create`, `ads_catalog_update_catalog` | - |
| Products | `ads_catalog_list_products` | `ads_catalog_product_create`, `ads_catalog_update_product` | `ads_catalog_delete_product` |
| Product sets | `ads_catalog_list_product_sets` | `ads_catalog_create_product_set`, `ads_catalog_update_product_set` | `ads_catalog_product_set_delete` |
| Feeds | `ads_catalog_list_product_feeds`, `ads_catalog_get_product_feed_upload_sessions` | `ads_catalog_create_product_feed`, `ads_catalog_update_product_feed`, `ads_catalog_create_product_feed_upload_session` | `ads_catalog_product_feed_delete` |
| Feed rules | `ads_catalog_get_feed_rules` | `ads_catalog_create_feed_rule`, `ads_catalog_update_feed_rule` | `ads_catalog_product_feed_delete_rule` |
| Event sources | `ads_catalog_event_source_get`, `ads_catalog_event_source_get_catalogs`, `ads_catalog_event_source_get_health`, `ads_catalog_event_source_get_recommendations` | `ads_catalog_event_source_connect`, `ads_catalog_event_source_disconnect` | - |

## Experiments and research

- `ads_experiment_list_tests`, `ads_experiment_check_eligibility`,
  `ads_experiment_abtest_get_test`, `ads_experiment_lift_get_test`: reads.
- `ads_experiment_abtest_create_test`, `ads_experiment_lift_create_test`,
  `ads_experiment_abtest_update_test`: A/B tests and conversion lift studies.
  Creating or changing one splits live delivery, so it affects spend.
- `ads_library_search`: public Meta Ad Library. Research only.
- `ads_get_help_article`: Business Help Center search. Good for policy
  questions - better than guessing at policy.

## Not used by these skills

- `ads_fb_partner_permission_manager`, `ads_ig_partnership_permission_manager`:
  Partnership Ads permissions. Partnership Ads are out of scope here.
- `ads_log_ui_interaction`: telemetry for Meta's in-host app.

## Community-reported, now settled

`sepivip/meta-ads-skill` (MIT, `ab583c5`) reported three tools Meta's reference
did not list - `ads_creative_upload_image`, `ads_entity_get_report`,
`ads_entity_schedule_report`. None was exposed on 2026-11-04; URL upload is
`ads_creative_upload_media`. Its other reports hold up in the tool descriptions:
budgets in minor currency units, `targeting` and `creative` as JSON-encoded
strings, flat `ads_create_creative` parameters, `ad_name`, and `entity_type`
spelled `ad_set`.

If a call fails, read the error - it usually tells you the real shape.

## Keep responses small

Some reads return far more than a conversation can hold:

- `ads_get_ig_media` returns full media URLs for every item. Pass `limit` and
  `filters` (a date range, or `product_type: REELS`) instead of paging the
  whole account.
- `ads_get_ad_entities` with `object_state=draft` and no `object_ids` returned
  about 600,000 characters on an account with old drafts (2026-11-03). Always
  name the campaign in `object_ids`; to see whether other drafts exist, use a
  small `limit` (it counts campaigns, each with its whole subtree).
- Live reads: ask for named `fields` and the `level` you need, with
  `object_ids` when you know them.

## Rate limits

Meta does not publish a number for this server. Community reports suggest
limits are easy to hit on large accounts, but we will not quote a figure we
cannot verify.

Practical consequence: prefer one aggregated query with breakdowns over a loop
of per-entity queries. Do not poll. Do not retry in a tight loop.
