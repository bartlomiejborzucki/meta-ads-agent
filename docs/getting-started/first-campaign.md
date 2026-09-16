# Your first paused campaign

A worked walkthrough of what the agent does, so you can recognise it going
right - and notice it going wrong.

Prerequisites: Meta's official Ads MCP connected
([connect-meta-mcp.md](connect-meta-mcp.md)) and, if you want to use a local
image, the optional CLI ([api-fallback.md](api-fallback.md)).

## 1. Set up a workspace

```bash
cd ~/projects/acme
meta-ads-agent init --brand "Acme Sp. z o.o."
```

Creates `.meta-ads/`, private by default - it writes its own `.gitignore`,
because it will hold account ids, performance data, and creative assets.

Fill in what you want to pin:

- `.meta-ads/brand.yaml` - naming, UTM conventions, **DSA beneficiary and payor
  if you advertise in the EU**, your own cost thresholds.
- `.meta-ads/voice.md` - how your brand sounds. Two or three examples you like
  beat a page of adjectives.

Most of `brand.yaml` is optional. Currency, timezone, Pages, and datasets are
read from Meta, and a stale copy is worse than no copy.

## 2. Audit first

```
Audit my Meta Ads account.
```

The agent reads the account, identities, structure, delivery errors, datasets,
audiences, and recent performance, then reports findings labelled **FACT**,
**INTERPRETATION**, and **RECOMMENDATION**, plus a list of what it could not
check.

It changes nothing. An audit that mutates an account is a bug.

Worth doing first because it catches the things that make a new campaign
pointless - no payment method, a dataset receiving no events, a reached spend
limit.

## 3. Ask for a campaign

```
Build a campaign for our webinar. Landing page
https://acme.example.com/webinar, 70 PLN/day, Poland, ages 25-55,
optimise for leads. Use ./creatives/hero.jpg. Three different angles.
Do not launch it.
```

"Do not launch it" is the default, not a special request. Say it anyway the
first time, so you can see for yourself.

## 4. Review the plan

The agent writes `.meta-ads/campaigns/<slug>/plan.yaml` and validates it:

```bash
meta-ads-agent validate-plan .meta-ads/campaigns/acme-webinar-q4/plan.yaml
```

```
INFO     budget.resolved     daily budget at ad_set level: 70.00 PLN (7000 minor units)
INFO     dsa.present         EU delivery to PL with beneficiary 'Acme Sp. z o.o.'
INFO     asset.ok            image hero.jpg: 1200x628, sha256:466af508f1e3...
INFO     routing.local_upload  local files upload through the Business SDK fallback
WARNING  tracking.attribution_unset  no attribution window recorded

VALID: 0 error(s), 1 warning(s), 7 note(s)
```

**Read the plan.** It is the cheapest point to change anything: the budget, the
currency, the audience, the copy, the destination. Once objects exist on Meta,
changing the plan is a bigger deal.

Things to check specifically: the budget amount **and its currency**, the
destination URL, the Page identity, and the angles - three variants with the
same angle are one idea, and the validator will have warned you.

## 5. The build

```
campaign        MCP        120210000000001   PAUSED
ad set          MCP        120210000000045   PAUSED
image upload    FALLBACK   fake_image_hash   (no MCP local-upload tool)
creative        MCP        120210000000089
ad × 3          MCP        ...123 ...124 ...125   PAUSED
```

Each id is written to `state.json` the moment it exists. If the build fails
halfway, `meta-ads-agent state <slug>` tells you what exists and where to
resume - it will not create a second campaign.

## 6. Previews

The agent renders the placements the campaign targets and gives you links:

```
Facebook Feed        ok
Instagram Feed       ok
Instagram Stories    1 issue — headline overlaps the swipe-up area
Instagram Reels      ok
```

**Open them.** This is the last cheap checkpoint. The Stories issue above is
typical: a 1:1 image crops to the centre and the text ends up under the
interface. Invisible in a plan, obvious in a preview.

Notes land in `.meta-ads/campaigns/<slug>/qa.md`.

## 7. Nothing is active

```
Created, all PAUSED:
  campaign 120210000000001  "Acme | OUTCOME_LEADS | 2026-09-16"
  ad set   120210000000045  "PL broad 25-55", 70.00 PLN/day
  3 ads    ...123 ...124 ...125

Previews rendered. One issue in Instagram Stories.
Nothing is spending. Want me to fix the Stories crop, or activate as is?
```

Fix the issue, or say:

```
Activate it.
```

Activation is top-down, and the agent verifies each status afterwards. An
active ad under a paused ad set does not deliver.

## 8. Afterwards

```
Compare the last seven days with the previous seven.
Why is the cost per lead going up?
Increase the PL ad set from 70 to 90 PLN/day.
Pause ads A and B.
```

The last two change spend, so they are confirmed against Meta's current values
first - and if the current budget is not what you thought, the agent says so
before changing anything.

## When something goes wrong

```bash
meta-ads-agent state acme-webinar-q4
```

Shows what exists, which stage failed, whether the failure was retry-safe, and
what comes next. A write marked **not retry-safe** means Meta may have applied
it before failing - so the next step is to look, not to retry.

Then tell the agent: *"resume the acme-webinar-q4 build."* It re-reads the
objects from Meta, confirms they match, and continues from where it stopped.

## What you should never see

- Anything created ACTIVE.
- A budget change without the old value, the new value, and the currency.
- An activation you did not explicitly approve.
- A second campaign after a failed build.
- An access token in any output.

If you see any of those, that is a bug worth reporting.
