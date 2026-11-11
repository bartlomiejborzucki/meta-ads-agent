# Current Meta Ads capabilities (official MCP vs. Marketing API)

**Reviewed:** 2026-11-04
**Method (2026-11-04):** the tool list and tool descriptions exposed by Meta's official Ads
MCP to a connected session (a claude.ai account connector), read without calling any tool.
A campaign built against the same server on 2026-11-03 confirmed the Instagram-post creative
and media upload paths live; the rest of what this file says about creatives, upload, draft
mode and deletion is what the tool descriptions say, dated 2026-11-04.
**Checked 2026-11-11:** the tool names a connected session exposed (103 `ads_*` names and
`offer_report`), and the descriptions of `ads_create_custom_audience`,
`ads_update_custom_audience` and `offer_report`, read without calling any tool. One name
from 2026-11-04 was gone - `ads_update_custom_audience_users` - and the two audience
descriptions now say customer-list membership is not supported by the MCP. Everything else
here is still dated 2026-11-04.
**Method (2026-09-16, superseded):** Meta's published `Ads MCP Server` documentation tree
under `developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-mcp-server/`,
plus the Marketing API changelog and the `facebook-business` PyPI release history. No live
session was available then.

**What changed since 2026-09-16.** `ads_create_creative` now builds single-video,
static-carousel, multi-media (`multi_media`), placement-customised
(`placement_customizations`), Facebook Page post (`object_story_id`) and Instagram post
(`source_instagram_media_id`) creatives. `ads_creative_upload_media` uploads images and
videos from a public URL, or a local file through Meta's upload app in hosts that support
interactive MCP Apps. `ads_boost_ig_post` documents that it creates everything PAUSED, behind
a plan-then-confirm step. `ads_update_entity` accepts `status: DELETED`, and
`ads_creative_delete` deletes a creative. Every fallback gap this project listed is covered
by the MCP as of this date - see [ADR-012](../architecture/adr/ADR-012-mcp-coverage-and-draft-mode.md).
Several catalog tools were renamed (`ads_catalog_list_*`).

**Draft mode.** For accounts where Meta has enabled it, `ads_create_*` stage objects in the
account's Ads Manager draft (`status=DRAFT`) and `ads_activate_entity` publishes them. The
descriptions disagree on the status a published object takes: `ads_create_campaign` says
published objects "go live ACTIVE", `ads_activate_entity` says publication "preserves staged
status unless publish_as_active requests activation". This project treats publication as
the moment spending can start.

> Re-verify before trusting this file. See
> [docs/reference/capability-refresh.md](../reference/capability-refresh.md) for the
> refresh procedure. `config/capabilities.yaml` is the machine-readable form and carries its
> own `last_reviewed` dates.

## Endpoint and authentication

| Item | Value |
| --- | --- |
| Remote MCP endpoint | `https://mcp.facebook.com/ads` |
| Transport | Streamable HTTP |
| Auth | Facebook Login for Business OAuth (browser), or `Authorization: Bearer <user access token>` |
| Scopes Meta documents | `ads_mcp_management`, `ads_read`, `ads_management`, `catalog_management`, `business_management`, `pages_show_list`, `instagram_basic` |
| OAuth client id | The **Meta App ID** of an app you control. Meta's get-started page documents the flow with your own app. |
| Claude Code install | `claude mcp add --transport http --client-id <META_APP_ID> meta-ads https://mcp.facebook.com/ads` |
| Codex install | `codex mcp add meta-ads --url https://mcp.facebook.com/ads --oauth-client-id <META_APP_ID>`, then `codex mcp login meta-ads`. By hand: a `[mcp_servers.meta-ads]` table in `~/.codex/config.toml` with a nested `[mcp_servers.meta-ads.oauth]` `client_id`. |
| Availability | Generally available. Any app on Meta's developer dashboard can connect; acting on another business's accounts needs Advanced Access to `ads_mcp_management`. |

The OAuth client id is the reason this project does **not** bundle a Meta MCP server entry in
its plugin manifests: a hardcoded `client_id` would be wrong for every user. See
[ADR-006](../architecture/adr/ADR-006-mcp-connection-is-user-owned.md).

