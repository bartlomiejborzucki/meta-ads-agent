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
meta-ads-agent capabilities --gaps             # only what the fallback covers
meta-ads-agent capabilities local_video_upload # one capability, with the reason
```

## What the fallback covers

Six capabilities, as of 2026-09-16. This list should shrink.

| Capability | Command | Why it exists |
| --- | --- | --- |
| `local_image_upload` | `meta-ads-agent api upload-image` | `ads_get_ad_images` lists images already on the account. No MCP tool ingests a local file. A community source reports an `ads_creative_upload_image` tool that takes URLs only - which still leaves local files unsolved. |
| `local_video_upload` | `meta-ads-agent api upload-video` | Same gap for video, plus Meta transcodes asynchronously so the upload has to wait for processing before the video is usable. |
| `create_video_creative` | `meta-ads-agent api create-creative --video` | `ads_create_creative` is documented as single-image link creatives only. |
| `create_existing_post_creative` | `meta-ads-agent api create-creative --post` | `ads_boost_ig_post` handles Instagram. A Facebook Page post has no MCP equivalent. |
| `create_multi_variant_creative` | `meta-ads-agent api create-creative --variants` | Several copy variants or placement-specific assets need `asset_feed_spec`, which the MCP does not expose. |
| `delete_entity` | `meta-ads-agent api delete` | The MCP has no delete tool for campaigns, ad sets, or ads. Prefer pausing anyway. |

Everything else - campaigns, ad sets, ads, single-image creatives, previews,
insights, audiences, datasets, pixel rules, catalogs, experiments, activity
logs, Ad Library - belongs to the MCP.

## What nothing covers

| Capability | Note |
| --- | --- |
| Carousel creatives | Not in 0.1.0. Planned. |
| Lead form creation or reading | No MCP tool. A campaign can still use a form id the user supplies. |
| Automated rules | No MCP tool, and out of scope: an autonomous spend optimiser contradicts the approval model. |
| Partnership / branded-content ads | Out of scope. |

If a user asks for one of these, say it is not supported. Do not improvise a
Graph call - there is no generic escape hatch, on purpose.

## Mixed pipelines

A video ad crosses both layers. Record which layer created each object, and
tell the user why at the point it happens:

```
1. campaign        MCP        ads_create_campaign          (PAUSED)
2. ad set          MCP        ads_create_ad_set            (PAUSED)
3. video upload    FALLBACK   api upload-video             ← no MCP upload tool
4. video creative  FALLBACK   api create-creative --video  ← MCP is single-image only
5. ad              MCP        ads_create_ad                (PAUSED)
6. preview         MCP        ads_get_ad_preview
```

Steps 3 and 4 need the optional `api` extra and a `META_ACCESS_TOKEN`. If the
user does not have them, the honest answer is: install the extra and set a
token, or upload the video in Ads Manager first and pass its id. What the
fallback is and why it is this small: <https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/getting-started/api-fallback.md>.

## The fallback is supposed to shrink

Every entry above is a bet that Meta will not ship the feature. We expect to
lose those bets, and that is the desired outcome.

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
