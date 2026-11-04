# Writing and validating a campaign plan

The plan is the source of truth for **intent**. Once it validates, execute the
plan rather than re-deriving intent from the conversation - that drift is how
an agent builds something the user did not approve.

Schema, with every field annotated:
[../assets/campaign-plan.yaml](../assets/campaign-plan.yaml).

## Where it lives

```
.meta-ads/campaigns/<slug>/
  plan.yaml       intent          ← reviewed by a human
  state.json      outcome         ← written as objects are created
  creatives.json  creative detail
  qa.md           preview QA notes
  report.md       latest report
```

`<slug>` is lowercase letters, digits, and hyphens. It names the directory, so
it must be filesystem-safe.

## The parts that cause mistakes

### Budgets are display amounts

```yaml
budget:
  level: ad_set      # ad_set (ABO) or campaign (CBO). Never both levels.
  type: daily        # daily or lifetime
  amount: 70         # seventy zloty. NOT 7000.
  currency: PLN      # must match the account
```

Conversion to Meta's minor units happens once, at the boundary, in tested code.
Never pre-multiply. Never omit the currency. `validate-plan` reports both the
display amount and the minor-unit value so you can see what will be sent.

A lifetime budget needs an end time - Meta cannot pace spend over an
open-ended period.

### Status is always PAUSED

There is no field for anything else, at any level. Activation is a separate
operation on reviewed objects.

### One asset source per asset

```yaml
assets:
  - local_path: ./creatives/a.jpg   # fingerprinted, uploaded once, cached
  # or
  - image_hash: abc123def456        # already on the account
  # or
  - video_id: "700000000000001"     # already uploaded
```

Exactly one. Two is ambiguous and none is useless.

Relative paths resolve against the **plan's directory**, not the current
working directory, so a workspace is portable between machines.

### Carousels, existing posts, and placement assets

A carousel takes **2 to 10 cards** instead of `assets`, and exactly one copy
variant - its primary text is shared by every card:

```yaml
mode: carousel
destination_url: https://example.com/webinar
cards:
  - asset: {local_path: ./cards/1.jpg}
    headline: Save the Friday
    link: https://example.com/webinar#agenda   # optional; defaults to destination_url
  - asset: {image_hash: abc123def456}
    headline: No more copy-paste
variants:
  - angle: three reasons
    primary_text: Three reasons the report should write itself.
```

Cards keep the order written: Meta's automatic reordering is turned off,
because a carousel that tells a story stops telling it when shuffled.