Third-party write-ups circulating in 2026 claim the server exposes "29 tools". A connected
session on 2026-11-04 exposed 104 distinct `ads_*` names, listed below; on 2026-11-11 it was
103, plus `offer_report` - the one tool without the prefix, which offers the user a scheduled
report after an analysis and creates nothing.

## Marketing API / SDK versions

| Item | Value as of 2026-09-16 |
| --- | --- |
| Current Graph/Marketing API version | `v26.0` |
| Oldest supported Marketing API version | `v24.0` (v23.0 expired 2026-06-09) |
| `facebook-business` (PyPI) latest | `26.0.1`, published 2026-08-25 |
| This project's default Graph version | `v26.0`, override with `META_GRAPH_API_VERSION` |

## Tool inventory (official MCP)

### Accounts, pages, identities

| Tool | Purpose |
| --- | --- |
| `ads_get_ad_accounts` | List ad accounts the user can access (name, status, currency, timezone) |
| `ads_get_ad_account_pages` | Facebook Pages already used for ads on an account |
| `ads_get_pages_for_business` | Pages owned by a business |
| `ads_get_user_pages` | All Pages the user can advertise with |
| `ads_get_ig_accounts` | Instagram Business/Creator accounts linked to an ad account |
| `ads_get_ig_media` | Advertisable IG posts, reels and stories; pages of up to 25 (`limit`), with `filters` on date, media type and product type |
| `ads_get_field_context` | Field metadata: type, filterability, enum values, supported levels |

`ads_get_field_context` matters a lot for this project: it is the supported way to discover
*current* enum values (objectives, optimization goals, CTA types) instead of hardcoding them.

### Campaign / ad set / ad lifecycle

| Tool | Purpose | Notes |
| --- | --- | --- |
| `ads_create_campaign` | Create a campaign | **Paused**, or a **draft** where draft mode is on. Takes `campaign_spend_cap` |
| `ads_create_ad_set` | Create an ad set (targeting, budget, optimization goal) | Paused, or a draft |
| `ads_create_ad` | Create an ad from a creative | Paused, or a draft. `creative` may name an existing post inline |
| `ads_update_entity` | Update fields on a campaign / ad set / ad | Spend-affecting; gate it. `status: DELETED` deletes. In draft mode most edits are staged (`is_draft`); `discard_draft_changes` previews, then discards with a token |
| `ads_activate_entity` | Paused -> active, or **publish** staged drafts (`object_ids`, `publish_as_active`, `allow_partial_publish`) | Starts spending; gate it |
| `ads_get_ad_entities` | Search/retrieve campaigns, ad sets, ads — and the primary insights tool. `object_state=draft` lists staged drafts | |
| `ads_get_errors` | Delivery-blocking errors for an account or entity | |

Deleting a campaign, ad set or ad is `ads_update_entity` with `status: DELETED`. Permanent.

### Creatives and media

| Tool | Purpose | Notes |
| --- | --- | --- |
| `ads_create_creative` | Create a creative: single image, single video (`video_id` plus a thumbnail), static carousel (`cards`, 2-10), multi-media (`multi_media`, 2-10 assets, up to 5 text variants), placement-customised (`placement_customizations`, 2-10 with one fallback), Facebook Page post (`object_story_id`), Instagram post (`source_instagram_media_id`), catalog carousel, Partnership Ads | Inert until an ad uses it |
| `ads_creative_update` | Rename a creative, set it ACTIVE, change its labels | Content is immutable |
| `ads_creative_delete` | Delete a creative not attached to an ad | Destructive |
| `ads_creative_upload_media` | Upload an image or video from a public URL, or a local file through Meta's upload app (hosts with interactive MCP Apps only) | Video is usable once its status is `ready` |
| `ads_creative_upload_local_image` / `ads_finalize_local_ad_image_upload` / `ads_delete_local_ad_image` | The upload app's own steps | App-driven |
| `ads_creative_update_image_elements` | AI edit of an existing ad image into a new image | Writes a new image; attaches nothing |
| `ads_creative_create_image_variations` | AI variations of a seed image | May return a job for `ads_get_async_result` |
| `ads_get_async_result` | Collect a long-running job | |
| `ads_get_creatives` | List creatives on an account, including `effective_object_story_id` and `effective_instagram_media_id` | |
| `ads_get_creative_ads` | Ads using a given creative | |
| `ads_get_ad_images` | List images already uploaded to the account | |
| `ads_get_ad_videos` | List videos already uploaded, with processing status | |
| `ads_get_ad_preview` | Render a placement preview (Feed, Story, Reels) and a `preview_url` | Covers our preview needs |
| `ads_get_ad_preview_screenshot` | Screenshot sink for the preview card | Documented as app-only, not for model use |
| `ads_boost_ig_post` | Campaign, ad set and ad from an existing Instagram post, in one call | Plan with `confirmed=false` first; everything created PAUSED |

