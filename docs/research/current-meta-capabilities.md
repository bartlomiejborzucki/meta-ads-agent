# Current Meta Ads capabilities (official MCP vs. Marketing API)

**Reviewed:** 2026-09-16
**Method:** read Meta's official `Ads MCP Server` documentation tree under
`developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-mcp-server/`,
one page per tool category, plus the Marketing API changelog and the
`facebook-business` PyPI release history.
**Not verified by live introspection.** No Meta MCP session was connected to the machine
this document was written on (`claude mcp list` showed no Meta server). Everything below is
sourced from Meta's own published tool reference, which is authoritative for tool *names*
but does not publish full JSON schemas. Parameter columns are therefore intentionally coarse.

**Spot-checked 2026-09-18.** Meta's `Ad creation and management` page was
re-read: all 28 tool names in that category are unchanged, none of them closes
any of the six fallback gaps then listed (no local upload, no video creative, no Page-post
creative, no `asset_feed_spec`, no delete for campaigns / ad sets / ads), and
the server is now documented as generally available rather than gradually
rolling out. The other categories were not re-read, so their `last_reviewed`
dates stand.

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

Third-party write-ups circulating in 2026 claim the server exposes "29 tools". Meta's own
documentation tree lists substantially more (~90 distinct names, below). Prefer the docs.

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
| `ads_get_ig_media` | Recent IG media filtered to boost-eligible items |
| `ads_get_field_context` | Field metadata: type, filterability, enum values, supported levels |

`ads_get_field_context` matters a lot for this project: it is the supported way to discover
*current* enum values (objectives, optimization goals, CTA types) instead of hardcoding them.

### Campaign / ad set / ad lifecycle

| Tool | Purpose | Notes |
| --- | --- | --- |
| `ads_create_campaign` | Create a campaign | Documented as created **paused** |
| `ads_create_ad_set` | Create an ad set (targeting, budget, optimization goal) | Documented as created **paused** |
| `ads_create_ad` | Create an ad from a creative | Documented as created **paused** |
| `ads_update_entity` | Update fields on a campaign / ad set / ad | Spend-affecting; gate it |
| `ads_activate_entity` | Paused -> active | Starts spending; gate it |
| `ads_get_ad_entities` | Search/retrieve campaigns, ad sets, ads — and the primary insights tool | |
| `ads_get_errors` | Delivery-blocking errors for an account or entity | |

There is **no delete tool** for campaigns, ad sets, or ads.

### Creatives and media

| Tool | Purpose | Notes |
| --- | --- | --- |
| `ads_create_creative` | Create a **single-image link** ad creative | Documented scope is single image only |
| `ads_get_creatives` | List creatives on an account | |
| `ads_get_creative_ads` | Ads using a given creative | |
| `ads_get_ad_images` | List images **already uploaded** to the account | No upload tool |
| `ads_get_ad_videos` | List videos **already uploaded** to the account | No upload tool |
| `ads_get_ad_preview` | Render a placement preview (Feed, Story, Reels) | Covers our preview needs |
| `ads_boost_ig_post` | Promote an existing organic Instagram post | No Facebook Page-post equivalent |

Media **upload** is the single largest gap. Listing tools exist; ingestion tools do not.

### Insights and diagnostics

| Tool | Purpose |
| --- | --- |
| `ads_get_ad_entities` | Metrics (spend, impressions, CTR, CPC, CPM, conversions) with filters, breakdowns, sorting, date ranges |
| `ads_insights_performance_trend` | Metric movement over time (CPC, CPM, cost per result, ROAS, CTR, CVR) |
| `ads_insights_anomaly_signal` | Flags unusual deviations worth investigating |
| `ads_insights_auction_ranking_benchmarks` | Auction/quality ranking signals |
| `ads_insights_industry_benchmark` | Ad set performance vs. similar advertisers |
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
| `ads_create_custom_audience` | Customer file, website, lookalike, app, engagement, offline | |
| `ads_update_custom_audience` | Name, description, rule, labels | |
| `ads_update_custom_audience_users` | Add/remove users via hashed personal data | **PII. Highest-risk tool on the server.** |
| `ads_delete_custom_audience` | Delete an audience | Destructive |

### Catalogs and commerce

