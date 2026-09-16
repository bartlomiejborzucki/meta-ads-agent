# ADR-006: The Meta MCP connection is user-owned, not bundled

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Both host plugin formats can bundle an MCP server. Codex plugins declare `mcpServers` pointing
at an `.mcp.json`; the Airtable example in `openai/plugins` ships
`{"type": "http", "url": "https://mcp.airtable.com/mcp", "oauth": {"client_id": "<...>"}}`.
Claude Code plugins support a bundled `.mcp.json` too. Bundling would be the smoothest
onboarding: install the plugin, the Meta server appears.

It does not work for Meta. Per Meta's get-started documentation the OAuth client id is the
**Meta App ID of an app the user controls**, and the redirect URL must be registered in that
app's Facebook Login settings to match the MCP client being used. Claude Code's own command
takes it as a parameter:

```
claude mcp add --transport http --client-id <META_APP_ID> meta-ads https://mcp.facebook.com/ads
```

There is no value we could ship that is correct for another user. A hardcoded `client_id`
would be wrong for everyone, and host substitution for MCP config covers `command`, `args`,
`env`, `url`, and `headers` — not a nested `oauth.client_id`.

## Decision

Do not bundle a Meta MCP server entry in either manifest. Instead:

- Document a **one-time** connection command per host in
  [docs/getting-started/connect-meta-mcp.md](../../getting-started/connect-meta-mcp.md).
- Ship `integrations/claude/mcp.json` and `integrations/codex/mcp.json` as copy-paste
  templates with the app-id placeholder clearly marked, referenced from the docs and from
  `integrations/README.md`.
- Have `meta-ads-agent doctor` detect whether a Meta MCP server is configured for the
  detected hosts and print the exact command if not.
- Have the core skill tell the agent to verify the connection by listing tools before
  attempting Meta work, and to point at the setup doc if absent.

A reliable documented command beats fragile magic. If Meta later publishes a public client id
or the hosts support dynamic client registration against this endpoint, revisit — that would
be a strict improvement and the docs are the only thing that changes.

## Consequences

**Good.** No broken install for anyone. No credential-shaped value in a public repository. The
connection is plainly the user's, which matches who owns the ad account. `doctor` turns a
confusing absence into a copy-pasteable fix.

**Bad, and accepted.**
- Onboarding is two steps: install the plugin, connect the MCP. Documented as two steps in the
  README quick start rather than hidden.
- Users who have never created a Meta App must create one — for OAuth identity only, not for
  API credentials. This is the one Developer-App requirement our "no developer app needed"
  claim has to qualify, and the getting-started doc says so directly instead of burying it.
- We cannot verify the connection from CI. `doctor` checks configuration presence; only a live
  session proves it works.
