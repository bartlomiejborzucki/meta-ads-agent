# ADR-011: In Claude Code, a plugin hook enforces the approval classes

- **Status:** accepted
- **Date:** 2026-10-14
- **Revisits:** [ADR-001](ADR-001-mcp-first.md), "advisory by construction"

## Context

[ADR-004](ADR-004-write-safety.md) sorts every operation into an approval
class. [ADR-001](ADR-001-mcp-first.md) accepted that the classes are
**advisory**: Meta's MCP write tools execute at once, the transport belongs to
Meta, and the only way to gate it was a proxy - rejected for breaking the
OAuth story, adding a service, and doubling the failure modes. ADR-001 named
the proxy as "the change to revisit, as an opt-in, if the advisory model
proves insufficient".

Claude Code now offers a third option that ADR-001 did not have. A plugin can
ship `PreToolUse` hooks: a command that sees each tool call, its name and its
input, before it runs, and can answer `deny` (the call does not happen) or
`ask` (the user must confirm it, even in auto mode). Hooks run in the host,
not between the host and Meta, so the OAuth flow, the endpoint and the
server are untouched.

## Decision

**The Claude Code plugin ships a `PreToolUse` hook on Meta's MCP tools that
enforces the approval classes in `config/capabilities.yaml`.**

- Every call to an `ads_*` tool on any MCP server is classed by name, from a
  table generated from `capabilities.yaml` (`hooks/tool-classes.json`). Only
  capabilities whose preferred provider is the official MCP route a tool;
  a fallback capability's list names related reads, not its route.
- A class in `APPROVAL_REQUIRED` (`update_active`, `budget_increase`,
  `activate`, `bulk`, `delete`, `pii_upload`) answers **`ask`**, with a reason
  naming the class and, for an entity update, the status and budget fields it
  would change.
- A create whose input sets a status other than `PAUSED` is **denied**. The
  plan format has no field for anything else, and nothing in this project
  creates live objects.
- An `ads_*` tool the table does not know, whose name is not a read, answers
  `ask`. A new write tool from Meta should meet a question, not silence.
- **Everything else stays silent.** The hook never answers `allow`: that would
  skip the user's own permission rules, and a read approved by the user's
  settings is not this project's to approve.
- The hook is Python with the standard library only, so it works without the
  optional CLI. It never writes tool input anywhere.
- It is on by default in the plugin. `META_ADS_AGENT_HOOKS=0` turns it off.

## Consequences

**Good.**
- In Claude Code with this plugin, an activation, a budget change, a delete
  or a customer-list upload cannot happen without the user seeing a prompt
  for that call, whatever the agent was told or decided.
- No proxy, no service, no change to how the MCP is connected (ADR-006).

**Bad, and accepted.**
- **Codex can only refuse.** Codex loads the plugin's `hooks/hooks.json`
  once the user trusts it in `/hooks`, but treats `ask` as a failed hook
  and runs the call. The hook therefore turns every `ask` into `deny` when
  its input looks like Codex's (`turn_id`, no `permission_mode`), or when
  `META_ADS_AGENT_HOOKS=strict`. In Codex the user makes approval-class
  changes themselves. *(Added 2026-10-14, after a Codex install.)*
- **Agents that read the skills as Markdown stay advisory.** The README says
  which host is which.
- **The hook needs `python3` on `PATH`.** Without it the hook fails as a
  non-blocking error and the call proceeds - back to advisory, with an error
  notice the user can see. Making that failure block every Meta call would
  turn a missing interpreter into a broken plugin.
- **The class comes from the tool name, and `ads_update_entity` covers a
  paused edit, a pause, a live edit and a budget change.** The hook cannot
  see the target's current status, so every `ads_update_entity` call asks. A
  paused edit costs one extra confirmation.
- **The deny rule reads field names Meta does not document.** It looks for
  `status`, `configured_status` and `effective_status` anywhere in the input,
  including inside JSON-encoded strings. A field under another name passes
  silently; Meta's own default for MCP creates is PAUSED.
- **Only MCP calls.** The fallback runs through the shell
  (`meta-ads-agent api ...`). Its writes create inert objects, except
  `api delete`, which refuses without `--approved` and is subject to the
  user's own shell permissions. Hooking every shell command to catch one
  CLI verb would start a Python process on each of them.
- **Users can still override it** - by turning the hook off, or by answering
  yes. That is the point: the decision is theirs, and it is now always made.

## Alternatives rejected

**A proxy in front of the MCP** - rejected in ADR-001, for the same reasons,
and no longer needed for Claude Code.

**`allow` for reads.** It would spare some prompts, and it would also override
a user who has chosen to confirm every Meta call.

**Ship it off by default.** The hook only ever adds a confirmation the skills
already require the agent to ask for. A safety check that most users never
turn on protects few of them.
