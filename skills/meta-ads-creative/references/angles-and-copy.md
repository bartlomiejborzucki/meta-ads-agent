# Angles and copy: working notes

Craft guidance, not platform rules. These are **heuristics** - useful defaults
with reasoning attached, overridable by the user's own judgement or
`brand.yaml`. Nothing here is something Meta enforces. The distinction is
recorded in [ADR-007](https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/architecture/adr/ADR-007-heuristics-vs-constraints.md).

## Finding angles

An angle answers: *why would this specific person care, right now?*

Sources, in rough order of reliability:

1. **The offer brief.** `problem`, `outcome`, and `audience` usually contain
   two or three angles already, unextracted.
2. **The user's own words.** How they described the problem when briefing you
   is often better copy than anything you would generate.
3. **Customer language.** Support tickets, sales calls, reviews, community
   posts. People describe their problems in words that resonate with people who
   have the same problem.
4. **The Ad Library.** What the category says - and, more usefully, what it
   does not.
5. **Invention.** Last, and the weakest.

Prompts that surface distinct angles rather than synonyms:

- What does this cost them *today*, in something other than money?
- What have they already tried, and why did it not work?
- Who else notices the problem - a boss, a client, a partner?
- What happens if they do nothing for another six months?
- What do they believe that is wrong?
- What is the smallest visible symptom of the underlying problem?

Each of those tends to produce a different reason to care, which is what makes
them angles rather than rewrites.

## Hooks

The first line's only job is to earn the second. Front-load it: Feed truncates
early.

Directions that tend to work, with the reason:

- **A concrete moment.** Specific beats abstract because it is recognisable.
- **A number the reader owns.** Their cost, their hours - not your claim.
- **Naming the wrong belief.** Creates a reason to keep reading.
- **The unexpected admission.** Honesty buys attention.

Openings to avoid, and why:

- "Are you struggling with X?" - the reader has seen this a thousand times.
- "Introducing..." - nobody was waiting.
- "In today's fast-paced world..." - says nothing, costs the whole first line.
- A question the reader will answer "no" to - you have lost them.

## Primary text

Front-load. The "see more" cut lands early in Feed and earlier in some
placements. The first sentence has to work alone, because for most readers it
will be alone.

Length is a trade-off, not a rule: short copy gets read, long copy qualifies. A
considered purchase can support length. An impulse offer usually cannot.
Whoever tells you the correct number of characters is describing their own
account, not a platform behaviour.

Do not repeat the headline in the body. It wastes the one line you are certain
gets read.

## Headlines

Short, and specific. The headline is frequently the only text a reader
processes, so it should carry the angle rather than decorate it.

- "Stop rebuilding the weekly report" - carries the angle.
- "The best reporting tool" - carries nothing.
- "Learn more" - the CTA already says that.

## CTAs

Meta's CTA types are an enum, and valid values depend on the objective. Use
`ads_get_field_context` to discover them - do not recall a list.

Match the CTA to what actually happens next. `SHOP_NOW` leading to a webinar
registration is a mismatch, and a mismatch between promise and page is the
cheapest conversion problem to fix.

## Structuring a test

Vary one layer.

| Testing | Hold constant | Vary |
| --- | --- | --- |
| Messaging | image, audience, placement | angle |
| Visuals | copy, audience | image or video |
| Offer | everything above | landing page and offer |

Changing several at once tells you which combination won and nothing about why -
so the next test starts from scratch. That is the real cost, not statistical
purity.

Each variant needs enough volume to produce a readable result.
`brand.yaml.thresholds.min_conversions_for_decision` and
`min_clicks_for_decision` are the user's own floors. Below them, the answer is
**insufficient evidence** - which is a legitimate outcome, not a failure to
analyse hard enough.

## Iterating on a winner

When an angle works, the useful question is *what* worked. New executions of a
proven angle are usually a better bet than a new angle, because you already
know the reason resonates.

- Same angle, new execution - different image, different hook, same reason.
- Same angle, new format - static to video, or the reverse.
- Adjacent angle - the neighbouring reason, if the first is exhausted.

Refreshing an execution and retiring an angle are different decisions. The
signals that tell them apart are `fatigue-signals.md`, under `references/` in
the `meta-ads-optimize` skill -
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-optimize/references/fatigue-signals.md>.

## Voice

`voice.md` governs tone. If it is thin, the fastest way to calibrate is to ask
for two or three ads or emails the user likes and two they dislike, with a
sentence on why. The "why" is the part that transfers.

Hard constraints live in `brand.yaml`:

- `banned_phrases` - must not appear verbatim
- `claims_policy` - binding
- offer `restrictions` - binding

## Things not to do

- Fabricate proof. Ever. It is the one failure with consequences outside the
  ad account.
- Present rewordings as separate concepts.
- Copy a competitor's text or creative.
- Promise an outcome the landing page does not deliver.
- Use urgency that is not real. A fake deadline is a claim.
- Write for the algorithm. Meta optimises delivery; the reader decides.