Media upload was the largest gap on 2026-09-16; `ads_creative_upload_media` closes it for
URLs everywhere and for local files in hosts with MCP Apps.

### Insights and diagnostics

| Tool | Purpose |
| --- | --- |
| `ads_get_ad_entities` | Metrics (spend, impressions, CTR, CPC, CPM, conversions) with filters, breakdowns, sorting, date ranges |
| `ads_insights_performance_trend` | Metric movement over time (CPC, CPM, cost per result, ROAS, CTR, CVR) |
| `ads_insights_anomaly_signal` | Flags unusual deviations worth investigating |
| `ads_insights_auction_ranking_benchmarks` | Auction/quality ranking signals |
| `ads_insights_industry_benchmark` | Ad set performance vs. similar advertisers |
| `ads_insights_performance_vs_peers` | Performance against peer advertisers |
| `ads_insights_advertiser_context` | Business/funnel summary to guide optimization-goal choice |
| `ads_get_opportunity_score` | Account optimization score 0-100 plus recommendations |
| `ads_account_get_activity_logs` | Activity log entries, scopable by object, window, category, user |

`ads_account_get_activity_logs` is what lets a diagnosis distinguish "performance drifted"
from "somebody edited the ad set on Tuesday". Use it in every regression investigation.

### Signals, datasets, pixels

| Tool | Purpose |
| --- | --- |
| `ads_get_datasets` | Datasets (pixels/apps) on a business or ad account |
| `ads_get_dataset_details` | Dataset metadata and Conversions API setup |
| `ads_get_dataset_stats` | Event volume over a window (up to 28 days), optional breakdowns |
| `ads_get_dataset_quality` | Event Match Quality, per-match-key coverage, freshness by channel |
| `ads_get_customconversions` | Custom conversions on an account |
| `ads_pixel_event_read` / `_create` / `_update` / `_delete` | Pixel event rules (created inactive) |
| `ads_pixel_parameter_read` / `_create` / `_update` / `_delete` | Pixel parameter extractors |

`ads_get_dataset_stats` + `ads_get_dataset_quality` are the difference between "a pixel object
exists" and "events are actually arriving". The tracking skill requires both.

### Custom audiences

| Tool | Purpose | Notes |
| --- | --- | --- |
| `ads_get_ad_account_custom_audiences` | List audiences, optional subtype filter | |
| `ads_get_custom_audience` | One audience: size, status, subtype | |
| `ads_get_custom_audience_adsets` | Ad sets targeting an audience | Check before mutating |
| `ads_create_custom_audience` | Customer list (created **empty**), website, engagement, mobile app, lookalike | A lookalike takes a source and a ratio (0.01-0.20) and **no country**: "geography is handled automatically" (2026-11-11) |
| `ads_update_custom_audience` | Name, description, rule, labels | Not membership: "Ads MCP does not support membership changes; use Ads Manager" (2026-11-11) |
| `ads_delete_custom_audience` | Delete an audience | Destructive |

### Catalogs and commerce

