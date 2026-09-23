---
name: meta-ads-creative
description: >-
  Generate genuinely different creative angles, hooks, primary text, headlines,
  descriptions, and CTAs for Meta (Facebook/Instagram) ads, constrained by the
  brand's voice, banned phrases, and claims policy. Use for "write me three
  angles", "new ad copy", "variations on the winning ad", "creative concepts
  for this offer", or when a campaign build needs copy.
---

# Creative: angles and copy

Three genuinely different reasons someone would care beat thirty rewordings of
one. Read `meta-ads-core` for the safety model; this skill writes, it does not
create objects.

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

## Read the constraints first

| Source | What it gives you |
| --- | --- |
| `.meta-ads/voice.md` | tone, vocabulary, examples the user likes and dislikes |
| `.meta-ads/brand.yaml` | `banned_phrases` (hard bans), `claims_policy` (binding), `profile` |
| `.meta-ads/offers/<slug>.yaml` | audience, problem, outcome, **proof**, restrictions, CTA |
| `ads_library_search` | what the category is already saying - via `meta-ads-research` |

If `voice.md` exists, it governs. If it does not, ask for two or three ads or
emails the user likes; examples calibrate tone far faster than adjectives.

## Never invent evidence

**You may cite only proof that exists in the offer brief or that the user
supplied.** No invented:

- results or percentages ("cut reporting time by 80%")
- customer counts ("trusted by 10,000 teams")
- testimonials or named customers
- scientific or medical claims
- product capabilities the product does not have
- awards, certifications, or rankings

If the offer has no proof, write copy that does not need any. Specificity can
come from the *problem* rather than from a number - "the Friday afternoon that
disappears into the weekly report" is concrete and requires no evidence.

A fabricated ad claim is a legal and reputational problem for the user, not a
creative flourish. If you find yourself wanting a statistic, ask for one.

`claims_policy` in `brand.yaml` is binding. `restrictions` in the offer brief
is binding. `banned_phrases` must not appear verbatim.

## Structure

Separate the layers. They are edited independently and they fail
independently.

| Layer | What it is |
| --- | --- |
| **Angle** | the *reason* someone would care. The concept. |
| **Hook** | the first line that earns the second. |
| **Primary text** | the body. Shown truncated in most placements. |
| **Headline** | short, below the image. Often the only thing read. |
| **Description** | optional, shown in some placements only. |
| **CTA** | Meta's enum. Discover valid values with `ads_get_field_context`. |

Front-load the primary text: Feed truncates it, and the "see more" cut lands
early. Say the thing that matters before the fold.

## Angles have to actually differ

An angle is a different **reason to care**, not a different sentence about the
same reason.

Distinct angles for one offer:

| Angle | The reason |
| --- | --- |
| Time recovered | the hours the work currently costs |
| Error risk | what happens when a manual number is wrong |
| Being the bottleneck | the person everyone waits on |
| Cost of the status quo | what the manual process costs annually |

Not distinct - one angle, four rewordings:

- "Save time on reporting"
- "Cut hours from your reporting"
- "Stop wasting time on reports"
- "Reporting shouldn't take hours"

If you produce the second kind, say so: *"these are four executions of one
angle, not four angles."* The plan validator warns when every variant shares an
angle, and calling rewordings a creative test produces a test that cannot teach
anything.

For a genuine test, vary **one** layer at a time. Different angles with the
same image tests messaging. The same copy on different images tests visuals.
Changing both tells you which combination won and nothing about why.

## How many

| Profile | Angles |
| --- | --- |
| `conservative` | 2 |
| `standard` | 3 |
| `experimental` | 4-5 |

Fewer, better-differentiated angles beat more variants. Each angle needs enough
budget to produce a readable result - see the volume floors in
`brand.yaml.thresholds`. Splitting a small budget across five angles produces
five inconclusive results.

## Output format

Give the user something they can review, then hand the chosen variants to
`meta-ads-campaign` as plan input.

```
ANGLE 1 — Time recovered
  Hook           Friday afternoon, gone again.
  Primary text   ...
  Headline       Stop rebuilding the weekly report
  Description    ...
  CTA            SIGN_UP
  Proof used     none - this angle asserts nothing measurable
  Test intent    does the time framing beat the risk framing

ANGLE 2 — Error risk
  ...
  Proof used     "340 attendees at the last session" (offer brief)
```

Always state what proof each angle relies on. It makes an unsupported claim
visible before it ships, and it shows the user exactly which claims they are
vouching for.

## Placement matters to copy

- **Feed** - primary text truncates early. Headline carries weight.
- **Stories and Reels** - vertical, sound often off, text overlay competes with
  UI. Short.
- **Right column** - image and headline only, tiny.

`meta-ads-preview` will show you the actual truncation. Do not guess at it -
count characters if you must, but the preview is the evidence.

## Existing posts

When the user wants to promote a post that already exists, **do not rewrite
it**. Promoting the real post preserves its likes, comments, and shares;
recreating the content as a new dark post starts from zero. If they ask you to
"make an ad from this post", find out which they mean.

## Competitor research

`meta-ads-research` and `ads_library_search` show what a category is saying.
Extract **themes**: angles in use, offers, formats, positioning, what nobody is
saying.

Do not copy a competitor's text or creative. Beyond the legal problem, ads that
sound like the category perform like the category - the gap is usually the
opportunity.

More: [references/angles-and-copy.md](references/angles-and-copy.md).
