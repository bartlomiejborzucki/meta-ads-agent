# Execution routing

Which layer performs which operation, and how to decide.

## The rule

1. If Meta's official Ads MCP has a tool for it, use the MCP.
2. Only if it does not, use the API fallback.
3. Never use the fallback because it is more convenient.
4. When you use the fallback, name the gap you are filling.

The table below is the routing map, and it is here so that a skill installed on
its own still has it. The machine-readable original is `capabilities.yaml`,
which ships with the CLI rather than with the skills -
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/config/capabilities.yaml>. Where the CLI is installed, query it rather
than remembering:

```bash
meta-ads-agent capabilities                    # everything, grouped by area
meta-ads-agent capabilities --gaps             # gaps, and the deprecated fallbacks
meta-ads-agent capabilities local_video_upload # one capability, with the reason
```

## What the fallback used to cover

As of 2026-11-04 the gap list is empty: Meta's MCP covers every capability the
fallback was built for. The commands below still work for one more release,
print a deprecation warning, and will then be deleted (ADR-002's
shrinking-fallback rule). "Live" means used in a real build on 2026-11-03;
"described" means the tool description says so on 2026-11-04.

| Capability | Through the MCP | Deprecated command |
| --- | --- | --- |
| `local_image_upload` | `ads_creative_upload_media`: a public URL anywhere, or a local file through Meta's upload app in hosts with interactive MCP Apps (live) | `meta-ads-agent api upload-image` |
| `local_video_upload` | the same tool; usable once `ads_get_ad_videos` reports `ready` (described) | `meta-ads-agent api upload-video` |
| `create_video_creative` | `ads_create_creative` with `video_id` and a thumbnail (described) | `meta-ads-agent api create-creative --video` |
| `create_existing_post_creative` | `ads_create_ad` with the post inline in `creative` - `source_instagram_media_id` + `instagram_user_id`, or `object_story_id` (live, Instagram); or `ads_boost_ig_post`, which creates everything PAUSED (described) | `meta-ads-agent api create-creative --post` |
| `create_multi_variant_creative` | `ads_create_creative` with `multi_media` or `placement_customizations`, then its `creative_id` in `ads_create_ad` (described) | `meta-ads-agent api create-creative --variants` |
| `create_carousel_creative` | `ads_create_creative` with `cards` (described) | `meta-ads-agent api create-creative --carousel` |
| `delete_entity` | `ads_update_entity` with `{"status": "DELETED"}` (described). Prefer pausing anyway. | `meta-ads-agent api delete` |

The one real use left is a local file in a terminal host that cannot open
Meta's upload app and has no public URL for it. Everything else - campaigns,
ad sets, ads, every creative format, previews, insights, audiences, datasets,
pixel rules, catalogs, experiments, activity logs, Ad Library - belongs to
the MCP.

## What nothing covers

| Capability | Note |
| --- | --- |
| Lead form creation or reading | No MCP tool. A campaign can still use a form id the user supplies. |
| Catalog (dynamic) ad creative | A template creative, which `ads_create_creative` is not documented to build; catalogs stay MCP-only. Prepare the catalog with `meta-ads-catalog`, build the ad in Ads Manager. |
| Automated rules | No MCP tool, and out of scope: an autonomous spend optimiser contradicts the approval model. |
| Partnership / branded-content ads | Out of scope here. The MCP builds them as of 2026-11-04; these skills do not cover them yet. |

If a user asks for one of these, say it is not supported. Do not improvise a
Graph call - there is no generic escape hatch, on purpose.

## A video ad, end to end

Every step is the MCP now. Record each id in `state.json` as it exists:

```
1. campaign        ads_create_campaign          (PAUSED, or a draft)
2. ad set          ads_create_ad_set            (PAUSED, or a draft)
3. video upload    ads_creative_upload_media    then ads_get_ad_videos until `ready`
4. video creative  ads_create_creative          video_id + a thumbnail
5. ad              ads_create_ad                (PAUSED, or a draft)
6. preview         ads_get_ad_preview
```

Step 3 needs a public URL for the video, or a host that can open Meta's
upload app. Without either, the deprecated `api upload-video` still works
with the `api` extra and a `META_ACCESS_TOKEN` - or the user uploads the video
in Ads Manager and passes its id. Why the fallback existed, and why it is
going: <https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/getting-started/api-fallback.md>.

## The fallback is supposed to shrink

Every fallback entry was a bet that Meta would not ship the feature. On
2026-11-04 the project lost all seven, which was the desired outcome.

If you notice a tool on the connected server that covers one of these gaps:

1. Verify it on a live connection and note the tool name and date.
2. Tell the user - it means one less credential they need.
3. Suggest the refresh procedure - <https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/reference/capability-refresh.md> -
   which flips the provider in the capability registry through a reviewed pull
   request.

Do not silently switch to a newly-discovered tool for a write operation in the
middle of a build. Finish the current build on the recorded path, then propose
the migration.

## Do not proxy

The agent calls `https://mcp.facebook.com/ads` directly. Nothing in this
project sits between them. The CLI is a sibling for gap-filling, never a
wrapper around MCP calls, and it must not become a way around the approval
model - which is why destructive commands require `--approved` and support
`--dry-run`.
