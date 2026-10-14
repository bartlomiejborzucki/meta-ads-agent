# Meta Ads MCP tool map

**Recorded 2026-09-16 from Meta's published Ads MCP tool reference.**

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
| `ads_get_ig_media` | Recent IG posts, filtered to boost-eligible |
| `ads_get_field_context` | Field metadata: types, filterability, enum values, supported levels |

`ads_get_field_context` is how you discover current objectives, optimisation
goals, and CTA types. Use it instead of a remembered list.

## Structure and lifecycle

| Tool | Notes |
| --- | --- |
| `ads_create_campaign` | Creates PAUSED. Never override. |
| `ads_create_ad_set` | Creates PAUSED. Budget here for ABO, on the campaign for CBO - never both. |
| `ads_create_ad` | Creates PAUSED. |
| `ads_update_entity` | Risk depends on the target's status: editing a paused entity is low risk, editing a live one is not. |
| `ads_activate_entity` | Starts spending. Explicit approval, after preview and QA. Top-down. |
| `ads_get_ad_entities` | Search campaigns / ad sets / ads, **and** the primary insights tool. |
| `ads_get_errors` | Delivery-blocking errors for an account or entity. |

No delete tool. Prefer pausing; the fallback covers deletion if it is truly
needed.

## Creatives and media

| Tool | Notes |
| --- | --- |
| `ads_create_creative` | Documented as **single-image link creatives**. Video, carousel, existing-Page-post, and multi-variant need the fallback. |
| `ads_get_creatives` | List creatives on the account |
| `ads_get_creative_ads` | Which ads use a creative - check before changing one |
| `ads_get_ad_images` | Images **already uploaded**. Not an upload tool. |
| `ads_get_ad_videos` | Videos already uploaded. Not an upload tool. |
| `ads_get_ad_preview` | Render a placement preview. Use it before every activation. |
| `ads_boost_ig_post` | Promote an existing Instagram post. **Not the build path:** Meta does not document a paused boost, so an Instagram post is built as an inert creative through the fallback (ADR-010) |

## Insights and diagnosis

| Tool | Use it for |
| --- | --- |
| `ads_get_ad_entities` | Metrics with filters, breakdowns, sorting, date ranges |
| `ads_insights_performance_trend` | How CPC, CPM, cost per result, ROAS, CTR, CVR moved |
| `ads_insights_anomaly_signal` | Meta's own view of what deviated |
| `ads_insights_auction_ranking_benchmarks` | Auction and quality ranking |
| `ads_insights_industry_benchmark` | Ad set performance vs similar advertisers |
| `ads_insights_advertiser_context` | Business/funnel summary, for optimisation-goal choice |
| `ads_get_opportunity_score` | Account score 0-100 with recommendations |
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
| Catalog | `ads_catalog_get_catalogs`, `ads_catalog_get_details`, `ads_catalog_get_diagnostics`, `ads_catalog_get_dynamic_ads_health`, `ads_catalog_get_data_sources` | `ads_catalog_create`, `ads_catalog_update_catalog` | - |
| Products | `ads_catalog_search_product`, `ads_catalog_get_product_details`, `ads_catalog_get_product_product_sets` | `ads_catalog_product_create`, `ads_catalog_update_product` | `ads_catalog_delete_product` |
| Product sets | `ads_catalog_get_product_sets`, `ads_catalog_get_product_set_details`, `ads_catalog_get_product_set_products` | `ads_catalog_create_product_set`, `ads_catalog_update_product_set` | `ads_catalog_product_set_delete` |
| Feeds | `ads_catalog_get_product_feed_details`, `ads_catalog_get_product_feed_upload_sessions` | `ads_catalog_create_product_feed`, `ads_catalog_update_product_feed`, `ads_catalog_create_product_feed_upload_session` | `ads_catalog_product_feed_delete` |
| Feed rules | `ads_catalog_get_feed_rules` | `ads_catalog_create_feed_rule` | `ads_catalog_product_feed_delete_rule` |
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

## Community-reported, unverified

Not in Meta's published reference as of 2026-09-16. Source:
`sepivip/meta-ads-skill` (MIT, `ab583c5`). Confirm before relying on them.

| Tool | Reported behaviour |
| --- | --- |
| `ads_creative_upload_image` | Upload an ad image **from a URL only** |
| `ads_entity_get_report` | Fetch a report |
| `ads_entity_schedule_report` | Schedule a recurring report |

Also reported, also unverified: budgets in minor currency units; `targeting` as
a JSON-encoded **string**; `ads_create_creative` taking flat parameters
(`page_id`, `image_hash`, `link_url`, `message`, `headline`,
`call_to_action_type`) rather than a nested `object_story_spec`; `creative` on
`ads_create_ad` as a JSON string; the ad name parameter called `ad_name`; and
`entity_type` spelled `ad_set` with an underscore.

Treat all of that as a hint about where mistakes cluster, not as a contract. If
a call fails, read the error - it usually tells you the real shape.

## Rate limits

Meta does not publish a number for this server. Community reports suggest
limits are easy to hit on large accounts, but we will not quote a figure we
cannot verify.

Practical consequence: prefer one aggregated query with breakdowns over a loop
of per-entity queries. Do not poll. Do not retry in a tight loop.
