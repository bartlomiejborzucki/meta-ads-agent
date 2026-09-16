# ADR-002: The fallback uses the official Business SDK, and is meant to shrink

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Meta's official MCP does not cover everything. Reading its documented tool list
([capabilities](../../research/current-meta-capabilities.md)), the gaps that matter for a
coding agent working from a user's filesystem are:

1. **Local media upload.** `ads_get_ad_images` and `ads_get_ad_videos` list what is already
   uploaded. No tool ingests a file. One community source reports an
   `ads_creative_upload_image` tool that accepts **URLs only** — which still leaves local
   files unsolved, and is the common case.
2. **Video creatives.** `ads_create_creative` is documented as single-image link creatives.
3. **Facebook Page existing-post creatives.** `ads_boost_ig_post` covers Instagram only.
4. **Multi-variant and placement-specific creatives** (`asset_feed_spec`). Not exposed.
5. **Deleting a campaign, ad set, or ad.** No delete tool at all.

"Upload this MP4 and make it an ad" is a first-session request. Without a fallback the honest
answer is "upload it in Ads Manager first", which defeats the purpose.

## Decision

Fill exactly those gaps, through the **official `facebook-business` SDK**, exposed as
`meta-ads-agent api <command>`. Specifically:

- Do not hand-roll Graph authentication, pagination, retries, or request formatting. The SDK
  does those. Chunked video upload with processing-status polling especially.
- Raw Graph requests only where the SDK lacks correct support. Each one must be encapsulated
  in one module, carry a comment explaining why, be covered by a test, and use the explicitly
  configured API version.
- `facebook-business` is an **optional extra**. An MCP-only install does not download it.
- The fallback obeys the same risk classes as the MCP. It is not a bypass. Destructive and
  spend-affecting commands support `--dry-run`.
- No generic "execute any Graph call" command in 0.1.0. It would void the safety model.

## The shrinking-fallback rule

This surface is a liability, not an asset. Every capability in it is a bet that Meta will not
ship the feature — a bet we expect to lose, and want to lose.

When Meta adds a capability we currently fall back for:

1. Verify it on a live connection and record the tool name and date.
2. Add or update a routing test.
3. Flip `preferred_provider` to `official_mcp` in `config/capabilities.yaml`.
4. Mark the fallback entry `deprecated: true` with a removal target.
5. Delete the code once a release has shipped with the deprecation.

A pull request that *grows* the fallback must state which MCP tool it checked and why that
tool is insufficient. "Easier this way" is not a reason.

## Consequences

**Good.** Local assets work on day one. The fallback is ~5 capabilities, not a platform. No
credentials for MCP-only users. The SDK absorbs Graph churn.

**Bad, and accepted.**
- Two code paths for some flows, so `provider` is recorded in state and reported to the user.
- The `api` extra needs a token, an ads-management scope, and possibly an app — real friction,
  isolated to users who need it and explained in
  [docs/getting-started/api-fallback.md](../../getting-started/api-fallback.md).
- `facebook-business` is licensed under the Facebook Platform License, not an OSI license. It
  is a dependency, never vendored. See [provenance](../../research/provenance.md).
- SDK majors track Graph versions, so upgrades are not routine. Dependabot is configured not
  to auto-merge them.

## Alternatives rejected

**Write our own Graph client for the gaps.** Reimplements chunked upload, retry semantics, and
pagination that the SDK already gets right, and makes us own Graph churn.

**Require users to upload assets in Ads Manager.** Breaks the core use case.

**Make the CLI a general Graph escape hatch.** Cheap to build, and it would make every
guardrail in the project optional. Explicitly out of scope.
