## Preflight: two checks, kept separate

These are independent questions with different answers and different
consequences, so never let one stand in for the other.

**1. Meta's official Ads MCP - the execution layer.** List the tools available
in this session and look for names beginning `ads_`. If there are none,
nothing in this skill can run against a real account: say so, and help the
user connect it - `connect-meta-mcp.md`, under `references/` in the
`meta-ads-core` skill, or
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/skills/meta-ads-core/references/connect-meta-mcp.md>.
The local CLI is not a substitute; it deliberately does not cover what the MCP
covers.

**2. The local `meta-ads-agent` CLI - optional, separately installed, usually
absent.** The skills install without it, so assume it is missing until a probe
says otherwise:

```bash
meta-ads-agent --version
```

"command not found" is the expected answer for most users, not a fault, and
not something to work around. **Do not put a `meta-ads-agent ...` command in
front of someone before that probe has succeeded.** A command that fails at
their prompt costs more than the step it was meant to save, and it makes the
rest of your advice look equally unchecked. Say "that step needs the optional
CLI, which is not installed here" and carry on with what the MCP can do.

With the MCP connected and no CLI, all of this still works in full: audits,
reporting, Ad Library research, previews, tracking diagnosis, creative work,
optimisation diagnosis, and the MCP-side changes that follow it. Workspace
files under `.meta-ads/` can be written directly - the templates are in the
`meta-ads-core` skill's `assets/` directory.

Only these need the CLI: campaign plan validation (and therefore campaign
builds), local image and video upload, video / existing-post / multi-variant
creatives, and deletion.
