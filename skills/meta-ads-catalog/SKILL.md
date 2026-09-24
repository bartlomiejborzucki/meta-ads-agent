---
name: meta-ads-catalog
description: >-
  Inspect and prepare a Meta (Facebook/Instagram) product catalog for catalog
  and dynamic ads: catalog and feed health, product issues, product sets,
  pixel and event-source matching, and what must be fixed before a catalog
  campaign can work. Use for "is my catalog healthy", "why are products
  rejected", "make a product set", "set up dynamic ads", or "connect the pixel
  to the catalog".
---

# Catalogs

Read `meta-ads-core` first. Its safety policy governs everything here.

<!-- shared:preflight start - generated from packaging/shared/preflight.md by scripts/sync_skill_blocks.py - edit there -->
## Preflight: two checks, kept separate

Independent questions; never let one answer stand in for the other.

**1. Meta's official Ads MCP - the execution layer.** Look for tools named
`ads_*` in this session. With none, nothing here can reach an account: say so
and help the user connect it - `connect-meta-mcp.md` under `references/` in the
`meta-ads-core` skill, or
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-core/references/connect-meta-mcp.md>.
The local CLI does not replace it.

**2. The local `meta-ads-agent` CLI - optional, usually absent.** Assume it is
missing until this succeeds:

```bash
meta-ads-agent --version
```

"command not found" is the normal answer, not a fault. **Show no
`meta-ads-agent ...` command before that probe has succeeded** - a command that
fails at the user's prompt costs more than the step it saves. Say "that step
needs the optional CLI, which is not installed here" and carry on.

The MCP alone covers audits, reporting, Ad Library research, previews,
tracking, creative, optimisation and the changes that follow; `.meta-ads/`
files can be written directly from the templates in `meta-ads-core`'s
`assets/`. Only these need the CLI: plan validation (so campaign builds),
local image and video upload, video / existing-post / multi-variant /
carousel creatives, deletion, and the `report` arithmetic (which has a
by-hand route).
<!-- shared:preflight end -->

```
ads_catalog_get_catalogs                 → catalogs the business owns
ads_catalog_get_diagnostics              → what is wrong with a catalog, by issue
ads_catalog_get_dynamic_ads_health       → whether it can feed dynamic ads at all
ads_catalog_get_product_feed_details     → a feed: schedule, last upload, errors
ads_catalog_get_product_sets             → product sets, and their filters
ads_catalog_get_product_set_products     → what a set actually contains
ads_catalog_event_source_get_health      → whether pixel events match products
ads_catalog_*_create / _update / _delete → changes: see the approval table
```

Every one of these is an MCP tool. There is no catalog fallback, by design
(ADR-002): the MCP covers catalogs thoroughly, and a second path would only
drift from it.

## Health before anything else

A catalog campaign is only as good as the catalog feeding it. Read in this
order, and stop at the first thing that is broken:

1. **Dynamic-ads health.** If the catalog cannot feed dynamic ads, nothing
   below matters yet.
2. **Diagnostics.** Issues by type and count - missing images, missing
   prices, invalid URLs, disapproved items. Report counts, and the share of
   the catalog each affects.
3. **Feed.** When it last uploaded, whether that upload had errors, and
   whether its schedule matches how often the shop changes. A feed that last
   succeeded a month ago is serving month-old prices.
4. **Event-source match.** Whether the pixel's `ViewContent`, `AddToCart` and
   `Purchase` events carry product ids that match the catalog. Retargeting
   dynamic ads depend on this match; without it they have no one to show
   products to.

```
CATALOG HEALTH - "Acme shop" (1234567890), read 2026-09-24

Dynamic ads      ready
Products         4,820 - 312 with issues (6.5%)
  missing image       201    fix in the feed
  invalid price        87    fix in the feed
  disapproved          24    policy - see each item
Feed             last upload 2026-09-24 06:00, 0 errors, daily
Event match      Purchase 94%, AddToCart 91%, ViewContent 62%
                 ViewContent is low: the product id on product pages does
                 not match the catalog id for a third of products.

Fix first        the ViewContent id mismatch - it limits every retargeting
                 audience built from product views.
```

Separate what is broken (fact) from what it causes (interpretation) from what
to do (recommendation), as the audit skill does.

## Product sets

A product set is a filter over the catalog - by category, brand, price,
availability, or custom labels. Read what a set **contains**, not just its
filter: a filter that looks right can match nothing, or everything.

When proposing a set, show the filter and the product count it would match
today, and whether any live ad set already uses a set with the same purpose.

## Approval

| Step | Class | Why |
| --- | --- | --- |
| Any read, diagnostic or health check | `read` | changes nothing |
| Creating a product set, feed or rule; editing products; connecting an event source | `update_active` - explicit approval | every live catalog ad that reads it changes, without any campaign being touched |
| Deleting a product, set, feed or rule | `delete` | breaks every ad set that uses it; check first |

The trap here is indirect: editing a product set's filter never mentions a
campaign, and still changes what live catalog ads show. Before any change,
say which live ad sets use the set.

## Catalog ads themselves

A catalog (dynamic) ad's creative is a template that fills in each product's
image, name and price. Meta's MCP is not documented to build that kind of
creative, and this project keeps catalogs MCP-only, so **catalog ads cannot be
built through this tool yet.** Say so plainly. What this skill can do is make
the catalog and product sets ready, so that building the ad in Ads Manager is
the last step rather than the first of several.

## Never

- Change a product set, feed or product without saying which live ads read it.
- Report a catalog as healthy from the product count alone.
- Promise a catalog ad build. It is not supported yet.

Diagnostics in more detail: [references/catalog-health.md](references/catalog-health.md).
