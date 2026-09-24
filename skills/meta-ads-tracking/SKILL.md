---
name: meta-ads-tracking
description: >-
  Inspect and diagnose Meta conversion tracking: pixels and datasets, event
  volume, Event Match Quality, Conversions API setup, custom conversions,
  conversion events, UTM parameters, attribution windows, and the gap between
  clicks and landing page views. Use for "is my pixel working", "why aren't
  conversions tracking", "check my conversion setup", "set up tracking", or
  before choosing a conversion objective.
---

# Tracking and signal quality

**A pixel existing is not evidence that tracking works.** That distinction is
the entire point of this skill, and getting it wrong sends people to fix their
creative when their measurement is broken.

Read-only by default. Pixel rule changes are `update_active` and need approval.
Read `meta-ads-core` first.

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

## Configuration is not evidence

| Question | Tool | What it proves |
| --- | --- | --- |
| Does a dataset exist? | `ads_get_datasets` | **only that an object exists** |
| How is it configured? | `ads_get_dataset_details` | intent, including Conversions API setup |
| **Are events arriving?** | `ads_get_dataset_stats` | **volume actually received, up to 28 days** |
| **Are they matchable?** | `ads_get_dataset_quality` | Event Match Quality, per-key coverage, freshness |
| What custom conversions exist? | `ads_get_customconversions` | definitions |
| What rules are on the pixel? | `ads_pixel_event_read` | event rules |
| What parameters are extracted? | `ads_pixel_parameter_read` | parameter extractors |

Report configuration and evidence as **separate findings**. "A PURCHASE custom
conversion is defined" and "PURCHASE events are arriving" are different claims,
and a user who conflates them will spend weeks optimising against nothing.

## Diagnostic sequence

### 1. Which dataset, and is it the one the ads use?

```
ads_get_datasets          → datasets on the business or account
ads_get_ad_entities       → which dataset each ad set actually references
```

An account with several pixels where the ad sets point at the wrong one is
common, and looks like a tracking failure because it is one.

### 2. Are events arriving?

```
ads_get_dataset_stats     → volume over a window, optionally broken down
```

- Zero events for an optimised-for event is a blocking finding. That ad set is
  optimising against nothing.
- A sudden drop to zero suggests a site change, a consent-banner change, a tag
  removal, or a deploy.
- A gradual decline suggests consent rates, browser restrictions, or an
  audience shift toward more-restricted platforms.

Break down by event source where the tool allows: browser versus server tells
you whether the pixel or the Conversions API is the one that stopped.

### 3. Are events matchable?

```
ads_get_dataset_quality   → Event Match Quality, per-key coverage, freshness
```

Events that arrive but cannot be matched to a person contribute little to
optimisation. EMQ depends on which identifying parameters are sent - email,
phone, name, location, click id, browser id.

Report the score **and the per-key coverage**, because the score alone gives no
action. "EMQ is low" is not actionable; "no email is sent on 80% of PURCHASE
events" is.

Freshness matters too: events arriving days late are less useful to the
optimiser than events arriving in seconds.

### 4. Is the event the ads optimise for the event that fires?

Cross-check the ad set's `conversion_event` and dataset against the events with
actual volume. An ad set optimising for `PURCHASE` on a dataset receiving only
`PAGE_VIEW` and `ADD_TO_CART` will deliver badly, and no creative work fixes
it.

### 5. Do clicks reach the site?

```
ads_get_ad_entities  → link clicks vs landing page views
```

A large gap means people click and do not arrive. Causes: a slow page, a
redirect chain that drops parameters, a consent wall, a broken URL, or the
pixel not firing on the landing page.

This is one of the highest-value comparisons available and it is routinely not
looked at.

### 6. Are UTMs intact?

Check the destination URL in the creative, then confirm the parameters survive
to the landing page. A redirect that strips query parameters breaks the
advertiser's own analytics while Meta's reporting looks fine - so the two
systems disagree and nobody knows which to trust.

`brand.yaml.utm` holds the conventions. Consistency is what makes later
analysis possible.

### 7. Which attribution window?

Record it. Never compare periods measured under different windows - see
`meta-ads-report`. If you cannot determine the window, say so rather than
implying the comparison is clean.

## What you cannot conclude from here

Be explicit about the limits. These tools show what Meta **received**; they do
not show what the browser did.

You **cannot** verify from the MCP alone:

- that the pixel fires correctly on every page
- that the Conversions API is sending the right values
- that deduplication between browser and server events works
- that consent management is configured correctly
- that a specific test purchase was tracked

For those the user needs Meta's Events Manager test tools, a browser
inspection, or their own server logs. **Say that** rather than implying
coverage you do not have. "Events are arriving and EMQ is 6.2" is a true and
useful statement; "your tracking is working" is not one you can make.

## Changing pixel rules

`ads_pixel_event_create`, `_update`, `_delete` and the parameter equivalents
are `update_active` work: they need explicit approval.

- New event rules are created **inactive**. Activating one is a separate step.
- **Deleting a rule can break historical reporting** and any audience or
  optimisation depending on it. Check what uses it first.
- Prefer deactivating to deleting, for the same reason we prefer pausing ads.

## Customer data

If tracking work touches customer data - uploading a list, configuring
server-side events with personal information:

- Explicit instruction only. Never as a step you inferred.
- Confirm a lawful basis and consent.
- Email and phone hashed with SHA-256 before transmission.
- Never log it, never write it to state, never commit the source file.
- Honour opt-outs and suppression lists.

These are the `pii_upload` rules from the shared safety policy, repeated here
because this skill is installable on its own. The full policy lives in the
`meta-ads-core` skill, as `safety-policy.md` under its `references/` -
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-core/references/safety-policy.md>.

## Reporting

```markdown
# Tracking — Acme, dataset 1234567890
Read 2026-09-16

## Configuration        (what is set up)
FACT  Dataset 1234567890 "Acme Web" exists, Conversions API configured.
FACT  Custom conversions defined: PURCHASE, LEAD.
FACT  Ad set "PL broad" optimises for LEAD on this dataset.

## Evidence             (what is actually happening)
FACT  Last 28 days: LEAD 1,240 events, PURCHASE 0 events
      (ads_get_dataset_stats).
FACT  Event Match Quality 4.1/10. Email present on 22% of LEAD events,
      phone on 4%, click id on 96% (ads_get_dataset_quality).

## Findings
1. BLOCKING — no PURCHASE events in 28 days, but a PURCHASE custom
   conversion exists. Any ad set optimising for PURCHASE cannot work.
2. RISK — EMQ 4.1 with email on 22% of events. Optimisation is working from
   weak identity signal.

## Recommendations
1. Determine whether purchases are expected to fire here. If yes, the
   purchase event is not implemented — that is a site fix, not an ads fix.
2. Send hashed email with LEAD events where consent allows. That is the
   single largest EMQ lever available here.

## Not verified
Whether the pixel fires correctly in the browser, whether server events
deduplicate against browser events, and whether consent management is
blocking events. None of that is visible from these tools — Events Manager
test events or a browser inspection would be needed.
```

Detail: [references/signal-quality.md](references/signal-quality.md).