33 tools under the `ads_catalog_*` prefix in the 2026-11-04 session, covering businesses,
catalogs, products, product sets, product feeds, feed rules, partner integrations and
event-source connections: `ads_catalog_get_businesses`, `ads_catalog_list_catalogs`,
`ads_catalog_list_dpa_eligible_catalogs`, `ads_catalog_create`,
`ads_catalog_update_catalog`, `ads_catalog_get_diagnostics`,
`ads_catalog_get_dynamic_ads_health`, `ads_catalog_get_data_sources`,
`ads_catalog_list_partner_integrations`, `ads_catalog_list_products`,
`ads_catalog_product_create`, `ads_catalog_update_product`, `ads_catalog_delete_product`,
`ads_catalog_list_product_sets`, `ads_catalog_create_product_set`,
`ads_catalog_update_product_set`, `ads_catalog_product_set_delete`,
`ads_catalog_list_product_feeds`, `ads_catalog_create_product_feed`,
`ads_catalog_update_product_feed`, `ads_catalog_create_product_feed_upload_session`,
`ads_catalog_get_product_feed_upload_sessions`, `ads_catalog_product_feed_delete`,
`ads_catalog_create_feed_rule`, `ads_catalog_update_feed_rule`, `ads_catalog_get_feed_rules`,
`ads_catalog_product_feed_delete_rule`, `ads_catalog_event_source_get`,
`ads_catalog_event_source_get_catalogs`, `ads_catalog_event_source_get_health`,
`ads_catalog_event_source_get_recommendations`, `ads_catalog_event_source_connect`,
`ads_catalog_event_source_disconnect`.

Catalog coverage is thorough. This project treats catalog work as **MCP-only** and adds no
fallback for it — see the shrinking-fallback philosophy in
[ADR-002](../architecture/adr/ADR-002-api-fallback.md).

### Experiments

`ads_experiment_list_tests`, `ads_experiment_check_eligibility`,
`ads_experiment_abtest_create_test`, `ads_experiment_abtest_get_test`,
`ads_experiment_abtest_update_test`, `ads_experiment_lift_create_test`,
`ads_experiment_lift_get_test`.

### Research and help

`ads_library_search` (public Meta Ad Library), `ads_get_help_article` (Business Help Center).

### Partnerships and the host app

`ads_fb_partner_permission_manager` and `ads_ig_partnership_permission_manager` manage
partner permissions for Partnership Ads, which this project does not build.
`ads_log_ui_interaction` is telemetry for Meta's in-host app.

## Classification

`OFFICIAL_MCP` = use the MCP, no local code. `API_FALLBACK` = MCP has no tool, use the
Business SDK. `BOTH` = MCP can do it but a narrow local path is still justified.
`UNSUPPORTED` = neither, in this release.

| Area | Class | Reasoning |
| --- | --- | --- |
| Account / page / IG discovery | `OFFICIAL_MCP` | Full coverage |
| Campaign, ad set, ad create / update / activate | `OFFICIAL_MCP` | Full coverage, paused-by-default |
| Entity search + insights | `OFFICIAL_MCP` | `ads_get_ad_entities` is the reporting workhorse |
| Ad preview | `OFFICIAL_MCP` | `ads_get_ad_preview` |
| Single-image link creative | `OFFICIAL_MCP` | `ads_create_creative` |
| Image / video upload | `OFFICIAL_MCP` | `ads_creative_upload_media` (2026-11-04). A local file needs a host with MCP Apps; elsewhere a public URL, or the deprecated `api upload-*` fallback |
| Video ad creative | `OFFICIAL_MCP` | `ads_create_creative` with `video_id` and a thumbnail (tool description, 2026-11-04) |
| Existing-post creative | `OFFICIAL_MCP` | `object_story_id` / `source_instagram_media_id`. The Instagram post was built live on 2026-11-03 inline in `ads_create_ad` (a `creative_id` made from the post failed with 1443051); `ads_boost_ig_post` creates PAUSED |
| Multi-variant / placement-specific creative | `OFFICIAL_MCP` | `multi_media`, `placement_customizations` (tool description, 2026-11-04) |
| Carousel creative | `OFFICIAL_MCP` | `cards` (tool description, 2026-11-04) |
| Delete campaign / ad set / ad | `OFFICIAL_MCP` | `ads_update_entity` with `status: DELETED` (tool description, 2026-11-04). Pause is almost always the better answer |
| Custom audiences | `OFFICIAL_MCP` | Create, update metadata, delete, lookalike. We add no fallback here on purpose |
| Customer-list members (add / replace / remove) | `UNSUPPORTED` | The MCP does not change membership (tool descriptions, 2026-11-11); `ads_update_custom_audience_users`, listed on 2026-11-04, is gone. Ads Manager > Audiences |
| Datasets / pixels / custom conversions | `OFFICIAL_MCP` | Full coverage |
| Catalogs | `OFFICIAL_MCP` | 33 tools |
| Catalog / dynamic ad creative (template) | `UNSUPPORTED` | `ads_create_creative` is not documented to build template creatives; catalogs stay MCP-only |
| Experiments | `OFFICIAL_MCP` | Full coverage |
| Ad Library research | `OFFICIAL_MCP` | `ads_library_search` |
| Activity logs | `OFFICIAL_MCP` | `ads_account_get_activity_logs` |
| Lead forms (`leadgen_forms`) | `UNSUPPORTED` | No MCP tool; no fallback |
| Automated rules | `UNSUPPORTED` | No MCP tool; out of scope |
| Partnership / branded-content ads | `UNSUPPORTED` | Out of scope here, although the MCP now builds them (`facebook_partnership_ad`, `instagram_partnership_ad`, partner `ads_boost_ig_post`) |

