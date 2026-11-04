# Objectives, optimisation goals, and structure

## Discover; do not recall

Meta's objective and optimisation-goal sets change with every API version.
Objectives were consolidated into ODAX (`OUTCOME_*`) names, retired objectives
are rejected, and valid objective/goal pairings shift.

So this file contains **no enum list**. Use:

```
ads_get_field_context   → current objectives, optimisation goals, CTA types,
                          with types, filterability, and supported levels
```

If a call fails with a VALIDATION error that lists supported fields, **that
list wins** over anything written here or remembered from an example.

Current ODAX objective families, as of 2026-09-16, named only so you recognise
the shape: `OUTCOME_AWARENESS`, `OUTCOME_TRAFFIC`, `OUTCOME_ENGAGEMENT`,
`OUTCOME_LEADS`, `OUTCOME_APP_PROMOTION`, `OUTCOME_SALES`. Verify before use.
An objective from a pre-ODAX example will be rejected.

## Choosing an objective

Work backwards from what counts as a result.

| The user wants | Look at |
| --- | --- |
| Purchases on a website | a sales objective with an offsite-conversion goal |
| Leads via a form on their site | a leads objective with an offsite-conversion goal |
| Leads via a Meta instant form | a leads objective with an on-Meta destination - but note we cannot create or read lead forms; the user must supply a form id |
| Traffic to a page | a traffic objective, usually landing-page views over link clicks |
| Reach or recall | an awareness objective |

The common mistake is a traffic objective where the user wants purchases. Meta
optimises for what you asked for, and it is good at it: a traffic campaign will
deliver cheap clicks from people who do not buy. If the user's success measure
is a conversion, the objective should be a conversion objective.

**Conversion objectives require a working signal.** Before choosing one:

```
ads_get_datasets          → which datasets exist
ads_get_dataset_stats     → is the event actually arriving?
ads_get_dataset_quality   → Event Match Quality, freshness
```

Optimising for an event with no recent volume will not deliver. That is a
platform reality, not an opinion, and no creative work compensates for it.

## Budget level

| | Budget on the campaign (CBO) | Budget on each ad set (ABO) |
| --- | --- | --- |
| Meta allocates between ad sets | yes | no |
| You control per-audience spend | no | yes |
| Useful when | you trust Meta to find the winner | you need guaranteed spend per audience, or you are testing |

**Platform constraint:** never both. Meta rejects it and the validator blocks
it.

Which to choose is a **media-buying judgement**, not a platform rule. Present
it as a choice with a recommendation and a reason. Anyone who tells you CBO is
always correct is describing a preference.

## Audience breadth

Broad targeting with a good signal, versus defined interest and audience
targeting. Both work. Which is better depends on the offer, the signal quality,
the budget, and the market.

**This is a heuristic, not a rule.** Do not present "go broad" as platform
guidance. If the user has a view, or `brand.yaml` records one, follow it.

If demographic bounds must actually hold, set `advantage_audience` explicitly.
Left unset, Meta's default may expand beyond the age and gender you specified -
which surprises people who thought they had set a floor.

Under Advantage+ audience, age, gender, interests and custom audiences are
suggestions, and Meta rejects a hard `age_max` below 65 or `age_min` above 25
(tool description, 2026-11-04). The target range goes in the plan's
`age_suggestion`, which becomes `targeting.age_range`. Turning Advantage+
audience off is for a real requirement - people outside the range must not
see the ad, or the ad set must reach only a custom audience - and goes in
`deviations` with that reason. Whether genders can be sent as a suggestion
the same way is not documented; do not invent a field for it.

## Placements

Automatic placements let Meta distribute across surfaces, and it is usually the
right default. Manual placements matter when:

- the creative only works in one aspect ratio
- the user has a specific reason (brand safety, a tested surface)
- you need to know which placements to preview

A 1:1 image in Stories crops badly. That is a creative problem, not a placement
problem - previews will show it, which is why the preview step is not optional.

**When one platform is the point, take all of it.** *Heuristic, default on.*
A Reel promoted for ThruPlay or reach on Instagram needs Instagram, not
Instagram Reels alone: Feed, Stories, Explore, profile and search are cheap
inventory the optimisation will use or ignore on its own. Write
`placements: {mode: manual, platforms: [instagram]}` and no `positions`. A
hand-picked subset is for a reason you can name - the creative breaks
elsewhere, a brand-safety rule - recorded in `deviations`. What it protects
against: a narrower auction, a higher cost per result, and a campaign score
in Ads Manager that drops for "too few placements" (53/100 on one such
campaign, 2026-11-04) with nobody remembering why.

## Advantage / automatic enhancements

Meta can alter a creative automatically: crops, brightness, text tweaks, added
overlays. Surface this in the plan. Users should never learn from a preview
that their creative changed.

`brand.yaml`'s `advantage_defaults` records the user's stance. `None` means
"leave Meta's default", which is itself stated in the plan rather than implied.

## Naming

`brand.yaml` holds templates with tokens: `{brand}`, `{objective}`,
`{audience}`, `{variant}`, `{offer}`, `{date}`. Use them. The same tokens feed
UTM construction, so consistent names are what make a later report groupable
by facet - and an inconsistent account is one where reporting quietly stops
being possible.

## What belongs where

| | Home | Behaviour |
| --- | --- | --- |
| Meta rejects it | the validator | blocks |
| A practitioner's view | this file, labelled | advises |
| This advertiser's policy | `brand.yaml` | blocks if configured |

The reasoning is recorded in [ADR-007](https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/architecture/adr/ADR-007-heuristics-vs-constraints.md).
Do not encode a heuristic as a hard rule, and do not present one as a platform
fact.
