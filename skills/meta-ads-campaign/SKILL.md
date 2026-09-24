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
read `meta-ads-core` first if it is installed; this skill repeats the parts
it cannot work without.

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
carousel creatives, deletion, and the `report` arithmetic (which has a by-hand route).
<!-- shared:preflight end -->

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

`.meta-ads/campaigns/<slug>/plan.yaml`. Schema and every field, annotated:
[assets/campaign-plan.yaml](assets/campaign-plan.yaml).

Budgets are **display amounts** with a currency - `70` and `PLN`, never `7000`.
Statuses are PAUSED; there is no field for anything else.

Names follow the brand's conventions: copy the `naming` templates from
`brand.yaml` into the plan's names as written - `{brand} | {objective} |
{date}`, `{audience}`, `{variant}` - and let the CLI expand them, together with
the brand's UTM parameters, rather than expanding them yourself:

```bash
meta-ads-agent render-plan .meta-ads/campaigns/<slug>/plan.yaml          # show
meta-ads-agent render-plan .meta-ads/campaigns/<slug>/plan.yaml --write  # save
```

It never overwrites a UTM parameter already in a URL, and `{date}` is the
plan's own creation date, so two builds agree on it. The validator refuses a
name that still contains a token. With no CLI, write the names and URLs out in
full instead, and say that you did.

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

<!-- shared:no-cli-writes start - generated from packaging/shared/no-cli-writes.md by scripts/sync_skill_blocks.py - edit there -->
## Building with no CLI: stop at the plan

Plan validation is the gate between a draft and spent money. It catches what a
careful reader misses: minor-unit currency arithmetic, a budget on exactly one
level, whether the Page, Instagram identity and dataset exist on this account,
EU transparency fields, special-category consistency, and whether each local
asset is the type it claims.

So when the probe says the CLI is absent: write the plan, show it, and **stop
before the first write.** Do not create objects and validate afterwards - a
wrong campaign that already exists, even paused, is much harder to argue with.

Then offer the routes forward, and say which you recommend:

1. **Validate without installing anything**, if `uv` is on their PATH:
   ```bash
   uvx --from "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
     meta-ads-agent validate-plan <plan>
   ```
2. **Install it**, if they will build campaigns again:
   ```bash
   uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"
   meta-ads-agent doctor
   ```
3. **Build it by hand** in Ads Manager from the plan - it is a complete
   specification.
4. **Keep the plan as the deliverable** and continue with the read-only work.

Offering no route forward is not an answer, and neither is quietly proceeding.
<!-- shared:no-cli-writes end -->

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
ingest a file. So this step needs the CLI, and there is no MCP route around
it:

```bash
meta-ads-agent api upload-image ./creatives/a.jpg --account act_...
meta-ads-agent api upload-video ./creatives/a.mp4 --account act_...
```

If the CLI is absent, say so and offer the two real alternatives: upload the
file in Ads Manager and pass the resulting `image_hash` or `video_id`, or
install the CLI with its `[api]` extra. Do not describe the upload as done.

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
| existing Instagram post | fallback - `api create-creative --post --instagram-media-id` (see below) |
| existing Facebook Page post | fallback - `api create-creative --post` |
| several copy variants | fallback - `api create-creative --variants` |
| an asset for one placement only | fallback - `api create-creative --variants --placement` |
| carousel, 2 to 10 cards | fallback - `api create-creative --carousel` |

**An Instagram post is not boosted.** `ads_boost_ig_post` exists, but Meta does
not document whether it can create a paused boost, and everything here is
created paused. So the post becomes an inert creative that a paused ad uses;
it keeps the post's engagement and spends nothing until activation. If the
user explicitly wants a boost, that is an activation - the same approval,
after previews, as any other.

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

Without the CLI, read `state.json` in the campaign directory yourself; it is
plain JSON and records the stage, every id, and the plan fingerprint.

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
