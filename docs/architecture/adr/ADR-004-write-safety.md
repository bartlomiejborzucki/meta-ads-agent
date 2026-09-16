# ADR-004: PAUSED by default, and explicit approval for anything that moves money

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Meta's official MCP has write tools that execute immediately: `ads_update_entity`,
`ads_activate_entity`, `ads_create_*`. There is no draft mode, no undo, no confirmation
screen. An agent that misreads "set up a campaign for the webinar" as "launch it" spends real
money, and nothing on the platform side prevents that.

The failure is asymmetric. Creating a paused campaign the user did not want costs a minute of
cleanup. Activating one they did not want costs their budget, and can corrupt learning on a
campaign they cared about.

Community projects all *say* "created PAUSED" and "you approve spend". None enforce it, and
several then encode budget-scaling heuristics with the same authority as platform rules.

## Decision

**Risk classes.** Every operation is classified, and the class determines what is required
before it runs:

| Class | Requires |
| --- | --- |
| `read` | nothing |
| `create_paused` | the user asked for something to be built |
| `update_inactive` | the user asked for the edit |
| `update_active` | explicit approval, if it can change delivery or spend |
| `budget_increase` | explicit approval, with current and proposed shown in account currency |
| `activate` | explicit approval, after preview and QA |
| `delete` | explicit approval, plus a stated reason pause is insufficient |
| `bulk` | the affected entities listed first, then approval |
| `pii_upload` | explicit instruction and a lawful basis |

**Paused by default.** Campaigns, ad sets, and ads are always created PAUSED. Meta's create
tools already do this; we never override it, and we never pass an active status at creation.

**Launch is still staged.** Even when the user says "launch it", the order is build → preview →
QA → *then* ask to activate. Activation is a separate operation on reviewed objects.

**Approval must be specific.** "Yes go ahead" given while planning is not approval to spend.
Approval names the entity and the change. Vague enthusiasm is never treated as permission.

**Never silent about money.** Any budget, bid, schedule, or status change is reported with the
old and new values, in the account's currency, read from Meta — not assumed.

**Prefer pause to delete.** Deleted objects lose their optimisation history permanently;
paused objects keep it. Delete is a guarded last resort, and the agent must say why pausing is
not enough.

**The fallback obeys the same rules.** `meta-ads-agent api` is not a bypass. Destructive and
spend-affecting commands support `--dry-run`.

## Consequences

**Good.** The expensive mistakes require a human sentence. Reviewing a paused structure is
cheap and previews make it concrete. Users can hand the agent a vague brief without risk.

**Bad, and accepted.**
- **The model is advisory.** Because the write tools belong to Meta's server, a
  sufficiently confused agent can still call `ads_activate_entity`. We shape behaviour with
  skills; we cannot enforce it in a transport we do not own. This is stated in the README
  rather than glossed over, and it is the argument a future opt-in proxy would have to answer
  (see [ADR-001](ADR-001-mcp-first.md)).
- More turns to launch. Intended.
- A user who wants one-shot autonomous launching will find this annoying. Also intended;
  profiles adjust verbosity and test counts, never the approval gates.

## Alternatives rejected

**Trust the user's phrasing.** "Launch this" is ambiguous in exactly the case where being
wrong is most expensive.

**A global `--yes` / autonomous mode.** One flag to undo the project's main safety property.

**Enforce via hooks that block MCP write tools.** Considered for Claude Code, whose hooks can
gate tool calls. Rejected for 0.1.0 as host-specific (no Codex equivalent), brittle against
tool renames, and in tension with [ADR-003](ADR-003-dual-agent-packaging.md). Worth revisiting
as an optional host-specific hardening layer.
