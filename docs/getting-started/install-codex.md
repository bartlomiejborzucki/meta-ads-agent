# Installing on Codex

> **Tested to a lower level than the Claude Code path.** Codex was not
> installed on the machine this release was developed on, so the manifest is
> validated structurally against OpenAI's published `plugin.json` specification
> rather than by a live install. If you hit a problem, please open an issue -
> it is useful information.

## Plugin structure

Codex reads `.codex-plugin/plugin.json`, which points at the same canonical
`./skills` directory as the Claude Code manifest. There is no duplicated skill
content - see
[ADR-003](../architecture/adr/ADR-003-dual-agent-packaging.md).

## Installing

Browse and install plugins from the Codex CLI:

```
/plugins
```

From there you can search, view details, install, and toggle plugins. If your
workspace has imported a GitHub marketplace containing this repository, it
appears in that list.

**Start a new session after installing.** Bundled skills and tools load at
session start.

## Local development install

```bash
git clone https://github.com/OWNER/meta-ads-agent.git
cd meta-ads-agent
```

Then point your Codex plugin configuration at this directory. Consult
`/plugins` and your Codex version's documentation for the current local-load
mechanism - it has changed more than once, so we would rather send you to the
authoritative source than print a stale flag here.

## Next: connect Meta's MCP

Not bundled, and cannot be - see
[ADR-006](../architecture/adr/ADR-006-mcp-connection-is-user-owned.md). Add the
server to your Codex MCP configuration using the template in
[`integrations/codex/mcp.json`](../../integrations/codex/mcp.json):

```json
{
  "mcpServers": {
    "meta-ads": {
      "type": "http",
      "url": "https://mcp.facebook.com/ads",
      "oauth": { "client_id": "<YOUR_META_APP_ID>" }
    }
  }
}
```

Getting an App ID, and why one is needed at all:
[connect-meta-mcp.md](connect-meta-mcp.md).

## Optional: the local CLI

Only for the capabilities Meta's MCP does not expose.

```bash
uv tool install "meta-ads-agent[api]"
meta-ads-agent doctor
meta-ads-agent init
```

`doctor` detects Codex if it is on your `PATH` and checks the Codex
configuration locations it knows about for a Meta MCP entry.

## First run

```
Audit my Meta Ads account.
```

Everything is created PAUSED. Activation, budget increases, and deletion all
require explicit approval.
