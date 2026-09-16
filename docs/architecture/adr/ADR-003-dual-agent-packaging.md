# ADR-003: One canonical skills directory, two thin host manifests

- **Status:** accepted
- **Date:** 2026-09-16

## Context

The project targets Codex and Claude Code. As of 2026-09-16 both consume Agent Skills from a
`skills/<name>/SKILL.md` layout with YAML frontmatter (`name`, `description`), and both use a
JSON manifest — Codex at `.codex-plugin/plugin.json`, Claude Code at
`.claude-plugin/plugin.json`. The field sets overlap but are not identical: Codex requires an
`interface` object (display metadata, `defaultPrompt`, icons) and points at MCP config with a
`mcpServers` path; Claude Code has `displayName` at the top level plus `userConfig`,
`dependencies`, `defaultEnabled`, and resolves `skills/` by convention.

MCP configuration differs more. Codex examples use
`{"type": "http", "url": "...", "oauth": {"client_id": "..."}}`. Claude Code uses `.mcp.json`
with `${CLAUDE_PLUGIN_ROOT}`-style substitution and a `claude mcp add` CLI path.

The temptation is `skills-codex/` and `skills-claude/`. That guarantees divergence: a fix
lands in one and not the other, and reviewers cannot tell which is current.

## Decision

One canonical `skills/` directory is the only home for skill content. Both manifests are thin
wrappers over it, carrying host-specific metadata and nothing else. Host-specific MCP
configuration lives in `integrations/codex/mcp.json` and `integrations/claude/mcp.json` as
documented templates.

Rules:

- Skill content must not name a host. No "in Claude Code, do X". Skills describe the Meta
  workflow; hosts are an installation concern.
- Anything host-specific goes in `integrations/<host>/` or the host manifest.
- Business logic is never duplicated because a config *syntax* differs.
- `skills/` must not be copied or symlinked into host-specific trees.
- A CI check fails the build if a second directory containing `SKILL.md` files appears.

## Consequences

**Good.** One place to fix a skill. Both hosts stay in step. Adding a third host is a manifest
plus an `integrations/` entry. Reviewers always know which file is canonical.

**Bad, and accepted.**
- The lowest common denominator: we cannot use a host-specific skill feature in canonical
  content. Acceptable — the valuable content is Meta workflow, which is host-neutral.
- Codex's `interface` block duplicates description text from the Claude manifest. Small, and a
  CI check keeps name, version, and description consistent across the two.
- Only Claude Code could be exercised on the development machine (`codex` was not installed),
  so the Codex manifest is validated structurally against OpenAI's published spec rather than
  by a live install. Recorded as a known limitation in the README.
