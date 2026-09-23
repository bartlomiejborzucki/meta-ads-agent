# Refreshing the capability map

Meta's official Ads MCP has no public source repository and publishes no
schemas, so we cannot diff it automatically and will not put credentials in CI
to try. The refresh is a documented manual procedure, run by someone with an
authenticated session.

**Do this when:** a new tool appears, a tool changes shape, an entry in
`config/capabilities.yaml` is more than 75 days old (the weekly upstream check
opens an issue; `doctor` warns users from 90 days), or
something that worked stops working.

## 1. Introspect the connected server

With Meta's MCP connected, ask the agent:

> List every Meta Ads tool available to you, with its description. Then
> summarise which of these are new or missing compared with
> `docs/research/current-meta-capabilities.md`, and note today's date.

Then, for anything that changed shape:

> Use `ads_get_field_context` to show current field metadata and enum values
> for <field>.

Introspection is the only reliable source. Meta's documentation pages are a
good cross-check and have already been shown to omit tools that exist.

## 2. Check the gaps specifically

Six capabilities currently route to the fallback. Each is a bet that Meta will
not ship the feature, and losing that bet is the desired outcome.

For each, ask whether a tool now exists:

| Gap | Look for |
| --- | --- |
| `local_image_upload` | any tool that accepts a local file path, not just a URL |
| `local_video_upload` | a video upload tool |
| `create_video_creative` | `ads_create_creative` accepting `video_id` or `video_data` |
| `create_existing_post_creative` | a Facebook Page equivalent of `ads_boost_ig_post` |
| `create_multi_variant_creative` | anything exposing `asset_feed_spec` |
| `delete_entity` | a delete tool for campaigns, ad sets, or ads |

Finding one is good news: it means one less reason for anyone to hold an access
token.

## 3. Update the registry

Edit `config/capabilities.yaml`:

```yaml
- name: local_video_upload
  preferred_provider: official_mcp     # was api_fallback
  fallback_provider: api_fallback      # kept during deprecation
  mcp_tools: [ads_upload_video]        # the tool you verified
  deprecated_fallback: true
  deprecated_since: 2026-11-xx
  removal_target: 0.3.0
  last_reviewed: 2026-11-xx
  notes: >
    Meta added ads_upload_video, verified <date>. The SDK fallback is
    deprecated and will be removed in 0.3.0.
```

Then:

```bash
meta-ads-agent capabilities --validate
```

## 4. Update the routing test

`tests/test_capability_routing.py` asserts the exact set of gaps:

```python
def test_the_known_gaps_are_the_documented_ones(self, registry):
    assert {c.name for c in registry.gaps()} == { ... }
```

Update it deliberately. The test exists so the fallback surface cannot change
without someone noticing.

## 5. Update the research document

`docs/research/current-meta-capabilities.md`: add the tool, change its
classification, update the review date, and move anything you confirmed out of
the "community-reported, unverified" section.

Record what you **verified**, not what you assume. If you saw the tool but did
not call it, say so.

## 6. Open a pull request

Title: `Capability refresh YYYY-MM-DD`.

Include: which tools you introspected, what changed, which gaps closed, which
registry entries and tests changed, and what you verified versus assumed.

**Do not auto-merge.** A capability map change alters routing for every user of
the project.

## Removing a deprecated fallback

Once a release has shipped with the deprecation:

1. Confirm the MCP path has been used in practice, not just declared.
2. Delete the fallback module and its CLI subcommand.
3. Delete its tests.
4. Remove `fallback_provider` from the registry entry.
5. Note the removal in `CHANGELOG.md` under a breaking-changes heading if the
   CLI surface shrank.

The fallback shrinking is the project working as intended. See
[ADR-002](../architecture/adr/ADR-002-api-fallback.md).

## Adding a new gap

Growing the fallback needs justification. A PR that does must state:

1. Which MCP tool you checked.
2. Why it is insufficient - with the error or the missing field.
3. Why the capability matters enough to carry the maintenance cost.

"Easier this way" is not a reason.

## Automation, and its limits

`.github/workflows/upstream-check.yml` watches the dependencies we *can* watch:
`facebook-business`, the Codex and Claude Code plugin formats, and the community
projects we track in `upstreams.yaml`. It opens or updates an issue on change
and never auto-merges.

It cannot watch Meta's MCP. That is why this page exists.
