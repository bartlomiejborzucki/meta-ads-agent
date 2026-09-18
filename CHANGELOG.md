# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-09-18

Initial development release. **Not production-ready.** The gap list is in the
README under [What's missing](README.md#whats-missing) - it is long, grouped by
what each gap needs, and worth reading before you point this at an account.

### Architecture

- Meta's official Ads MCP (`https://mcp.facebook.com/ads`) is the primary
  execution layer. The agent calls it directly; nothing in this project sits
  between them.
- A narrow Marketing API fallback, through Meta's official `facebook-business`
  SDK, covers six capabilities the official MCP does not expose. It is an
  **optional** extra, so a default install needs no credentials at all.
- Nine ADRs record the reasoning, including the parts that were rejected.

### Skills

One canonical `skills/` directory, packaged for both Codex and Claude Code
without duplicated content.

- `meta-ads-core` — routing, risk classes, account discovery, plan-then-apply,
  state and resumability, error recovery
- `meta-ads-audit` — read-only account audit, separating fact from
  interpretation from recommendation
- `meta-ads-campaign` — brief to validated plan to paused build to verified
  result
- `meta-ads-creative` — angles that differ by reason rather than wording
- `meta-ads-preview` — placement previews and QA as the activation gate
- `meta-ads-optimize` — diagnose before proposing, propose before applying
- `meta-ads-report` — equal-length period comparisons, attribution-aware
- `meta-ads-tracking` — dataset health, with configuration and evidence
  reported separately
- `meta-ads-research` — Ad Library themes, not clones

### Write safety

- Everything created is PAUSED. The plan model has no field for anything else.
- Nine risk classes, each with a stated approval requirement: `read`,
  `create_paused`, `update_inactive`, `update_active`, `budget_increase`,
  `activate`, `bulk`, `delete`, `pii_upload`.
- Budget changes are reported with old value, new value, and currency read from
  Meta.
- Deletion requires an explicit approval flag **and** a stated reason, and
  refuses an ACTIVE object. Pausing is preferred: deleted objects lose their
  optimisation history permanently.
- No generic "run any Graph call" command, by design.

### Deterministic layer

- `money.py` — one `Money` type carrying minor units, currency, and scale. ISO
  4217 minor-unit digits for zero-, two-, three-, and four-decimal currencies;
  an unknown code raises rather than assuming 100. Meta's own
  `currency_offset` overrides the table.
- Campaign plan, brand config, offer brief, campaign state, and asset manifest
  as Pydantic models that reject unknown fields.
- Platform-constraint validation before any write: account state and payability,
  currency match, budget level, Page and Instagram identity, dataset and event
  presence, destination reachability, EU DSA fields, special-category
  consistency, and local asset type and dimensions.
- State flushed after every create, so an interrupted build resumes instead of
  duplicating. Idempotent by plan reference; a plan edited after objects exist
  blocks the resume.
- Assets deduplicated by SHA-256 per ad account: the same bytes upload once,
  ever.
- Append-only action log. Secrets scrubbed on the way to disk.

### API fallback

Six capabilities, expected to shrink:

| Capability | Why |
| --- | --- |
| `local_image_upload` | no MCP tool ingests a local file |
| `local_video_upload` | same, plus asynchronous transcoding |
| `create_video_creative` | `ads_create_creative` is single-image only |
| `create_existing_post_creative` | `ads_boost_ig_post` covers Instagram only |
| `create_multi_variant_creative` | `asset_feed_spec` is not exposed |
| `delete_entity` | no MCP delete tool |

Graph API version in exactly one place, defaulting to `v26.0`. Video ids are
recorded **before** the processing wait, so a timeout never causes a re-upload.
Writes are never marked retry-safe: a timeout does not tell you whether Meta
applied it.

### CLI

`doctor`, `init`, `capabilities`, `validate-plan`, `state`, and `api`. Dry runs
work before any credentials exist. `doctor` reports MCP readiness and fallback
readiness separately, and never prints a token.

### Research

- `docs/research/current-meta-capabilities.md` — tool-by-tool inventory of
  Meta's official Ads MCP (~90 tools), read from Meta's own documentation, with
  an explicit list of what it does **not** assert
- `docs/research/ecosystem-audit.md` — eleven projects at pinned SHAs, with what
  each does well, does badly, and what nobody was doing
- `docs/research/provenance.md` — per-source license review. **0.1.0 contains no
  adapted third-party material**; every influence is reimplemented or
  reference-only.

### Hosts

- Claude Code and Codex load the same `skills/` directory. `.claude-plugin/` and
  `.codex-plugin/` are thin manifests over it; no skill names a host, and CI
  fails the build if a second `SKILL.md` tree or a host-specific phrase appears.
- Per-host MCP templates in each host's real format:
  `integrations/claude/mcp.json` (`mcpServers` JSON) and
  `integrations/codex/config.toml` (`[mcp_servers.meta-ads]` TOML with a nested
  `oauth.client_id`). Connection commands for both hosts, including
  `codex mcp login`, in `docs/getting-started/`.
- Meta's ads MCP server is generally available; connecting needs an App ID as
  the OAuth client id, not an access token. Acting on another business's
  accounts needs Advanced Access to `ads_mcp_management`.

### Project

- MIT licensed. Independent; not affiliated with Meta, OpenAI, or Anthropic.
- 523 offline tests, 90% line coverage. The SDK boundary is faked; nothing
  reaches Meta.
- CI: format, lint, types, tests on Python 3.11-3.13, a wheel install check,
  manifest validation, single-skills-tree enforcement, template validation,
  pinned Gitleaks over tree and history, and `.gitignore` assertions.
- Scheduled upstream monitor that opens or updates an issue and never
  auto-merges.

### Roadmap

Not commitments; a statement of direction. Kept short here because the reasoning
lives in the README's [What's missing](README.md#whats-missing).

**Second milestone.** Carousel creatives. Placement-specific assets. Existing
Instagram post campaigns through `ads_boost_ig_post`. Fatigue signal arithmetic
moved into Python. Longer-term reporting and stored period comparisons. Budget
pacing analysis in code. Lookalike audience workflows. Live integration tests.

**Third milestone.** Catalog ads. Lead forms, if Meta exposes them. A/B tests
through `ads_experiment_*`. Multi-account workflows. Scheduled reporting.

**Ongoing.** Shrinking the fallback. Every capability Meta adds to its official
MCP is one we delete.

[Unreleased]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/releases/tag/v0.1.0