34 tools under the `ads_catalog_*` prefix covering catalogs, products, product sets, product
feeds, feed rules, and event-source connections: `ads_catalog_create`,
`ads_catalog_update_catalog`, `ads_catalog_get_catalogs`, `ads_catalog_get_details`,
`ads_catalog_get_diagnostics`, `ads_catalog_get_dynamic_ads_health`,
`ads_catalog_get_data_sources`, `ads_catalog_get_product_details`,
`ads_catalog_product_create`, `ads_catalog_update_product`, `ads_catalog_delete_product`,
`ads_catalog_get_product_product_sets`, `ads_catalog_search_product`,
`ads_catalog_create_product_set`, `ads_catalog_update_product_set`,
`ads_catalog_get_product_sets`, `ads_catalog_get_product_set_details`,
`ads_catalog_get_product_set_products`, `ads_catalog_product_set_delete`,
`ads_catalog_create_product_feed`, `ads_catalog_update_product_feed`,
`ads_catalog_get_product_feed_details`, `ads_catalog_create_product_feed_upload_session`,
`ads_catalog_get_product_feed_upload_sessions`, `ads_catalog_product_feed_delete`,
`ads_catalog_create_feed_rule`, `ads_catalog_get_feed_rules`,
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
| **Local image upload** | `API_FALLBACK` | No MCP upload tool; only `ads_get_ad_images` |
| **Local video upload** | `API_FALLBACK` | No MCP upload tool; needs processing polling |
| **Video ad creative** | `API_FALLBACK` | `ads_create_creative` documents single-image only |
| **Existing-post creative** | `API_FALLBACK` | Facebook Page posts have no MCP tool; `ads_boost_ig_post` exists for Instagram, but a paused boost is undocumented, so IG posts are built inert too (ADR-010, 2026-09-24) |
| **Multi-variant / placement-specific creative (`asset_feed_spec`)** | `API_FALLBACK` | Not exposed |
| **Carousel creative** | `API_FALLBACK` | Not exposed; built through the fallback since 0.6.0 (ADR-010) |
| **Delete campaign / ad set / ad** | `API_FALLBACK` | No MCP delete tool. Pause is almost always the better answer |
| Custom audiences | `OFFICIAL_MCP` | Full coverage including PII upload. We add no fallback here on purpose |
| Datasets / pixels / custom conversions | `OFFICIAL_MCP` | Full coverage |
| Catalogs | `OFFICIAL_MCP` | 34 tools |
| Catalog / dynamic ad creative (template) | `UNSUPPORTED` | `ads_create_creative` is not documented to build template creatives; catalogs stay MCP-only |
| Experiments | `OFFICIAL_MCP` | Full coverage |
| Ad Library research | `OFFICIAL_MCP` | `ads_library_search` |
| Activity logs | `OFFICIAL_MCP` | `ads_account_get_activity_logs` |
| Lead forms (`leadgen_forms`) | `UNSUPPORTED` | No MCP tool; no fallback in 0.1.0 |
| Automated rules | `UNSUPPORTED` | No MCP tool; out of scope |
| Partnership / branded-content ads | `UNSUPPORTED` | Out of scope |

## Community-reported tools absent from Meta's published reference

Reviewing `sepivip/meta-ads-skill` (MIT, commit `ab583c5`, 2026-07-31) — a skill written
against a live official-MCP session — surfaced three tool names that do **not** appear on
Meta's documentation pages:

| Tool | Reported behaviour | Status |
| --- | --- | --- |
| `ads_creative_upload_image` | Uploads an ad image **from a URL only**; reportedly cannot read a local file path | Unverified |
| `ads_entity_get_report` | Fetch a report | Unverified |
| `ads_entity_schedule_report` | Schedule a recurring report | Unverified |

If `ads_creative_upload_image` exists and is URL-only, the gap this project fills narrows from
"image upload" to "*local-file* image upload" — which is still a real gap, and still the
common case for an agent working from a user's filesystem. `config/capabilities.yaml`
records the capability as `local_image_upload` for exactly this reason.

Other unverified observations from the same source, recorded so a live session can confirm
or refute them rather than being treated as fact:

- Budgets passed to `ads_create_campaign` / `ads_create_ad_set` are in **minor currency
  units** of the account currency.
- `ads_create_ad_set` expects `targeting` as a **JSON-encoded string**, not an object.
- `ads_create_creative` takes **flat** parameters (`page_id`, `image_hash`, `link_url`,
  `message`, `headline`, `call_to_action_type`) rather than a nested `object_story_spec`.
- `ads_create_ad` expects `creative` as a JSON-encoded string and names the ad `ad_name`.
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