## Names absent from the 2026-11-04 session

Listed in Meta's reference on 2026-09-16, not exposed to the connected session on
2026-11-04 - renamed, as far as the names show, to the `ads_catalog_list_*` tools above:
`ads_catalog_get_catalogs`, `ads_catalog_get_details`, `ads_catalog_get_product_details`,
`ads_catalog_get_product_product_sets`, `ads_catalog_search_product`,
`ads_catalog_get_product_sets`, `ads_catalog_get_product_set_details`,
`ads_catalog_get_product_set_products`, `ads_catalog_get_product_feed_details`.

## Community-reported tools absent from Meta's published reference

Reviewing `sepivip/meta-ads-skill` (MIT, commit `ab583c5`, 2026-07-31) — a skill written
against a live official-MCP session — surfaced three tool names that do **not** appear on
Meta's documentation pages:

| Tool | Reported behaviour | Status |
| --- | --- | --- |
| `ads_creative_upload_image` | Uploads an ad image **from a URL only**; reportedly cannot read a local file path | Absent 2026-11-04; `ads_creative_upload_media` does this and more |
| `ads_entity_get_report` | Fetch a report | Absent 2026-11-04 |
| `ads_entity_schedule_report` | Schedule a recurring report | Absent 2026-11-04 |

None of the three appeared in the 2026-11-04 session. URL upload is now
`ads_creative_upload_media`.

Other unverified observations from the same source, recorded so a live session can confirm
or refute them rather than being treated as fact:

- Budgets passed to `ads_create_campaign` / `ads_create_ad_set` are in **minor currency
  units** of the account currency. *(Confirmed by the tool descriptions, 2026-11-04.)*
- `ads_create_ad_set` expects `targeting` as a **JSON-encoded string**, not an object.
- `ads_create_creative` takes **flat** parameters (`page_id`, `image_hash`, `link_url`,
  `message`, `headline`, `call_to_action_type`) rather than a nested `object_story_spec`.
- `ads_create_ad` expects `creative` as a JSON-encoded string and names the ad `ad_name`.
  *(Confirmed by the tool description, 2026-11-04.)*
- `entity_type` for an ad set is spelled `ad_set`, with an underscore.
- `ads_get_ad_accounts` returns eligibility fields worth checking before any write:
  `is_ads_mcp_enabled`, `is_queryable`, `has_payment_method`.

None of these are encoded as hard assumptions in this project's code. They live in
`skills/meta-ads-core/references/mcp-tool-map.md` as hints, flagged as unverified, next to
the instruction that a VALIDATION error listing supported fields outranks any local note.

## Things this document deliberately does not assert

- **Rate limits.** Meta's MCP pages do not publish a number. Community posts claim ~200
  calls/hour/account; that is unverified. The skills therefore instruct batching and
  caution rather than quoting a limit.
- **Full parameter schemas.** Not published. The agent should introspect the connected
  server and use `ads_get_field_context` rather than trusting a local enum list.
- **Objective and optimization-goal enums.** Deliberately absent. They change. See
  `skills/meta-ads-campaign/references/objectives-and-optimization.md`, which explains how
  to discover them instead of listing them.
- **Per-account eligibility.** The server is generally available, but an individual account
  still exposes `is_ads_mcp_enabled`, and we have not confirmed what makes it false.
