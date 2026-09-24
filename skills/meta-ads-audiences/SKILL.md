---
name: meta-ads-audiences
description: >-
  Plan and build Meta (Facebook/Instagram) custom and lookalike audiences:
  choosing a lookalike's source, country and size, website and engagement
  audiences, exclusions, and checking an audience before it is used. Use for
  "build a lookalike", "who should we target", "create an audience from our
  customers", "exclude existing buyers", or "why is this audience so small".
---

# Audiences

Read `meta-ads-core` first. Its safety policy governs everything here.

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

```
ads_get_ad_account_custom_audiences  → what exists already
ads_get_custom_audience              → one audience: size, status, subtype
ads_get_custom_audience_adsets       → where it is used - check before changing it
ads_create_custom_audience           → website, engagement, lookalike, customer file
ads_update_custom_audience           → name, description, rule
ads_update_custom_audience_users     → customer-list members: PII, highest risk
ads_get_help_article                 → Meta's current rules, to quote rather than recall
```

## Look before you build

Most accounts already have the audience someone is about to create. List them
first, and reuse one that fits: a second copy of the same website audience
splits nothing and confuses every later report.

For an audience that exists, read its size and status before relying on it. An
audience still populating, or too small to deliver, is a finding - say so
before it goes into a plan.

## Approval, by what the step changes

| Step | Class | Why |
| --- | --- | --- |
| Listing, reading, sizing | `read` | changes nothing |
| Creating a website, engagement or lookalike audience | `update_active` - explicit approval | no PII and no delivery change by itself, but the capability map classes it here, and it is a new object in their account |
| Attaching an audience to a **live** ad set, or excluding one | `update_active` | delivery shifts the moment it is saved |
| Adding people to a customer-list audience | `pii_upload` | the highest-risk operation on the server - see below |
| Deleting an audience | `delete` | check `ads_get_custom_audience_adsets` first: deleting one in use breaks those ad sets |

## Lookalikes: the source decides everything

A lookalike is Meta finding people who resemble a **source** audience. The
source is the decision; the rest is settings.

**Choose the source by value, not by size.** Purchasers resemble purchasers.
All website visitors resemble people who visit websites. In order of how much
they usually say about a customer:

1. Customers by value or repeat purchase, if the user has that list
2. Purchasers, from the dataset's purchase events
3. Leads that became customers
4. Leads
5. People who engaged deeply - watched most of a video, saved, messaged
6. All website visitors

Recency matters too: last-180-day purchasers describe today's customer better
than all-time purchasers.

**Size the source.** Meta sets a minimum source size and publishes guidance on
what size works well; both have changed over time. Read the current numbers
with `ads_get_help_article` and quote them with the date, rather than stating
them from memory. A source below the minimum cannot be used; one barely above
it produces a lookalike of a handful of people's quirks.

**Country and percentage.** A lookalike is built within one or more
countries, as a percentage of each country's population. Smaller is closer to
the source and smaller in reach; larger is broader and looser. For a first
lookalike, the closest band is the usual starting point, widened only when
delivery is limited. Say what the choice trades, in those words.

**It takes time to populate.** A new lookalike is not ready the moment it is
created. Check its status before building an ad set on it, and do not
activate anything that depends on one still being filled.

### What to propose

```
LOOKALIKE PROPOSAL

Source        Purchasers, last 180 days (dataset 1234567890)
              4,120 people - above Meta's minimum (help article, read 2026-09-24)
Country       PL
Size          1% - closest match, smallest reach
Why           Purchasers describe the customer better than visitors, and
              180 days describes today's customer better than all-time.
Alternative   3%, if 1% under-delivers after the learning phase.

Creating it needs your approval (it is a new audience in your account).
Attaching it to the live ad set "PL broad 25-55" is a separate approval,
because delivery changes when that is saved.
```

## Exclusions

Excluding existing customers from prospecting is usually right and costs
nothing to propose. Two checks first:

- The exclusion audience exists and has populated - an empty exclusion
  excludes nobody, silently.
- The same audience is not also **included** in that ad set. The validator
  refuses an audience that is both (`targeting.audience_included_and_excluded`)
  because it leaves nobody to reach.

## Customer lists: `pii_upload`

A customer-file audience is built from personal data. Everything in the core
safety policy's `pii_upload` class applies, without exception:

- explicit instruction from the user, for this list, now;
- a lawful basis the user has stated - their consent records or legitimate
  interest, not an assumption;
- identifiers hashed before they leave the machine;
- nothing from the list written to a log, a state file, a report, or this
  conversation;
- the source file never committed.

If any of those is missing, stop and say which. There is no fallback for this
path on purpose: one route, maximum scrutiny.

## Before an audience is used

Read back: its size, its status, which ad sets already use it, and for a
lookalike its source and percentage. Put that in the plan, so the user
approves an audience they can see rather than a name.

## Never

- Invent a source-size minimum, a population figure, or a "best" percentage.
  Read Meta's help, or say you have not.
- Treat approval to create an audience as approval to attach it to a live ad
  set. They are two steps.
- Put any member of a customer list anywhere but Meta's upload.
- Delete an audience without checking which ad sets use it.

Audience sizing and source-quality details:
[references/lookalike-sources.md](references/lookalike-sources.md).