An existing post is either a Facebook Page post (`post_id: "<page>_<post>"`)
or an Instagram post (`instagram_media_id`, with `instagram_account_id` and
the Page's `page_id`) - exactly one. No assets and no variants: the post runs as published, and keeps
its engagement. Build an Instagram post inline in the ad, not as a separate
creative first - see the `meta-ads-campaign` skill's Creative section.

To serve an asset in one placement only, use `mode: multi_variant` and give
it `placement` - one of `facebook_feed`, `facebook_stories`, `facebook_reels`,
`instagram_feed`, `instagram_stories`, `instagram_reels`. At least one asset
must stay unpinned, to serve everywhere else:

```yaml
mode: multi_variant
assets:
  - local_path: ./square.jpg                   # everywhere else
  - local_path: ./vertical.jpg
    placement: instagram_stories               # only here
```

In any other mode `placement` is refused, because nothing would honour it.
A multi-variant creative takes images or videos, not both, and an asset pinned
to a placement the ad set's manual placements leave out is refused too - it
would never serve.

### Age under Advantage+ audience

With `advantage_audience: true`, Meta rejects a hard `age_max` below 65 or
`age_min` above 25 (tool description, 2026-11-04). Put the ages you are aiming
at in `age_suggestion` - it becomes `targeting.age_range`, a suggestion Meta
can go beyond:

```yaml
targeting:
  countries: [PL]
  advantage_audience: true
  age_suggestion: {min: 30, max: 50}
```

If people outside the range must not see the ad, that is the case for
`advantage_audience: false` with `age_min` / `age_max`, and a `deviations`
entry saying why. The validator warns on either mismatch.

### Spend cap, placements by platform, and deviations

```yaml
campaign:
  spend_cap: {amount: 500, currency: PLN}   # Meta's spend_cap; same currency as budgets
  deviations:
    - setting: placements
      meta_recommends: Advantage+ placements
      reason: the creative is a 9:16 Reel, and nothing else fits it
  ad_sets:
    - placements:
        mode: manual
        platforms: [instagram]              # every Instagram position
```

- **`spend_cap`** stops the campaign at that total. Meta rejected a PLN cap
  below 500 on 2026-11-03 (error 2446307); the validator warns below that.
  Other currencies have no recorded minimum.
- **`platforms`** without `positions` means every position on that platform -
  Feed, Stories, Reels, Explore, profile, search. A hand-picked subset of
  `positions` is for a recorded reason only.
- **`deviations`** lists what the plan does against Meta's advice, and why.
  Ads Manager scores each campaign against Meta's recommendations; a manual
  placement or Advantage+ audience turned off lowers that score on purpose,
  and the entry is what tells a later reader it was a decision.

### `angle` is the concept, not the wording

```yaml
variants:
  - angle: time saved              # the reason someone would care
    primary_text: ...
    headline: ...
    cta_type: SIGN_UP
```

Two variants with the same angle and different phrasing are one idea. The
validator warns when every variant shares an angle, because calling that "three
creative tests" is not true.

### Enum-shaped fields are shape-checked only

`objective`, `optimization_goal`, `cta_type`, `billing_event`,
`special_ad_categories` must be `UPPER_SNAKE_CASE`. Their **values** are not
validated against a local list - Meta's valid sets change every version, and a
local allowlist would reject new values. Discover them with
`ads_get_field_context`.

## Validating

```bash
meta-ads-agent validate-plan .meta-ads/campaigns/<slug>/plan.yaml
```

| Exit | Meaning |
| --- | --- |
| 0 | valid; warnings may be present |
| 1 | blocked by at least one error |
| 2 | the file could not be read or parsed |

Useful flags:

```bash
--json                 machine-readable findings and provider routing
--skip-assets          do not read local files (faster; skips crop checks)
--strict               treat warnings as failure
--account-file PATH    cached account facts
--brand-file PATH      brand config
```

Errors block. Warnings are for the user to see. Do not "fix" a warning by
removing the thing that triggered it.

## Account context

Without account facts, the currency, identity, dataset, and eligibility checks
cannot run, and the report says `account.not_read`. A plan validated with no
account context is **not** a plan cleared for execution.

After reading the account from Meta, cache it in `.meta-ads/account.yaml` - or,
in a workspace that works with more than one ad account, in
`.meta-ads/accounts/<act_id>.yaml`, one per account. `validate-plan` picks the
file for the plan's own `ad_account_id`, and never validates against another
account's facts: an `account.yaml` for a different account is ignored, with a
hint. The
shape is the `account.yaml` template in the `meta-ads-core` skill's `assets/`
directory: <https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-core/assets/account.yaml>. Three fields matter especially:

- `currency_offset` - Meta's own minor-unit multiplier for this account. It
  **outranks** our built-in table.
- `min_daily_budget` - the account's field of the same name, in minor units.
  With it, a daily budget Meta would reject is caught before the first write
  (`budget.below_minimum`) instead of after the campaign already exists.
- `valid_objectives`, `valid_optimization_goals`, `valid_call_to_action_types` -
  discovered enum sets. An **empty** list means "we did not look", so the
  validator skips the membership check rather than rejecting a value it has not
  verified.

## Reading the report

Findings carry a stable `code` so you can reference one precisely.

```
ERROR    dsa.missing_fields    targeting PL requires beneficiary, payor
WARNING  currency.unverified   plan budgets are in PLN, not verified against the account
INFO     budget.resolved       daily budget at ad_set level: 70.00 PLN (7000 minor units)
INFO     plan.deviation        placements differs from Meta's recommendation (Advantage+ placements): ...
```

The `Execution routing` section names which layer performs each step. Since
2026-11-04 every creative mode routes to Meta's MCP; a `routing.fallback`
finding would mean the plan needs the token-based fallback, so tell the user
**before** they need a token halfway through a build.

## Changing a plan after objects exist

The plan's fingerprint is stored with the state. Editing the plan after objects
have been created blocks the resume, because continuing would apply a different
plan to existing structure.

Two honest options: restore the plan that produced them, or start a new slug
for the new plan. There is no third option that does not risk a mismatch
between what the user approved and what exists.
