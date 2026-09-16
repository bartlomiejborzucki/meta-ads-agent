---
name: meta-ads-campaign
description: >-
  Build Meta (Facebook/Instagram) campaigns end to end: turn a brief into a
  validated campaign plan, then create the campaign, ad set, assets, creative,
  and ads - all PAUSED - verify the result, and persist every id so an
  interrupted build can resume. Use for "build a campaign", "create ads from
  this brief", "set up a campaign but don't launch it", "launch this offer", or
  resuming a campaign build that failed partway.
---

# Campaign builder

Everything you create is PAUSED. Activation is a separate, approved step -
read `meta-ads-core` first.

## The pipeline

```
intent → account context → brand/offer context → PLAN → VALIDATE
       → [approval if consequential] → campaign PAUSED → ad sets PAUSED
       → assets → creatives → ads PAUSED → preview → QA
       → report → awaiting approval
```

Never skip validation. Never activate because creation succeeded.

## 1. Gather

Ask only for what you cannot discover. Everything below is discoverable from
Meta or the workspace, so reading first makes the conversation shorter.

**From Meta** (`ads_get_ad_accounts`, `ads_get_user_pages`,
`ads_get_ig_accounts`, `ads_get_datasets`): account id, currency, timezone,
eligibility, Page, Instagram identity, datasets and their event volume.

**From the workspace** (`.meta-ads/brand.yaml`, `offers/<slug>.yaml`,
`voice.md`): naming conventions, UTM templates, DSA beneficiary and payor,
default countries and CTA, banned phrases, claims policy, thresholds.

**From the user**, if still missing: the offer and its landing page, the budget
and whether it is daily or lifetime, the market, the creative assets, and what
counts as a result.

If the offer is vague, write the plan with your assumptions stated in `notes`
rather than interrogating the user. They can correct a plan faster than they
can answer eight questions.

## 2. Choose the structure

Discover current valid values rather than recalling them:

```
ads_get_field_context   → objectives, optimisation goals, CTA types for this
                          account and API version
```

Decisions to make explicitly, and record why in the plan's `notes`:

- **Objective** - follows from what counts as a result. Use current ODAX names
  (`OUTCOME_*`), never a retired objective from an old example.
- **Optimisation goal** - must be valid for the objective. If it optimises for
  conversions, a dataset and an event with recent volume are required.
- **Budget level** - campaign (CBO) or ad set (ABO), never both. Meta rejects
  both, and so does the validator.
- **Audience** - broad or defined. Both are defensible; this is a media-buying
  judgement, not a platform rule, so present it as a choice.
- **Placements** - automatic unless specific creative demands otherwise.
- **Advantage settings** - state them. Meta may alter a creative
  automatically, and the user should not discover that from a preview.

Background, with the uncertainty marked:
[references/objectives-and-optimization.md](references/objectives-and-optimization.md).

## 3. Write the plan

`.meta-ads/campaigns/<slug>/plan.yaml`. Schema and every field:
`templates/campaign/campaign-plan.yaml`.

Budgets are **display amounts** with a currency - `70` and `PLN`, never `7000`.
Statuses are PAUSED; there is no field for anything else.

Show the plan to the user before creating anything. A plan is cheap to change
and a campaign is not.

## 4. Validate

```bash
meta-ads-agent validate-plan .meta-ads/campaigns/<slug>/plan.yaml
```

`0` valid, `1` blocked, `2` unparseable. **Fix every error before the first
write.** Warnings are for the user to see, not for you to suppress.

It checks the account exists and is active and payable, the currency matches,
budgets convert cleanly and sit on one level only, the Page and Instagram
identity exist on this account, the dataset and event exist, the destination is
a reachable public URL, EU transparency fields are present when the plan
targets the EU/EEA, special ad categories are consistent with brand config, and
local assets exist and are the type they claim.

It also reports which layer will perform each step, so you can tell the user in
advance where the fallback is involved.

Pass `--account-file` if you have cached account facts;
[references/campaign-plan-guide.md](references/campaign-plan-guide.md) explains
how to write them.

## 5. Create, PAUSED, recording as you go

Record each id **before starting the next call**. This is what makes a failure
resumable instead of duplicating.

```
1. ads_create_campaign   → record id, stage campaign_created
2. ads_create_ad_set     → record each id, stage ad_sets_created
3. assets                → see below, stage assets_uploaded
4. creative              → record id, stage creatives_created
5. ads_create_ad         → record each id, stage ads_created
```

If a call fails, stop. Do not continue past a failure, and do not retry a write
without querying Meta first - a timeout does not tell you whether the object
was created.

### Assets

A local file needs the fallback; Meta's MCP lists uploaded media but cannot
ingest a file.

```bash
meta-ads-agent api upload-image ./creatives/a.jpg --account act_...
meta-ads-agent api upload-video ./creatives/a.mp4 --account act_...
```

Both are deduplicated by content fingerprint, so a rerun costs nothing. Video
upload waits for Meta to finish transcoding; a creative built against an
unprocessed video is rejected.

If the user already has an `image_hash` or `video_id`, use it and skip the
upload entirely.

### Creative

| Mode | Who does it |
| --- | --- |
| single image | MCP - `ads_create_creative` |
| single video | fallback - `api create-creative --video` |
| existing Instagram post | MCP - `ads_boost_ig_post` |
| existing Facebook Page post | fallback - `api create-creative --post` |
| several copy variants | fallback - `api create-creative --variants` |
| carousel | not supported in 0.1.0 - say so |

Say which one you used and why. Copy and angles come from `meta-ads-creative`.

## 6. Preview and QA

Hand off to `meta-ads-preview`. Render the placements the campaign actually
targets, not just Feed, and check identity, copy, destination, crops, safe
zones, and truncation before anyone is asked to approve spending.

## 7. Report, then ask

Tell the user what exists: every object with its id and status, which layer
created it, the budget in account currency, where the previews are, and what
QA found.

Then ask whether to activate. Explicitly. Once. Activation is top-down -
campaign, then ad set, then ads - and an active ad under a paused ad set does
not deliver.

If they say no, or say nothing, the campaign stays paused. That is a complete,
successful outcome.

## Resuming a failed build

```bash
meta-ads-agent state <slug>
```

It reports what exists, which stage failed, whether the failure was retry-safe,
and what comes next. Then re-read those objects from Meta, confirm they match,
and continue from the first incomplete stage.

If the plan changed after objects were created, the tool blocks the resume -
correctly. Restore the plan that produced them, or start a new slug.

## Regional and regulatory

**EU/EEA delivery** requires DSA transparency fields - beneficiary and payor.
They identify who paid and who benefits, and **they must never be invented**.
Take them from `brand.yaml`, from the account's defaults, or from the user.

**Special ad categories** - credit, employment, housing, social issues,
elections, politics - must be declared. An empty list is a claim the user is
making, not a safe default, and misdeclaring risks account suspension. Never
try to work around a category restriction.

Detail:
[references/special-categories-and-dsa.md](references/special-categories-and-dsa.md).
