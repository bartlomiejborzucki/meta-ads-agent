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
or an Instagram post (`instagram_media_id`, with `instagram_account_id`) -
exactly one. No assets and no variants: the post runs as published, and keeps
its engagement.

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
INFO     routing.fallback      creative mode single_video will use the Business SDK fallback
```

The `Execution routing` section names which layer performs each step, so you
can tell the user where the fallback is involved **before** they need a token
halfway through a build.

## Changing a plan after objects exist

The plan's fingerprint is stored with the state. Editing the plan after objects
have been created blocks the resume, because continuing would apply a different
plan to existing structure.

Two honest options: restore the plan that produced them, or start a new slug
for the new plan. There is no third option that does not risk a mismatch
between what the user approved and what exists.
