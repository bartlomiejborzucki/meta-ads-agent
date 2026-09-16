---
name: meta-ads-core
description: >-
  Foundation for all Meta (Facebook/Instagram) Ads work: how to route between
  Meta's official Ads MCP and the local API fallback, the write-safety and
  approval model, account context discovery, the brand workspace, campaign
  state and resumability, and error recovery. Use whenever a task touches a
  Meta ad account - audits, campaign builds, creative, previews, reporting,
  optimisation, budgets, pausing, activation - and before using any other
  meta-ads-* skill.
---

# Meta Ads: core operating model

Skills reason. Meta's MCP and the Marketing API execute. The user controls
spending.

## Before anything else

1. **Confirm the connection.** List your available tools and look for the Meta
   Ads MCP (tool names begin `ads_`). If it is absent, stop and point the user
   at `docs/getting-started/connect-meta-mcp.md`. Do not offer the API fallback
   as a substitute - it deliberately does not cover what the MCP covers.
2. **Read the account.** `ads_get_ad_accounts`. You need `currency` and
   `timezone` before you can interpret any number, and you should check
   `is_ads_mcp_enabled`, `is_queryable`, and `has_payment_method` before any
   write. An account with no payment method will create objects happily and
   never deliver.
3. **Read the brand workspace** if one exists: `.meta-ads/brand.yaml` for
   defaults and thresholds, `.meta-ads/voice.md` for tone. Run
   `meta-ads-agent init` if the user wants one and there is none.

## Routing: MCP first

```
Does Meta's official MCP have a tool for this?
  yes -> use it
  no  -> is it in the fallback?  meta-ads-agent capabilities --gaps
           yes -> use the CLI, and tell the user which gap you are filling
           no  -> say it is not supported; do not improvise
```

The fallback covers exactly six things today: local image upload, local video
upload, video creatives, Facebook Page existing-post creatives, multi-variant
creatives, and deletion. Everything else is the MCP's job. Never reach for the
fallback because it feels easier - `meta-ads-agent capabilities <name>` will
tell you who owns a capability and why.

When you do use the fallback, say so plainly: *"Meta's official MCP does not
currently expose local video upload, so this step used the Business SDK
fallback."*

Details: [references/execution-routing.md](references/execution-routing.md).

## Safety: the user controls spending

**Never infer permission to spend money from a vague request.**

| Operation | What you need first |
| --- | --- |
| Read anything | nothing |
| Create campaigns / ad sets / ads **PAUSED** | the user asked you to build something |
| Edit a paused entity | the user asked for the edit |
| Edit a live entity in a way that changes delivery | explicit approval |
| Raise a budget | explicit approval, with old and new shown in account currency |
| Activate anything | explicit approval, after preview and QA |
| Delete | explicit approval, plus why pausing is not enough |
| Anything touching many entities | show the list, then get approval |
| Upload a customer list | explicit instruction and a lawful basis |

Everything you create is PAUSED. Meta's create tools already do this; never
override it. Even when the user says "launch it", the order is
**build → preview → QA → ask → activate**. Approval given while planning is not
approval to spend. Approval names the entity and the change.

Prefer pausing to deleting: a deleted object loses its optimisation history
permanently, a paused one keeps it.

Full policy: [references/safety-policy.md](references/safety-policy.md).

## Money

Read the account currency before you interpret a budget. A bare "70" is not
dollars - it is 70 of whatever the account bills in, and on some accounts Meta
expects minor units. Do not do this arithmetic in your head:

```
meta-ads-agent validate-plan <plan>   # reports every budget in both units
```

When you report a budget change, always give the old value, the new value, and
the currency.

## Plan, then apply

For anything consequential:

```
intent → plan → validate → [approval] → apply → verify → persist
```

Write the plan to `.meta-ads/campaigns/<slug>/plan.yaml`, validate it with
`meta-ads-agent validate-plan`, and fix every error before the first write.
Once it validates, **execute the plan, not the conversation** - re-deriving
intent from chat history is how an agent drifts from what the user approved.

## State and resumability

Record every created id in `.meta-ads/campaigns/<slug>/state.json` **the moment
it exists**, before starting the next write. If a build fails halfway, a rerun
must continue, not start over.

Resuming:

```
meta-ads-agent state <slug>     # what exists, and what comes next
```

Then re-read those objects from Meta before touching them. **Local state is a
convenience; Meta is authoritative.** The user may have changed things in Ads
Manager, and their change wins until they say otherwise. If local and remote
disagree, report the mismatch and stop.

More: [references/workspace-and-state.md](references/workspace-and-state.md).

## When a call fails

- Show the Meta error - code, subcode, and message. Do not paraphrase it away.
- Say which stage failed and what already exists.
- **Reads** may be retried with backoff. **Writes** may not be retried blindly:
  a timeout does not tell you whether Meta created the object. Query for it
  first, then decide.
- Do not loop. Meta rate-limits, and a retry storm makes a bad situation worse.

Known errors and what they actually mean:
[references/meta-errors.md](references/meta-errors.md).

## Tool names change

Meta evolves this MCP. Treat
[references/mcp-tool-map.md](references/mcp-tool-map.md) as a dated map, not a
contract, and prefer these in order:

1. What the connected server actually exposes.
2. `ads_get_field_context` for current field metadata and enum values.
3. A platform VALIDATION error - if it lists supported fields, that list wins
   over anything written here.
4. This project's references.

Never hardcode an objective or optimisation-goal list from memory. They change
with every API version.

## Which skill to use

| The user wants | Skill |
| --- | --- |
| "Audit my account", "what's broken" | `meta-ads-audit` |
| "Build a campaign", "create ads from this brief" | `meta-ads-campaign` |
| "Write me three angles", copy, creative concepts | `meta-ads-creative` |
| "Show me previews", pre-launch QA | `meta-ads-preview` |
| "Why is this getting worse", "should I pause this" | `meta-ads-optimize` |
| "How did last week go", period comparisons | `meta-ads-report` |
| "Is my pixel working", conversion setup | `meta-ads-tracking` |
| "What are competitors running" | `meta-ads-research` |

Do not mutate an account during an audit or a reporting request. Analysis,
planning, and mutation are separate activities, and a user asking "how did last
week go" has not asked you to change anything.

## Honesty

Label what you say:

- **FACT** - read from Meta. Cite the tool and the date range.
- **INTERPRETATION** - your reading of the facts. Say what would change it.
- **RECOMMENDATION** - what you would do, and what it assumes.

If the data is too thin to support a conclusion, say **insufficient evidence**
and say what you would need. Do not derive a metric whose inputs are missing
without saying so. Never invent results, statistics, testimonials, or product
capabilities - in analysis or in ad copy.
