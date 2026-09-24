---
name: meta-ads-preview
description: >-
  Render Meta ad previews across placements (Facebook Feed, Instagram Feed,
  Stories, Reels, and others the campaign targets) and QA them before anything
  is activated - identity, copy, headline, CTA, destination, crops, safe zones,
  truncation, missing assets, and Meta's automatic creative changes. Use for
  "show me previews", "check this before launch", "how will this look on
  Instagram", or as the gate before any activation.
---

# Preview and creative QA

Read-only, and mandatory before activation. Nobody should be asked to approve
spending on an ad they have not seen.

Read `meta-ads-core` first.

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

## Render the placements that matter

```
ads_get_ad_preview   → a preview for an ad or creative in a given placement
```

Preview the placements **the campaign actually targets**. With automatic
placements that means Feed, Instagram Feed, Stories, and Reels at minimum -
previewing Feed alone hides the failure mode that matters most, because Feed is
the placement least likely to break.

For each preview, give the user the `preview_url` as a link. A link they can
open beats a description of what you saw.

If a placement fails to render, say which one and why. A creative that cannot
render in a targeted placement will not deliver there, and that is a finding,
not a glitch to skip past.

## What to check

Per rendered placement. Work down the list; it is ordered by how expensive the
mistake is.

### Identity

- [ ] The Page name and avatar are the intended brand
- [ ] The Instagram handle is the intended account, where IG placements render
- [ ] "Sponsored" appears as expected

Wrong identity is the most embarrassing failure and the easiest to miss,
because the copy is what you are reading.

### Destination

- [ ] The link goes where the plan says
- [ ] UTM parameters are present and correctly formed
- [ ] No unresolved template placeholders (`{{...}}`, `<...>`)
- [ ] The displayed domain is the real destination

### Copy

- [ ] Primary text reads correctly **as truncated**, not as written
- [ ] The first line works alone, because for most readers it will be alone
- [ ] Headline is not cut mid-word
- [ ] Description renders where the placement supports it, and is absent where
      it does not
- [ ] CTA button text matches what happens next
- [ ] No typos, no doubled spaces, no stray markdown

Truncation is the most common real defect. Copy that reads well in a plan and
badly at the cut is a plan that passed review and an ad that does not work.

### Visual

- [ ] The image or video is present, not a placeholder
- [ ] The crop keeps the subject in frame at this aspect ratio
- [ ] Text in the creative is legible at rendered size
- [ ] Nothing important sits under a safe-zone overlay - in Stories and Reels,
      UI covers the top and bottom
- [ ] Video: the first frame is not a black or blank frame
- [ ] Video: it makes sense with the sound off

A 1:1 image in Stories crops to the centre and loses the top and bottom. A logo
in the top-right of a Reel lands behind the interface. Both are invisible in a
plan and obvious in a preview.

### Meta's automatic changes

- [ ] Compare the rendered creative against the plan's `advantage` settings
- [ ] Note any enhancement Meta applied that the plan did not declare
- [ ] Flag added overlays, altered crops, brightness or text changes

Meta may alter creative automatically. Users should not discover that here -
but if they are going to, this is where.

## Using vision

If you can look at rendered previews as images, do. Reading a preview is
categorically better than reading a description of one, and crop, legibility,
and safe-zone problems are visual problems that do not survive being put into
words.

Describe what you actually see, and separate observation from judgement:

```
FACT            Instagram Stories preview: the headline text sits in the
                bottom 15% of the frame, overlapping the swipe-up area.
INTERPRETATION  It will be partly obscured by the interface on most devices.
RECOMMENDATION  Move the text above the lower sixth, or supply a 9:16 asset.
```

## Writing it up

`.meta-ads/campaigns/<slug>/qa.md`:

```markdown
# QA — acme-webinar-q4
Rendered 2026-09-16, ad 120210000000123 (PAUSED)

## Placements rendered
- Facebook Feed          ok
- Instagram Feed         ok
- Instagram Stories      1 issue
- Instagram Reels        ok

## Issues
1. Instagram Stories — headline overlaps the swipe-up area.
   The asset is 1:1 and crops to the centre.
   Fix: supply a 9:16 asset, or exclude Stories.

## Verified
- Identity: Acme Sp. z o.o. / @acme
- Destination: https://acme.example.com/webinar?utm_source=meta&...
- Primary text truncates after "...the weekly report." — reads correctly
- CTA: Sign Up, matches the registration page

## Verdict
Not ready. One placement issue to resolve before activation.
```

Then set the state stage to `previewed`, and to `qa_passed` only if it actually
passed.

## The gate

State the verdict plainly: **ready for approval** or **not ready, because X**.

Do not soften a real problem into a note. The whole point of this stage is that
it is cheaper to fix now than after the budget has spent. And do not ask for
activation approval while an issue is open - if the ad needs fixing, say that
instead.

## Previews are not delivery

A clean preview means the creative renders and the configuration is coherent.
It does not mean the ad will be approved by Meta's review, that the landing
page works, that tracking fires, or that the offer will convert.

Check `ads_get_errors` for delivery-blocking problems, and use
`meta-ads-tracking` for the signal side. Previews cover the creative, and
saying so is more useful than implying broader coverage.

Placement specifics:
[references/placement-qa.md](references/placement-qa.md).
