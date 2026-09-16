# Special ad categories and EU transparency

Two regulatory areas that are easy to get wrong and expensive to get wrong.
Both are treated as first-class plan fields rather than afterthoughts.

## Special ad categories

Meta restricts targeting for ads about certain subjects. Declaring the category
is mandatory when it applies, and **misdeclaring is an account-suspension
risk**, not a validation warning.

Categories Meta has used: credit, employment, housing, social issues,
elections, and politics. The exact enum values change - discover them with
`ads_get_field_context` rather than hardcoding a list.

### When it applies

Not by industry, but by **what the ad is about**. A bank advertising a graduate
scheme is employment. A landlord advertising a flat is housing. A company
advertising a political position is social issues, even if the company is not
political.

If in doubt: `ads_get_help_article` searches Meta's own Help Center, which is a
better source than your judgement or mine. Then ask the user.

### What declaring does

Targeting options narrow. Age and gender targeting is restricted or removed,
some interest and behaviour targeting becomes unavailable, and certain audience
types cannot be used. Lookalikes may work differently.

This surprises users who expected their usual targeting. Tell them **before**
the build, not when the plan fails validation - it may change the whole
approach.

### Rules

- An empty `special_ad_categories` list asserts none applies. That is a claim
  the user is making. If the offer looks like it might qualify, ask.
- `brand.yaml`'s `special_ad_category` declares a standing category. If it is
  set and the plan omits it, validation blocks - correctly.
- **Never try to work around a category restriction.** Not with creative
  wording, not with a different objective, not by omitting the declaration.
  There is no version of that which ends well.
- If Meta rejects an ad for a category reason (error 1359188), the fix is to
  declare the category, not to rephrase the ad.

## EU / EEA transparency (DSA)

Ads delivered in the EU or EEA need transparency fields naming who paid for the
ad and who benefits from it.

| Field | Meaning |
| --- | --- |
| `beneficiary` | the legal entity whose product or service is promoted |
| `payor` | the legal entity paying for the ad |

They are often the same entity. They are often not - an agency may be the
payor with the client as beneficiary.

### Which countries

The validator treats all 27 EU member states plus Iceland, Liechtenstein, and
Norway as requiring the fields. A plan targeting any of them without both
fields is blocked.

### Never invent them

A wrong beneficiary is a compliance problem, not a typo. Three acceptable
sources, in order:

1. `.meta-ads/brand.yaml` under `dsa:` - where the user records them once.
2. The account's own defaults, if Meta exposes them.
3. The user, asked directly.

"I'll use the brand name" is not a source. The legal entity name is frequently
different from the brand name, which is exactly why this is configuration and
not inference.

### Practical flow

```
Does any ad set target an EU/EEA country?
  no  → nothing to do
  yes → is dsa.beneficiary and dsa.payor set in the plan?
          yes → proceed
          no  → is it in brand.yaml?
                  yes → use it, and say so in the plan
                  no  → ask the user, then offer to save it to brand.yaml
```

Offering to persist it matters: asked once, it is a small question. Asked every
campaign, it is friction that leads to someone guessing.

## Other regional regulation

Political and issue advertising has additional requirements in several
countries - authorisation, disclaimers, registration - which vary and change.
This project does not model them.

If the user's ads are political or issue-based, say plainly that this tool does
not handle the authorisation and disclaimer requirements, and point them at
Meta's own policy documentation via `ads_get_help_article`. Do not attempt it
from memory.

## Validation codes

| Code | Meaning |
| --- | --- |
| `special_category.not_declared` | error - brand config declares a category the plan omits |
| `special_category.none_declared` | note - the plan asserts none applies; confirm that is true |
| `dsa.missing_fields` | error - EU/EEA targeting without beneficiary or payor |
| `dsa.present` | note - which entities were used, so the user can check them |
