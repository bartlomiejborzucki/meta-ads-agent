# Using meta-ads-agent in Claude Cowork (and claude.ai)

*As used on 2026-11-03 and 2026-11-04, to build a real campaign. Cowork and
claude.ai change; check against what your session shows.*

Cowork runs each session on a machine of its own, with a folder from your
computer connected to it. That shapes three things differently from Claude
Code or Codex on your own machine.

## 1. Meta's MCP is an account connector

In claude.ai and Cowork, Meta's Ads MCP is added as a **connector on your
Claude account** - in claude.ai's connector settings - rather than with
`claude mcp add` and an App ID in a local config. Once connected, every
session sees its tools, under names such as
`mcp__claude_ai_Facebook_ads__ads_get_ad_accounts`. The skills only look for
the `ads_*` part, so they work unchanged, and so does the plugin's approval
hook where the host runs plugin hooks.

To check it: ask the agent to list its Meta tools, or to read your ad
accounts. If none are there, the connector is not connected for this account
or session.

`meta-ads-agent doctor` cannot see an account connector - it lives on
Anthropic's side, not in any file on the session machine - and reports
"Meta Ads MCP configured: MISSING ... may still be connected as a claude.ai
account connector". That is expected; the tool list is the real check.

## 2. The CLI is per session

The session machine can install the optional CLI the usual way, including
the API fallback extra:

```bash
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git#egg=meta-ads-agent[api]"
meta-ads-agent --version
```

But its home directory does not outlive the session: the next session starts
without the CLI. Install it again when a step needs it - plan validation for
a campaign build is the usual one - or validate without installing:

```bash
uvx --from "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
  meta-ads-agent validate-plan <plan>
```

Nothing a campaign needs is stored in the CLI's install, so reinstalling
loses nothing.

## 3. The workspace lives in your connected folder

Put `.meta-ads/` in the **project folder you connected to Cowork**, not in the
session's home directory. Plans, `state.json`, the launch baseline and QA
notes then survive the session, and the next one resumes from them:

```bash
cd <the connected project folder>
meta-ads-agent init        # or write the files from the core skill's templates
```

A workspace created anywhere else is gone when the session ends, along with
the ids of whatever it built - Meta keeps the objects, but the resume does
not know about them.

## Uploading media

Cowork and claude.ai can show Meta's interactive upload app, so
`ads_creative_upload_media` with `LOCAL_FILE` lets you pick an image or video
from your computer - no token, no CLI. A public URL works too.

## Related

- [Connect Meta's MCP](connect-meta-mcp.md) - the App ID route, for Claude
  Code and Codex.
- [Install in Claude Code](install-claude-code.md) - the plugin and its hook.
- [The API fallback](api-fallback.md) - deprecated as of 2026-11-04; what is
  left of it.
