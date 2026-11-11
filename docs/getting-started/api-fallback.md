# Optional: the Marketing API fallback

**Deprecated as of 2026-11-04.** Meta's official Ads MCP now does everything
this fallback was built for
([ADR-012](../architecture/adr/ADR-012-mcp-coverage-and-draft-mode.md)). The
commands still work for one more release, print a deprecation warning, and
will then be removed. If everything you do goes through the MCP, you never
need a token, an app secret, or this page.

## What the fallback covered, and what does it now

```bash
meta-ads-agent capabilities --gaps     # no gaps; the deprecated fallbacks listed
```

| Capability | Deprecated command | Through the MCP, as of 2026-11-04 |
| --- | --- | --- |
| Upload a local image | `api upload-image` | `ads_creative_upload_media` - a public URL anywhere, or a local file through Meta's upload app in hosts with interactive MCP Apps |
| Upload a local video | `api upload-video` | the same, then wait for `ads_get_ad_videos` to report it ready |
| Video creative | `api create-creative --video` | `ads_create_creative` with `video_id` and a thumbnail |
| Existing-post creative | `api create-creative --post` | `ads_create_ad` with the post inline (`object_story_id`, or `source_instagram_media_id` with `instagram_user_id`), or `ads_boost_ig_post`, which creates PAUSED |
| Multi-variant or placement-specific creative | `api create-creative --variants` | `ads_create_creative` with `multi_media` or `placement_customizations` |
| Carousel creative | `api create-creative --carousel` | `ads_create_creative` with `cards` |
| Delete a campaign, ad set, or ad | `api delete` | `ads_update_entity` with `status: DELETED`. Prefer pausing anyway. |

The one case the MCP does not cover: a local file, in a terminal host that
cannot show Meta's upload app, with no public URL for it. For that, until the
commands go, this page still applies - or upload the file in Ads Manager and
pass the resulting `image_hash` or `video_id`.

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

Either export the variables in your shell, or put them in a `.env` file in the
directory you run the CLI from - it reads `./.env` at start-up, and a variable
already in your environment wins. From a checkout of this repository:

```bash
cp .env.example .env
```

Installed with `uv tool install` rather than cloned? Create `.env` by hand with
the lines below; only the `META_*` keys are read from it.

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
Meta Business SDK             OK       facebook-business 26.0.4
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
