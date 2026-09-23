---
name: meta-ads-research
description: >-
  Research competitor and category advertising through Meta's public Ad Library:
  what angles, offers, formats, and positioning are in market, how long ads have
  been running, and what nobody is saying. Use for "what are competitors
  running", "show me ads in this category", "creative inspiration", "Ad Library
  research", or before generating creative angles for an unfamiliar market.
---

# Ad Library research

Read-only, public data. Read `meta-ads-core` first.

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
local image and video upload, video / existing-post / multi-variant
creatives, deletion, and the `report` arithmetic (which has a by-hand route).
<!-- shared:preflight end -->

```
ads_library_search   → search the public Meta Ad Library
```

## What this is for

Understanding what a market is already saying, so the creative you write is
positioned against it rather than accidentally identical to it.

**Extract themes. Do not clone.**

| Extract | Do not take |
| --- | --- |
| Angles in use - the reasons being offered | headlines or body copy, verbatim or lightly reworded |
| Offer structures - trial, discount, bundle, demo | images, video, or design |
| Formats - static, video, carousel, UGC style | brand names, logos, or trademarks |
| Positioning - who they claim to be for | claims, statistics, or testimonials |
| Longevity - ads running a long time | a competitor's specific creative concept |
| **Absences** - what nobody is saying | |

Two reasons the distinction matters. Copying creative is a legal problem -
someone else's ad is their copyrighted work. And ads that sound like the
category perform like the category: the gap is usually where the opportunity
is, not the crowd.

A competitor's claim is theirs to substantiate, not yours to borrow. If a
competitor says "cut costs 40%", you may not say it. You have no evidence for
it, and it is their number.

## Reading the results

### Longevity is the most useful signal available

The Ad Library shows how long an ad has been running. A long-running ad is the
closest thing to a public performance signal you can get, because advertisers
do not keep paying for ads that lose money.

Caveats that keep it honest: a large advertiser may run an ad for brand reasons
regardless of performance, a small advertiser may simply not be watching, and
you cannot see spend. So it is evidence, not proof.

### Volume is not quality

Twenty variants of one ad means the advertiser is testing, not that the ad
works. Judge concepts, not counts.

### You cannot see performance

No spend, no CTR, no conversions, no cost per result. Anyone claiming to know
which competitor ad is "winning" from the Ad Library is inferring from
longevity. Say so when you do it.

## A useful search pattern

1. **Direct competitors** by advertiser name. What they lead with, and how long
   the current set has run.
2. **Category terms** by keyword. Who else is in this auction, including
   advertisers the user has not thought of.
3. **Adjacent categories** solving the same problem differently. Often where
   the unclaimed angles are.
4. **Geography.** The Ad Library is region-scoped, and a market can look
   entirely different in another country.

Then look for the absence. If every ad in a category leads with price, the
angle nobody is using is available.

## How to report it

```markdown
# Ad Library — project management tools, PL, 2026-09-16

## Angles in market
1. Price / value          — 6 of 11 advertisers lead with it
2. Integration breadth    — 3
3. Speed of setup         — 2
4. Team visibility        — 1

## Long-running (likely working)
- <Advertiser A> — running 94 days, "onboarding in an afternoon".
  Angle: speed of setup. Format: 30s screen recording, captions, no voiceover.
- <Advertiser B> — running 61 days, free-trial offer, static with product UI.

## Formats
Static product screenshots dominate (8 of 11). Two use screen recordings.
None uses talking-head or UGC-style video.

## Nobody is saying
- What it costs to keep doing this manually
- Anything about the person who currently owns the spreadsheet
- Anything aimed at the team rather than the buyer

## Read on this
INTERPRETATION  The category competes on features and price. The cost-of-
                status-quo angle is unclaimed here, and it needs no
                competitive claim to make — which means we can run it
                without evidence we do not have.
CAVEAT          Longevity is the only performance signal available. No spend,
                no CTR, no conversions. A 94-day ad is probably working, but
                a large advertiser may run one for brand reasons regardless.
```

Describe competitors' angles in your own words. Do not paste their copy into a
report - the report is where "inspiration" quietly becomes duplication.

## Handing off to creative

Pass `meta-ads-creative`:

- the angles in market, and how crowded each is
- the unclaimed angles
- format conventions, and where they are unanimous enough to break
- the offer structures in use

Do not pass competitor copy. The creative skill writes from the offer brief,
the brand voice, and the *gap* - which is the useful output of this research.

## Limits

- Public data only. Not all ads, not all regions, not all time.
- No performance data of any kind.
- Coverage varies by country and by advertiser category.
- An absent advertiser may be advertising and not indexed here.

Say what you searched, in which region, and on what date. Ad Library results
change constantly, so an undated finding is not reproducible - and a research
note nobody can re-check is a rumour.
