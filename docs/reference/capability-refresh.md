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

Then save the tool list the agent gave you - its names are all that matter,
so pasted text, JSON, or `/mcp` output all work - and compare it with the map:

```bash
meta-ads-agent capabilities --compare tools.txt
```

It reports tools the map routes work to that the session lacks (fix these
first: a skill will reach for them), tools the session has that Meta's
reference did not list, whether each community-reported name exists, and new
tools whose names suggest one of the fallback gaps, while any remain. It exits
1 on any difference and changes nothing.

## 2. Check the gaps specifically

On 2026-11-04 no capability routes to the fallback any more: Meta's MCP
covered all seven former gaps, and their commands are deprecated (ADR-012).
`meta-ads-agent capabilities --gaps` lists them. Two things to check now
instead:

| Check | Why |
| --- | --- |
| Each deprecated fallback's MCP route still exists - `ads_creative_upload_media`, `ads_create_creative` (`video_id`, `cards`, `multi_media`, `placement_customizations`, `object_story_id`, `source_instagram_media_id`), `ads_boost_ig_post`, `ads_update_entity` with `status: DELETED` | the next release deletes the fallback code; a route that went away is a reason to keep it |
| Whether hosts without MCP Apps can upload a local file | the one use left for `api upload-image` / `upload-video` |
| How `ads_activate_entity` describes a draft publish | the descriptions disagreed on 2026-11-04 about the status a published campaign takes |

A new gap - something the skills need that no tool provides - goes through
ADR-002's rule: name the tool checked and why it is insufficient.

## 3. Update the registry

If Meta's reference itself changed, update
`docs/research/current-meta-capabilities.md` first - it carries the sources -
and regenerate the machine-readable inventory from it:

```bash
uv run python scripts/build_mcp_tool_inventory.py
```

CI fails when the two disagree.

Edit `config/capabilities.yaml`:

```yaml
- name: local_video_upload
  preferred_provider: official_mcp     # was api_fallback
  fallback_provider: api_fallback      # kept for one release; this pair is what
                                       # marks the fallback deprecated
  mcp_tools: [ads_creative_upload_media]   # the tool you verified
  last_reviewed: 2026-11-04
  notes: >
    DEPRECATED fallback. Meta's ads_creative_upload_media uploads a video
    from a URL or a local file, verified <date>. `api upload-video` stays for
    one release and is then removed.
```

There is no separate "deprecated" key: an entry whose preferred provider is
the MCP and whose fallback is still `api_fallback` is a deprecated fallback
(`capabilities --gaps` counts them), and its note must say `DEPRECATED`.

When Meta **removes** a tool, the other direction: take the name out of the
research document and the entry's `mcp_tools`, and if nothing else does the
job set `preferred_provider: none` with a note saying where the user does it
instead. `upload_customer_list` (2026-11-11) is the worked example.

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
