# ADR-001: The official Meta Ads MCP is the primary execution layer

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Meta ships a first-party MCP server at `https://mcp.facebook.com/ads`. A survey of eleven
community projects ([ecosystem audit](../../research/ecosystem-audit.md)) found six of them
are Marketing API clients — most predating the first-party server, several still growing.

Meta's documented tool inventory covers accounts, pages, Instagram identities, campaign / ad
set / ad lifecycle, single-image creatives, ad previews, entity search and insights, seven
insight-analysis tools, custom audiences, datasets and pixel rules, 34 catalog tools,
experiments, activity logs, delivery errors, and Ad Library search — roughly 90 tools.

It also authenticates through Meta OAuth in the browser. A user needs no access token and no
app secret — only a Meta App ID, used as the OAuth client id.

The server is generally available: any app registered on Meta's developer dashboard can
connect. Acting on another business's accounts needs Advanced Access to
`ads_mcp_management`; operating your own does not.

## Decision

The official MCP is the primary and default execution layer for everything it covers. The
agent connects to it directly. This project adds no proxy, no wrapper server, and no
alternative client for covered capabilities.

## Consequences

**Good.**
- A default install requires no credentials at all. Nothing to leak, nothing to rotate,
  nothing to explain before the first audit runs.
- Meta maintains the API surface. Objective enums, creative fields, targeting rules,
  Advantage+ behaviour, and version migrations stop being our problem.
- New Meta capabilities arrive without a release from us.
- We get to spend our effort on the layer nobody has built: plans, validation, state,
  resumability, approval gates, brand context, diagnosis.

**Bad, and accepted.**
- We depend on a surface with no public source repository and no published schemas. Tool
  names can change without notice. Mitigation: never hardcode tool names in code; keep them
  in a dated reference; instruct the agent to introspect the connected server and to trust a
  platform validation error over any local note.
- Connection state is invisible to us: `doctor` can report that a server is configured, not
  that a session is authorised. The skills therefore make the agent list tools and read the
  account's own eligibility fields before writing.
- Rate limits are undocumented. Community reports suggest they are easy to hit on large
  accounts. The skills therefore ask for aggregated queries rather than per-entity loops, and
  we quote no specific number we cannot verify.
- Meta's MCP has no approval gate of its own — its write tools execute immediately. That is
  precisely why our safety model lives in the skills and not in a transport we control. It is
  advisory by construction, which is a real limitation and stated plainly in the README.

## Alternatives rejected

**Build our own MCP server over the Marketing API.** Six projects already do. It duplicates
what Meta now maintains, requires a token from every user on day one, and needs a release
every time Meta ships a version.

**Wrap the official MCP in our own proxy to enforce guardrails.** Tempting, because it would
make the safety model enforceable rather than advisory. Rejected for 0.1.0: it inserts a
service between the agent and Meta, breaks the OAuth story, doubles the failure modes, and
must be re-tested against every MCP change. If the advisory model proves insufficient in
practice, this is the change to revisit — as an opt-in, not a default.

**Prefer a third-party MCP with broader coverage.** The broadest is BUSL-licensed and its
trust model is worse, not better: it asks users to hand ads credentials to a third party.
