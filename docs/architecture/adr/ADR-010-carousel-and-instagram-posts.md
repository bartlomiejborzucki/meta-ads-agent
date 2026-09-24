# ADR-010: Carousels and Instagram posts join the fallback

- **Status:** accepted
- **Date:** 2026-09-24

## Context

[ADR-002](ADR-002-api-fallback.md) says the fallback is meant to shrink, and
that a change which grows it must name the MCP tool it checked and say why
that tool is not enough. 0.6 grows it in two places and extends a third.

**Carousel creatives.** The tool checked is `ads_create_creative`, which Meta
documents as creating single-image link creatives. A carousel is a link
creative whose `link_data.child_attachments` holds 2 to 10 cards, each with its
own image or video, headline and link. No tool in the published reference
takes that shape (`docs/research/current-meta-capabilities.md`, reviewed
2026-09-16). Carousels were on the roadmap since 0.1.0 and are among the most
common formats an advertiser asks for.

**Instagram existing posts.** The tool checked is `ads_boost_ig_post`. It
exists and is the obvious route - and the capability map already named it.
What Meta does not document is whether a boost can be created **paused**.
"Boost" in Meta's own products means delivery starts at once. This project's
safety model (ADR-004) creates everything PAUSED, and activation is a separate
step after previews and approval; a tool that may start spending on creation
cannot be the build path until a live session shows it can be told not to.
The SDK can build an inert creative from the post (`source_instagram_media_id`
with the Instagram identity), which spends nothing until a paused ad uses it
and is activated - the same shape as the Facebook Page post path already in
the fallback.

**Placement-specific assets** (`AssetRef.placement`) are not new fallback
surface. They are `asset_feed_spec.asset_customization_rules`, inside the
multi-variant gap ADR-002 already lists ("multi-variant and
placement-specific creatives"). 0.3 refused them in the validator because
nothing built them; 0.6 builds them.

## Decision

- `create_carousel_creative` becomes a fallback capability:
  `meta-ads-agent api create-creative --carousel`, from 2 to 10 cards.
- `create_existing_post_creative` accepts an Instagram post as well as a
  Facebook Page post. `ads_boost_ig_post` stays in the capability map as the
  MCP tool for Instagram, with a note that it is not the build path until a
  live session confirms a paused boost.
- A multi-variant creative turns each placement-pinned asset into an asset
  customisation rule for that placement, plus a default rule for the rest.

All three are inert creatives. None of them touches a budget or a status.

## Revisit when

- A live session shows `ads_create_creative` accepting cards, or
  `ads_boost_ig_post` creating a paused boost. Then the shrinking-fallback
  procedure in ADR-002 applies: flip the provider, deprecate, delete.
- The live tests in `tests/live/` run. The carousel and customisation-rule
  shapes are checked against the SDK's object descriptions offline, and have
  not been confirmed by Meta.

## Consequences

**Good.** The two most-requested missing formats can be built, and placement
assets stop being a field that validates and does nothing.

**Bad, and accepted.** Two more capabilities that need a token. The fallback
is seven entries now rather than six; ADR-002's rule is that this has to be
argued, and this is the argument.
