# Host integrations

The skills in `skills/` are canonical and host-neutral. Anything host-specific
lives here or in the host manifest - see
[ADR-003](../docs/architecture/adr/ADR-003-dual-agent-packaging.md).

## Layout

| Path | Purpose |
| --- | --- |
| `../.claude-plugin/plugin.json` | Claude Code plugin manifest |
| `../.claude-plugin/marketplace.json` | Marketplace entry, so the repo can be added as a marketplace |
| `../.codex-plugin/plugin.json` | Codex plugin manifest, including the `interface` display block |
| `claude/mcp.json` | Meta MCP config **template** for Claude Code (`mcpServers` JSON) |
| `codex/config.toml` | Meta MCP config **template** for Codex (`[mcp_servers.*]` TOML) |

The two templates are not the same file in two places: the hosts genuinely
disagree about the format. Claude Code reads a `mcpServers` object from JSON;
Codex reads `[mcp_servers.<id>]` tables from `~/.codex/config.toml`, with the
OAuth client id in a nested `[mcp_servers.<id>.oauth]` table.

Both manifests point at the same `./skills` directory. Neither contains skill
content, and neither duplicates the other's logic. A CI check fails the build if
a second directory containing `SKILL.md` files appears anywhere in the
repository.

## Why the MCP server is not bundled

Both plugin formats can ship an MCP server. We do not, for one specific reason:
per Meta's get-started documentation, the OAuth client id for
`https://mcp.facebook.com/ads` is the **Meta App ID of an app you control**, and
the redirect URL must be registered in that app's Facebook Login settings for
the client you are using.

So there is no value we could commit that would be correct for anyone else. A
hardcoded client id would produce a broken install for every user, and host
variable substitution for MCP configuration covers `command`, `args`, `env`,
`url`, and `headers` - not a nested `oauth.client_id`.

A documented one-time command beats fragile magic:

```bash
# Claude Code
claude mcp add --transport http --client-id <YOUR_META_APP_ID> \
  meta-ads https://mcp.facebook.com/ads

# Codex
codex mcp add meta-ads --url https://mcp.facebook.com/ads \
  --oauth-client-id <YOUR_META_APP_ID>
codex mcp login meta-ads
```

Both hosts can pin the OAuth callback port (`--callback-port`, `oauth.callback_port`)
for the case where Meta requires a fixed registered redirect.

Full walkthrough, including creating the app:
[docs/getting-started/connect-meta-mcp.md](../docs/getting-started/connect-meta-mcp.md).

`meta-ads-agent doctor` detects whether a Meta MCP server is configured for the
hosts it can see, and prints the exact command when it is not.

If Meta later publishes a public client id, or if a host supports dynamic client
registration against this endpoint, bundling becomes possible and only the docs
need to change.

## Codex: no per-skill interface metadata

OpenAI's skill documentation describes an optional `agents/openai.yaml` inside
a skill directory, carrying display metadata and declared MCP tool
dependencies. It is optional; `name` and `description` in `SKILL.md` are the
only required metadata, and that is what makes one skills tree serve both
hosts.

We deliberately omit them. Adding host-specific files inside the canonical
`skills/` tree is exactly the divergence ADR-003 exists to prevent, and the
plugin-level `interface` block already provides the display metadata that
matters. If Codex later requires per-skill metadata, it should be generated at
package time rather than committed into `skills/`.

## Adding a third host

1. Add a manifest in the location that host expects.
2. Point it at `./skills`.
3. Add `integrations/<host>/` with a template in that host's own configuration
   format if it differs.
4. Teach `doctor` where that host keeps its configuration, so it can detect the
   Meta connection.

Do not copy or symlink `skills/`. Do not add host-specific content to a skill.
