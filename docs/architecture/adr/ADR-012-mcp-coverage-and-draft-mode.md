# ADR-012: The MCP covers the fallback's gaps, and publishing a draft is spending

- **Status:** accepted
- **Date:** 2026-11-04
- **Amends:** [ADR-002](ADR-002-api-fallback.md) (the gaps),
  [ADR-004](ADR-004-write-safety.md) ("there is no draft mode"),
  [ADR-010](ADR-010-carousel-and-instagram-posts.md) (carousels, Instagram posts)

## Context

A campaign was built on 2026-11-03 against Meta's official Ads MCP, connected
as a claude.ai account connector, on a PLN account. The skills told the agent
to reach for the token-based fallback for things the MCP already did, and
described a write model the server no longer has.

On 2026-11-04 the tools that session exposed were read - names and
descriptions only, no calls. What they say:

- `ads_create_creative` builds single-video creatives (`video_id` plus a
  thumbnail), static carousels (`cards`, 2 to 10), multi-media creatives
  (`multi_media`, with up to five text variants), placement-customised
  creatives (`placement_customizations`, with one fallback asset), Facebook
  Page posts (`object_story_id`) and Instagram posts
  (`source_instagram_media_id`).
- `ads_creative_upload_media` uploads images and videos from a public URL, or
  a local file through Meta's upload app in hosts that support interactive
  MCP Apps.
- `ads_boost_ig_post` plans with `confirmed=false` and documents "All entities
  are created in PAUSED state".
- `ads_update_entity` takes `status: DELETED`; `ads_creative_delete` deletes a
  creative.

The 2026-11-03 build used the Instagram-post creative and the upload app for
real. The rest is the tool descriptions' word, dated.

It also met **draft mode**. On accounts where Meta has enabled it,
`ads_create_*` stage objects in the account's Ads Manager draft
(`status=DRAFT`), and `ads_activate_entity` publishes them, with `object_ids`,
`allow_partial_publish`, `publish_as_active` and `ignore_validation_errors`.
An edit to a published object is staged too (`is_draft: true`) and has to be
published on its own; a pause-only update applies live. The descriptions
disagree on what a published new campaign does: `ads_create_campaign` says
published objects "go live ACTIVE", with no separate activation step;
`ads_activate_entity` says publication "preserves staged status unless
publish_as_active requests activation". The account also held drafts from
months earlier - one campaign, 43 ad sets, 10 ads - that a publish without
`object_ids` could have swept up.

## Decision

**Every former gap routes to the MCP.** In `config/capabilities.yaml`,
`local_image_upload`, `local_video_upload`, `create_video_creative`,
`create_existing_post_creative`, `create_multi_variant_creative`,
`create_carousel_creative` and `delete_entity` now have
`preferred_provider: official_mcp` and `fallback_provider: api_fallback`.
This is steps 3 and 4 of ADR-002's shrinking-fallback procedure: their
`meta-ads-agent api` commands keep working, print a deprecation warning, and
are deleted in a later release. Local upload keeps the most real use: a
terminal host without MCP Apps can only give the MCP a public URL.

**An Instagram post is built inline.** The live build showed a `creative_id`
made from an Instagram post failing at `ads_create_ad` with
`ObjectStorySpecRedundant` (1443051), and the same post passed inline in the
ad's `creative` working. `ads_boost_ig_post` is a valid alternative now that
it is documented as PAUSED, behind its plan step, with its defaults (US
targeting among them) overridden from the user's plan.

**Publishing is the `activate` class.** Whatever status a published object
ends up with, publication is the step after which money can move, so it needs
what activation needed: previews, QA, and explicit approval naming the
objects. Before publishing, the agent lists the account's drafts and shows
any it did not create; it publishes only by `object_ids`, uses
`allow_partial_publish` or `ignore_validation_errors` only with the user's
say-so, and `publish_as_active` only when the user asked to turn something
on. Publishing a staged edit to a published object is the class of that edit
(`update_active`, or `budget_increase`). Discarding drafts is approved like a
delete. A pause is never followed by a publish.

**The plan records what Meta enforces and what the user chose against Meta's
advice.** New optional plan fields: `spend_cap`, `age_suggestion` (the
Advantage+ audience age range), `placements.platforms` (every position of a
platform), and `deviations` (a setting that goes against a Meta
recommendation, with the reason). The validator warns on a PLN spend cap
below 500 (Meta's error 2446307, seen 2026-11-03) and on hard age bounds
under Advantage+ audience, which the tool descriptions say are rejected.

## Consequences

**Good.** The common build - an Instagram post, an uploaded video - needs no
token. The fallback is a deprecation list, not a feature list. The safety
model describes the server that exists.

**Bad, and accepted.**
- The routing rests partly on tool descriptions, not live calls. The registry
  notes say which is which; `tests/live/` has not been extended.
- The hook classes by tool name. Publishing goes through
  `ads_activate_entity`, already an `ask`; `ads_boost_ig_post` asks when
  `confirmed` is true. A publish of the wrong objects is still a prompt the
  user can wave through.
- The two descriptions of a publish disagree. Treating publication as
  activation is the cautious reading; if Meta settles it the other way, the
  cost is one extra confirmation.

## Revisit when

- The next release ships: delete the deprecated fallback commands (ADR-002
  step 5), keeping only what a terminal host needs for local files, if
  anything.
- Meta documents the published status unambiguously, or draft mode becomes
  universal.
