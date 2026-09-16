# Optional: the Marketing API fallback

**You probably do not need this.** If everything you do is covered by Meta's
official Ads MCP, you never need a token, an app secret, or this page.

Set it up when you want one of six specific things.

## What the fallback covers

```bash
meta-ads-agent capabilities --gaps
```

| Capability | Command | Why it is not the MCP's job |
| --- | --- | --- |
| Upload a local image | `api upload-image` | `ads_get_ad_images` lists images already on the account. No MCP tool ingests a file. |
| Upload a local video | `api upload-video` | Same gap, plus Meta transcodes asynchronously so the upload must wait for processing. |
| Video creative | `api create-creative --video` | `ads_create_creative` is documented as single-image link creatives only. |
| Facebook Page existing-post creative | `api create-creative --post` | `ads_boost_ig_post` covers Instagram; a Page post has no equivalent. |
| Multi-variant creative | `api create-creative --variants` | Several copy variants need `asset_feed_spec`, which the MCP does not expose. |
| Delete a campaign, ad set, or ad | `api delete` | No MCP delete tool. Prefer pausing anyway. |

Everything else - campaigns, ad sets, ads, single-image creatives, previews,
insights, audiences, datasets, catalogs, experiments, activity logs, Ad Library -
belongs to the MCP and needs no credentials.

If you can upload assets in Ads Manager and pass the resulting `image_hash` or
`video_id`, you can skip this entirely.

## Install

```bash
uv tool install "meta-ads-agent[api]"
# or
pip install "meta-ads-agent[api]"
# or, from a clone:
uv pip install -e ".[api]"
```

The extra pulls in `facebook-business`, Meta's official Python SDK. It is
optional so that a default MCP-only install stays credential-free and small.

## Get an access token

You need a token with `ads_management` on the target account. Two routes:

**Graph API Explorer** - fastest for trying it out.
<https://developers.facebook.com/tools/explorer/>, select your app, request
`ads_management` and `ads_read`, generate. Short-lived, which is fine for a
one-off upload.

**System user token** - right for repeated or automated use. In Business
Settings, create a system user, assign it to the ad account with the ads
management role, and generate a token. These can be long-lived, which also
means a leak matters more.

Either way, the token grants write access to your ad account. Treat it like a
password.

## Configure

```bash
cp .env.example .env
```

```bash
META_ACCESS_TOKEN=<your token>
META_AD_ACCOUNT_ID=act_1234567890     # optional; saves --account on every call
META_APP_ID=                          # rarely needed
META_APP_SECRET=                      # rarely needed
META_GRAPH_API_VERSION=v26.0          # optional override
```

`.env` is gitignored, and a CI secret scan runs on every push. Beyond that:

- **Never paste a token into a chat with an agent.** Put it in `.env` or the
  environment.
- Tokens are never logged, never written to campaign state, and never printed.
  `doctor` shows a hash and a length so you can tell *which* token is
  configured without the value appearing anywhere.
- Rotate anything that leaks. Assume anything pasted into a transcript has
  leaked.

## Verify

```bash
meta-ads-agent doctor
```

Look for:

```
Meta Business SDK             OK       facebook-business 26.0.1
META_ACCESS_TOKEN             OK       sha256:a1b2c3d4e5f6 (len 213)

READY FOR API FALLBACK        yes
```

## Use it

```bash
# Dry runs need no credentials at all - they describe what would happen.
meta-ads-agent api upload-image ./creatives/hero.jpg --dry-run

meta-ads-agent api upload-image ./creatives/hero.jpg --account act_1234567890
meta-ads-agent api upload-video ./creatives/demo.mp4 --account act_1234567890
```

Both are deduplicated by content fingerprint, per ad account. Upload the same
file twice and the second call returns the existing id without re-uploading -
so a retried campaign build costs nothing, and one file never becomes two Meta
objects.

Video upload waits for Meta to finish transcoding, because a creative built
against an unprocessed video is rejected. The video id is recorded **before**
the wait begins, so a timeout never causes a re-upload.

```bash
# A video creative from an uploaded video
meta-ads-agent api create-creative --video \
  --name "angle-a video" \
  --page-id 1111111111 \
  --video-id 700000000000001 \
  --url https://example.com/offer \
  --primary-text "Friday afternoons, returned." \
  --headline "Stop rebuilding the report" \
  --cta SIGN_UP
```

Normally your agent runs these as part of a campaign build and tells you which
gap it is filling. You rarely need to type them.

## Safety

The fallback follows the same rules as the MCP. It is **not** a way around the
approval model:

- Destructive and spend-affecting commands support `--dry-run`.
- Deletion requires `--approved` **and** `--reason`, and refuses an ACTIVE
  object outright.
- Nothing here can activate an ad.
- There is no generic "run any Graph call" command, deliberately. It would void
  every guardrail in the project.

## Graph API version

Default `v26.0`, the version this release was tested against. Override with
`META_GRAPH_API_VERSION`. Read
[api-versioning.md](../reference/api-versioning.md) before you do -
`facebook-business` majors track Graph versions, so the SDK and the version
have to agree.

## This should shrink

Every capability above is a bet that Meta will not ship the feature, and we
expect to lose those bets. When Meta adds one of them to the official MCP, the
fallback entry is deprecated and removed, and one more reason to hold a token
goes away.

If you notice a tool on the connected server that covers one of these gaps,
please open an issue. See
[ADR-002](../architecture/adr/ADR-002-api-fallback.md) and
[capability-refresh.md](../reference/capability-refresh.md).
