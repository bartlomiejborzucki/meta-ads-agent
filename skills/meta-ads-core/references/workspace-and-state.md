# Brand workspace and campaign state

## The workspace

`.meta-ads/` in the user's project. Private by default (it gets its own
`.gitignore`), and never inside the installed plugin - plugin directories hold
code and get wiped on reinstall.

`meta-ads-agent init` creates it from the templates in this skill's
[assets/](../assets/) directory. Those templates are the same files the CLI
ships, so with no CLI you can write them out yourself and lose nothing.

```
.meta-ads/
  brand.yaml              defaults, naming, DSA, the user's own thresholds
  voice.md                brand voice, free-form prose
  account.yaml            cached account facts. A cache. Meta is authoritative.
  accounts/<act_id>.yaml  the same, one per account, when the workspace has several
  offers/<slug>.yaml      reusable offer briefs
  assets/manifest.json    local fingerprint -> remote image hash / video id
  campaigns/<slug>/
    plan.yaml             intent
    state.json            what exists on Meta
    creatives.json        creative detail as built
    qa.md                 preview QA notes
    report.md             latest report
  reports/                account-level reports
  actions.jsonl           append-only audit log
```

Read `brand.yaml` before planning and `voice.md` before writing copy. Keep them
separate: the campaign engine does not care about tone, and the copywriter does
not care about billing events.

Nothing in `brand.yaml` is required. Most of it is discoverable from Meta, and
a cached copy of a discoverable value invites drift. Prefer reading from Meta;
use the config for what Meta cannot tell you - voice, banned phrases, claims
policy, DSA beneficiary, the user's own thresholds.

## Sources of truth

| Question | Authority |
| --- | --- |
| What did the user intend to build? | `plan.yaml` |
| What exists, and what are its ids? | `state.json` |
| What are this brand's defaults and voice? | `brand.yaml`, `voice.md` |
| Which local file maps to which remote id? | `.meta-ads/assets/manifest.json` |
| **What is the account's actual state?** | **Meta. Always.** |

## The plan

Write it before meaningful writes. Validate it. Fix every error.

```bash
meta-ads-agent validate-plan .meta-ads/campaigns/<slug>/plan.yaml
```

Exit codes: `0` valid, `1` blocked by an error, `2` the file could not be
parsed. Warnings do not block - they are things a human should see, not things
Meta will reject.

Once it validates, **execute the plan, not the conversation.** The plan is what
the user reviewed.

Schema and every field: the annotated `campaign-plan.yaml` in the
`meta-ads-campaign` skill's `assets/` directory -
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-campaign/assets/campaign-plan.yaml>.

## State, and why it is flushed constantly

Record each id **the moment it exists**, before starting the next write. An id
that exists on Meta but not on disk is an orphan, and the next run will create
a duplicate.

`state.json` records, per object: id, type, name, provider (`official_mcp` or
`api_fallback`), plan reference, parent, status at creation, and timestamp. Plus
the current pipeline stage, any failures, and a fingerprint of the plan that
produced it all.

**No secrets in state.** No tokens, no app secrets, no customer data. The
writer scrubs them as a backstop, but they should never get that far.

## Resuming an interrupted build

```bash
meta-ads-agent state <slug>
```

It reports what exists, which stage failed, whether the failure was retry-safe,
and what comes next. Then:

1. Re-read the recorded objects from Meta. Confirm they still exist and still
   look as recorded.
2. If the failed write may have partially applied, search for the object by
   name and parent before creating anything.
3. Continue from the first incomplete stage. Do not restart.

If the plan changed after objects were created, the tool blocks the resume.
That is correct: continuing would apply a different plan to existing structure.
Either restore the plan that produced them, or start a new slug.

## Reconciliation

Before mutating anything from saved state, re-read it from Meta.

If they disagree - a different status, a different name, a missing object -
**report the mismatch and stop.** The user may have changed it in Ads Manager,
another tool may have touched it, or Meta may have changed it itself
(rejection, spend limit reached). Their change wins until they say otherwise.
Silently overwriting a human's edit is the worst thing this tool could do.

## Assets

Local files are fingerprinted by content (SHA-256) and mapped per ad account to
a remote image hash or video id. A renamed file is the same asset; the same
bytes are uploaded once, ever.

This is why a retried build does not re-upload a 200MB video, and why one file
never becomes two Meta objects - which would make later reporting ambiguous.

## The action log

`.meta-ads/actions.jsonl`, one JSON object per line: timestamp, host,
operation, capability, risk level, provider, resource, before and after
summaries, result, and whether approval was noted.

It lets the user answer "what did this thing do to my account" without trusting
a transcript. It records actions, not reasoning, and never credentials or
customer data.

## Privacy

The workspace holds ad account ids, performance exports, creative assets, and
campaign state. It is gitignored by default. Do not commit reports, exports, or
customer audience files. If the user wants to version part of it, that is their
call to make deliberately - not a default.
