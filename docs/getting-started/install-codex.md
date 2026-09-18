# Installing on Codex

The nine skills are host-neutral Markdown, so Codex loads exactly the same
`skills/` directory Claude Code does - no Codex-specific copy, no divergence
([ADR-003](../architecture/adr/ADR-003-dual-agent-packaging.md)).

Three things to install, in this order:

| | What | Needed? |
| --- | --- | --- |
| 1 | The skills, as a plugin or a skills directory | yes |
| 2 | Meta's official Ads MCP server | yes - it is the execution layer |
| 3 | The `meta-ads-agent` CLI | only for local uploads and the other gaps |

## 1. Install the skills

### As a plugin

```
/plugins
```

The plugin browser searches configured marketplaces, installs, and toggles
plugins. Press Space on an installed plugin to enable or disable it.

**Start a new session afterwards.** Bundled skills load at session start.

### As a skills directory

Codex reads skills from `.agents/skills/` in the repository you are working in
(searching the current directory, its parents, and the repository root) and
from `$HOME/.agents/skills/` for every project. Symlinking into either works
without any plugin machinery, and is the fastest way to try this or to develop
against it:

```bash
git clone https://github.com/bartlomiejborzucki/meta-ads-agent.git
cd meta-ads-agent

# every project
mkdir -p ~/.agents/skills
for skill in skills/meta-ads-*; do
  ln -sfn "$PWD/$skill" ~/.agents/skills/"$(basename "$skill")"
done
```

For one repository instead, link into `<that repo>/.agents/skills/`. Symlinks
mean an edit to a `SKILL.md` is live in the next session.

Confirm they loaded by typing `$` - the nine `meta-ads-*` skills should be in
the list.

### Using them

Type `$` to pick a skill explicitly:

```
$meta-ads-audit
$meta-ads-campaign
```

Or just describe the work - each skill's `description` is written as trigger
text, so "audit my Meta Ads account" or "build a paused campaign from this
brief" matches without naming a skill. Either way, start with
[`meta-ads-core`](../../skills/meta-ads-core/SKILL.md) loaded: it carries the
routing rules, the approval model, and the state format the others rely on.

### Optional: pin the routing rule in AGENTS.md

Skills load on demand. If you want the safety posture to be always-on in a
particular repository, add three lines to its `AGENTS.md`:

```markdown
## Meta Ads

Use the `meta-ads-*` skills for anything touching a Meta ad account. Prefer the
official Ads MCP over the local CLI. Nothing is activated, no budget is raised,
and nothing is deleted without my explicit approval for that specific thing.
```

## 2. Connect Meta's official MCP

Not bundled, and cannot be: Meta's OAuth client id is the **Meta App ID of an
app you control**, so any value shipped here would be wrong for everyone
([ADR-006](../architecture/adr/ADR-006-mcp-connection-is-user-owned.md)).

```bash
codex mcp add meta-ads --url https://mcp.facebook.com/ads \
  --oauth-client-id <YOUR_META_APP_ID>
codex mcp login meta-ads
```

`codex mcp login` prints the callback URL. Register it in your app's **Facebook
Login for Business** settings, then run the login again - a redirect mismatch is
the most common first-run failure.

Prefer editing config by hand? The same thing in `~/.codex/config.toml`, with
the full template in
[`integrations/codex/config.toml`](../../integrations/codex/config.toml):

```toml
[mcp_servers.meta-ads]
url = "https://mcp.facebook.com/ads"

[mcp_servers.meta-ads.oauth]
client_id = "<YOUR_META_APP_ID>"
```

Then:

```bash
codex mcp list
```

Getting an App ID, the scopes to grant, and why a read-only grant is the one
hard safety guarantee: [connect-meta-mcp.md](connect-meta-mcp.md).

## 3. Optional: the local CLI

Only for the handful of capabilities Meta's MCP does not expose - uploading an
image or video from your filesystem, video / existing-post / multi-variant
creatives, and deletion. `doctor`, `init`, and `validate-plan` are useful on
their own and need no credentials.

```bash
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git#egg=meta-ads-agent[api]"
meta-ads-agent doctor
meta-ads-agent init
```

Not on PyPI yet, deliberately -
[ADR-009](../architecture/adr/ADR-009-distribution.md).

`doctor` detects the `codex` binary on your `PATH` and looks for a
`mcp.facebook.com/ads` entry in `~/.codex/config.toml`.

**Sandbox note.** The CLI writes to `.meta-ads/` in your working directory and
reads local asset files. In Codex's default workspace-write sandbox both are
allowed; in read-only mode `init`, `state`, and any upload will be refused by
the sandbox rather than by us. Network access is needed only for the optional
fallback - `validate-plan` and `state` are entirely local.

## First run

```
Audit my Meta Ads account.
```

```
Build a paused campaign for this offer: <offer>, landing page <url>,
70 PLN/day, Poland, using ./creatives/hero.jpg. Three different angles.
```

Everything is created PAUSED. Activation, budget increases, deletion, and
customer-list uploads each require explicit approval for that specific thing -
[the safety model](../../README.md#safety-model).

A worked walkthrough, including what going wrong looks like:
[first-campaign.md](first-campaign.md).

## Troubleshooting

**No `meta-ads-*` skills under `$`.** Start a new session; skills load at
session start. If you installed by symlink, check the link target resolves and
that each directory contains a `SKILL.md`.

**`url` in `config.toml` looks ignored.** Older Codex builds hid remote HTTP
MCP servers behind `experimental_use_rmcp_client = true`. Update Codex before
setting it.

**No `ads_` tools in the session.** `codex mcp list` to confirm the server is
registered, then `codex mcp login meta-ads` to (re)authorise. Full
troubleshooting: [connect-meta-mcp.md](connect-meta-mcp.md#troubleshooting).

**Reporting a Codex-specific problem.** Include your `codex --version` and
whether the skills came from a plugin or a symlink - the two paths fail
differently. The manifest in `.codex-plugin/plugin.json` is validated against
OpenAI's published specification by
[a script](../../scripts/validate_codex_plugin.py), which catches a malformed
manifest but not a host behaviour change.
