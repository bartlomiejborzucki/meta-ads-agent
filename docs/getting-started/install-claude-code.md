# Installing on Claude Code

Requires Claude Code v2.1.233 or later.

## From this repository

```bash
claude plugin marketplace add OWNER/meta-ads-agent
claude plugin install meta-ads-agent@meta-ads-agent
```

Scope it:

```bash
claude plugin install meta-ads-agent@meta-ads-agent --scope project   # shared via git
claude plugin install meta-ads-agent@meta-ads-agent --scope local     # gitignored
```

Confirm:

```bash
claude plugin list
```

## Local development install

Load the plugin for one session without installing it:

```bash
git clone https://github.com/OWNER/meta-ads-agent.git
cd meta-ads-agent
claude --plugin-dir .
```

Or keep it loaded by symlinking into your skills directory:

```bash
ln -s "$(pwd)" ~/.claude/skills/meta-ads-agent
# loads as meta-ads-agent@skills-dir
```

`SKILL.md` edits take effect immediately. Other components need
`/reload-plugins` or a restart.

Validate the manifest before committing a change to it:

```bash
claude plugin validate . --strict
```

## Next: connect Meta's MCP

The plugin does **not** bundle the Meta MCP server, and cannot - see
[ADR-006](../architecture/adr/ADR-006-mcp-connection-is-user-owned.md). One
command:

```bash
claude mcp add --transport http --client-id <YOUR_META_APP_ID> \
  meta-ads https://mcp.facebook.com/ads
```

Walkthrough: [connect-meta-mcp.md](connect-meta-mcp.md).

## Optional: the local CLI

Only needed for capabilities Meta's official MCP does not expose - uploading an
image or video from your filesystem, video and existing-post and multi-variant
creatives, and deletion. Also provides `doctor`, `init`, and `validate-plan`,
which are useful on their own.

```bash
uv tool install "meta-ads-agent[api]"
# or, from a clone:
uv pip install -e ".[api]"
# or without the fallback at all:
uv pip install -e .
```

Then:

```bash
meta-ads-agent doctor
meta-ads-agent init
```

## First run

```
Audit my Meta Ads account.
```

Then:

```
Build a paused campaign for this offer: <offer>, landing page <url>,
70 PLN/day, Poland, using ./creatives/hero.jpg. Do not launch it.
```

Nothing becomes active without you saying so, explicitly, after seeing previews.

## Uninstalling

```bash
claude plugin uninstall meta-ads-agent
claude mcp remove meta-ads
```

`.meta-ads/` stays. It is your data - delete it yourself if you want it gone.
