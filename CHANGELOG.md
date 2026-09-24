# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.9.0] - 2026-09-24

**Schemas worth promising.** `MIGRATION: none required` - and now tested
against the files 0.1.0 and 0.2.0 shipped.

### Added

- [docs/reference/compatibility.md](docs/reference/compatibility.md): what
  an upgrade may change in the workspace, the CLI, its `--json` output, its
  exit codes and the skills, and how each promise is tested.
- Compatibility tests over `tests/fixtures/written-by/`, the examples and
  templates of every earlier release: each is read, each plan validated, and
  each saved campaign state resumed against its plan.
- A `--json` contract: every command's keys recorded, and a test that fails
  when one is removed or renamed.

### Changed

- A `schema_version` above what this release understands is refused, with
  an error that says to upgrade, in plans, state, brand config, offers and
  the asset manifest. Before, a newer file was silently read by older rules.
- [The roadmap](docs/roadmap.md) ends with the 1.0 checklist: what remains,
  and who can do each part.

## [0.8.0] - 2026-09-24

**Catalogs and more than one account.** `MIGRATION: none required`; an
existing `account.yaml` is read as before.

### Added

- **`meta-ads-catalog`**: catalog, feed and event-source health in the order
  that finds the blocking problem first; product sets read by content;
  changes approved with the live ad sets they affect named.
- **Several ad accounts per workspace**: cached facts at
  `accounts/<act_id>.yaml`, and `validate-plan` reads the file for the
  plan's own account. `state` shows and filters campaigns by account
  (`--account`).
- A trigger-eval case for the new skill.

### Changed

- The capability map splits catalogs into `read_catalogs`, `change_catalog`
  (`update_active`) and `delete_catalog_objects`, and records
  `create_dynamic_ad_creative` as not supported.
- An `account.yaml` for a different account than the plan's is no longer
  used for validation; a hint says where the right file belongs.

## [0.7.0] - 2026-09-24

**Audiences and experiments.** `MIGRATION: none required`. Two new skills;
an installed copy gains them on `meta-ads-agent upgrade`.

### Added

- **`meta-ads-audiences`**: custom and lookalike audiences - reuse before
  building, lookalike source by value and recency, Meta's numbers read from
  its help rather than recalled, creating and attaching as separate
  approvals, and every `pii_upload` rule for customer lists.
- **`meta-ads-experiments`**: A/B tests and lift studies - one question,
  one variable, a metric named in advance, eligibility first, sized before
  creation, read without choosing the metric afterwards.
- **`meta-ads-agent report power`**: the smallest lift a test can detect in a
  given time, or the time it needs for a given lift; alpha divided among
  cells.
- Trigger-eval cases for both skills.

### Changed

- The capability map's `experiments` entry is split into `read_experiments`
  (read), `create_experiment` and `update_experiment` (both
  `update_active`).
- Eleven skills, wherever the docs give a count.

## [0.6.0] - 2026-09-24

**Creative formats.** `MIGRATION: none required`; 0.2 fingerprints still
resume, because the new `cards` field is left out of their recomputation.

### Added

- **Carousel creatives.** `mode: carousel` with 2 to 10 cards; `api
  create-creative --carousel --cards FILE`. Card order is kept. A new
  fallback capability, argued in
  [ADR-010](docs/architecture/adr/ADR-010-carousel-and-instagram-posts.md).
- **Instagram existing posts.** `mode: existing_post` with
  `instagram_media_id` and `instagram_account_id`; `api create-creative
  --post --instagram-media-id`. Built as an inert creative, not a boost:
  Meta does not document whether `ads_boost_ig_post` can create a paused
  boost.
- **Placement-specific assets.** `placement` on an asset in `mode:
  multi_variant` becomes an asset customisation rule; `api create-creative
  --variants --placement ASSET=PLACEMENT`. At least one asset stays
  unpinned as the default.
- `api create-creative --variants --variants-file FILE`: more than one copy
  variant from the CLI.
- Contract tests and live tests for each new request shape.

### Changed

- `placement` outside `mode: multi_variant` is refused by the plan model;
  the validator's `asset.placement_unsupported` is gone because placements
  are now built.
- The fallback covers seven capabilities; the skills, README, routing
  reference and capability-refresh guide say so.

## [0.5.0] - 2026-09-23

**Verification without a test account.** `MIGRATION: none required`.

### Fixed

- **Code 368 is no longer retry-safe.** A policy block was in the transient
  set, so a read that hit it was marked safe to retry, while the error
  reference said "Stop. Do not retry" in the same row. The reference now
  gives 368 its own section.
- **A shell injection in the trigger-evals workflow.** Its cost input was
  spliced into the script; it now arrives through the environment and must
  be a number.

### Added

- **Contract tests against the real SDK.** Every creative the fallback
  builds, and every field constant and field list it uses, is checked
  against the `facebook-business` SDK's own object descriptions: fields,
  types, enum values. The main CI job installs the `api` extra to run them.
- **Recorded Graph errors**: one response per code in the error reference,
  replayed through the SDK's `FacebookRequestError`, checked for code,
  subcode, message, redaction and the retry decision.
- **Live tests** for the five things only Meta can confirm, following the
  rules in `tests/live/README.md`. They skip without a designated test
  account and have not run.
- **`meta-ads-agent capabilities --compare TOOL_LIST`**: a live session's
  tool list against the capability map - missing, new, community-reported,
  and possible fallback-gap closers. Exits 1 on any difference.
- `config/mcp-tools.yaml`, the reference's 91 tool names, generated from the
  research document by `scripts/build_mcp_tool_inventory.py` and checked in
  CI.
- The 0.5.0 security review in [SECURITY.md](SECURITY.md#050-review).

## [0.4.0] - 2026-09-23

**Arithmetic in code.** `MIGRATION: none required`. `brand.yaml` gains one
optional threshold with a default.

### Added

- **`meta-ads-agent report compare`** - two equal, adjacent windows (or two
  meeting at `--boundary`, the day of a known change), every rate recomputed
  from sums, each metric labelled `signal`, `noise`, `insufficient`,
  `observed` or `unavailable` against the user's noise band and volume
  floors, and the metric chain's documented rules read off those labels.
  Incomplete windows, entities live in one window only, and a current window
  still inside attribution are flagged.
- **`meta-ads-agent report fatigue`** - per ad, CTR against its own best
  earlier window, the frequency condition (from a window-long row, since
  daily reach does not add up; otherwise `unknown`), spend since the decline
  began, days with delivery, and which siblings held up. Below the click
  floor: insufficient evidence.
- **`meta-ads-agent report pacing`** - daily utilisation and outlier days, or
  a lifetime budget against a straight-line schedule with a projection.
- `thresholds.noise_band_pct` in `brand.yaml` (default 10).
- [docs/reference/report-input.md](docs/reference/report-input.md): the
  accepted insights shape. It is the Marketing API's documented row; the
  official MCP's response schema is unpublished, so mapping onto it is the
  agent's job and is unverified against a live session.
- **Trigger evals** in `evals/`: one `claude plugin eval` case per skill and
  two negatives, graded on which skill loaded. Run on demand by the
  `Trigger evals` workflow; not yet run.

### Changed

- The report and optimise skills use the `report` commands when the CLI is
  present and keep the by-hand route when it is not. The report skill still
  names no CLI command in its `SKILL.md`; the command lives in its metrics
  reference.
- The shared preflight block went from 285 words to 199 and the no-CLI build
  block from 244 to 194, with every rule kept. Each skill still carries its own copy,
  so a skill installed alone still works.

## [0.3.0] - 2026-09-23

**Local state and the validator.** `MIGRATION: none required` - state written
by 0.2 is read as it is, including its plan fingerprints.

### Fixed - money

- **Meta's currency offsets win over ISO 4217 where they differ.** Meta counts
  COP, CRC, HUF, IDR and TWD in whole units (ISO says hundredths) and BHD and
  JOD in hundredths (ISO says thousandths). For an account in one of them
  whose `currency_offset` had not been read, a budget went to Meta 100x (or
  10x) too large. From Meta's currency reference, read 2026-09-23.
- `Money.from_display("Infinity")` crashed with `OverflowError`;
  `from_minor(70.9)` silently became 70; `offset=0` silently became the
  table default. All three are errors now.

### Fixed - concurrency

- **Two sessions on one workspace no longer lose each other's writes.** The
  asset manifest, campaign state, the action log and the installer are
  updated under an advisory lock (`flock` / `msvcrt`, no dependency). Two
  uploads of the same file wait for each other instead of uploading it twice.
- **Campaign state is merged, not overwritten.** Before saving, objects
  another session recorded are folded in. Two different ids for one plan
  element are both kept on disk, then reported: one is a duplicate on Meta.
- Action-log appends are fsynced.

### Fixed - resume

- **A new release no longer blocks every in-flight resume.** The plan
  fingerprint hashed defaulted fields too, so adding any field to the plan
  model changed every existing fingerprint. Defaults are excluded now, and
  the fingerprint names its algorithm (`v2:sha256:`); 0.2 fingerprints are
  still compared the way they were computed.

### Added - validation

- A campaign-level lifetime budget needs an end on the campaign or on every
  ad set (`schedule.lifetime_needs_end`); only ad-set budgets were checked.
- Bids: a capped strategy without `bid_amount`, the uncapped one with it, and
  an amount the currency cannot represent (`bid.*`).
- The account's own minimum daily budget, when `account.yaml` carries Meta's
  `min_daily_budget` (`budget.below_minimum`).
- A local video in a `single_image` ad is refused by the model, as a
  `video_id` already was.
- Unexpanded `{token}`s in a name or URL (`naming.unrendered`), and
  `tracking.utm` parameters missing from the URL (`tracking.utm_not_applied`).
- `AssetRef.placement` is refused (`asset.placement_unsupported`) instead of
  validating and then serving the asset in every placement.
- Findings print errors, then warnings, then notes. `objective.invalid` is
  reported once, not once per ad set.

### Added - `render-plan`

- **`meta-ads-agent render-plan`** applies the `naming` and `utm` templates
  in `brand.yaml`, and a plan's `tracking.utm`, which were documented as
  substituted and substituted by nothing. Strict about unknown or empty
  tokens, never overwrites a UTM already in a URL, and idempotent. Prints
  every change; writes with `--write`.

### Added - audit

- Failed and dry-run `api` commands are recorded in `actions.jsonl`; a
  deletion record names the ad account. `read(limit=0)` returns nothing
  rather than everything.

### Changed

- The validator is a package of modules by concern (`report`,
  `checks_account`, `checks_budget`, `checks_adset`, `checks_creative`).
  Imports from `meta_ads_agent.validation` are unchanged.
- The safety policy says what its class name did not: any budget change, a
  cut included, needs explicit approval. Summaries that said "raise a
  budget" now say so too.
- CI runs the suite on macOS and on Windows (non-blocking until its first
  green run), checks versions on every change, lints `scripts/`, and pins
  every action to a commit SHA. The upstream check fails when a lookup
  fails, creates its own label, and opens an issue when the capability map
  is 75 days old.

## [0.2.1] - 2026-09-23

**Security and correctness fixes from a review of 0.2.0.** `MIGRATION: none
required`. Recorded in [SECURITY.md](SECURITY.md#021-review); what comes next
is in [docs/roadmap.md](docs/roadmap.md).

### Security

- `redact_mapping` masked no camelCase key: `metaAccessToken` and
  `pageAccessToken` were printed in full. Keys are split on case, and any key
  ending in `_token`, `_secret`, `_password` or `_api_key` is masked.
- `redact_url` kept `fb_exchange_token`, `code`, `input_token` and any other
  parameter it had not been told about. A query now survives only if every
  parameter is known to be harmless, and `user:pass@` is always removed.
- `Authorization: OAuth <token>` is masked, as `Bearer` already was.
- `open-url` no longer falls back to `cmd.exe /c start`, which treated the
  `&` in an OAuth URL as a command separator. The fallback is
  `rundll32.exe url.dll,FileProtocolHandler`, which parses nothing.

### Fixed

- With no `--account` and no `META_AD_ACCOUNT_ID`, a real `api` call went to
  `act_<no account configured>`. It is now refused before anything is sent;
  the placeholder remains only in dry-run output.
- `123` and `act_123` were two asset-manifest keys, so the same file could be
  uploaded twice. Account ids are normalised once.
- A schedule with a UTC offset on one end and not the other crashed
  `validate-plan` with a traceback. It is a validation error.
- A lowercase `--cta` and a malformed `META_GRAPH_API_VERSION` escaped as
  tracebacks. They are a usage error (exit 2) and a configuration error.
- CI: the PyPI job could run from a manual dispatch on any branch, skipping
  the tag and changelog checks. It now requires a `v*` tag. The step that was
  meant to assert the upgraded installation is complete only printed a status,
  for the wrong directory; it now asserts it for the right one.

### Documentation

- `docs/reference/cli.md` documents `install`, `upgrade`, `migrate`,
  `mcp-config` and `open-url`, and a test fails if a command has no section.
  Its `api` section no longer claims every dry run works without credentials:
  a `delete` dry run reads the object from Meta.
- Stale "0.1.0" statements and hard-coded test counts removed from the
  README, publishing guide, SECURITY.md, the capability map and three skill
  references.
- [docs/roadmap.md](docs/roadmap.md): the plan for 0.3 to 1.0.

## [0.2.0] - 2026-09-21

**Packaging and updates.** Two failures with one root: the project assumed the
repository would be there at run time, and assumed something would re-run an
installer for us. Neither is true. `MIGRATION: none required` - the one
workspace migration in this release is applied automatically by
`meta-ads-agent upgrade` and is a no-op on a workspace created by `init`.

### Added - installing and updating

- **`meta-ads-agent install`, `upgrade` and `migrate`.** Codex caches a plugin
  under `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`, documents
  only a `SessionStart` hook, and skips even that until the user has reviewed
  and trusted it. There is no post-install or post-update event, so the update
  path is a command somebody runs. Pretending otherwise is how an installation
  ends up reporting a version it is not running.
- **`release-manifest.json`**, generated by
  `scripts/build_release_manifest.py` and checked in CI. It enumerates every
  shipped file with its SHA-256, so an update is a diff between two lists
  rather than a walk over the files that happen to be present. A new file, a
  new directory, a new script and a deleted file are the same operation.
- **Interruption-resistant updates.** The order is backup, stage, verify the
  stage, swap, verify the installation, and only then record the version. An
  update killed at any point leaves an installation that describes itself as
  mid-update and names the stage it stopped at, rather than one that claims to
  be current.
- **`--rollback`**, restoring the backup taken before the failed attempt. A
  resumed update reuses that backup rather than archiving the half-installed
  tree over it.
- **Versioned workspace migrations**, separate from the payload update because
  replacing our files and editing the user's are different risks. Each has an
  id, is recorded in `.meta-ads/.migrations.json` the moment it succeeds, and
  independently detects whether its effect is already present - so a deleted
  ledger cannot cause a second run. The workspace is copied aside before the
  first migration that changes anything, and a failure stops the run.
- **Script-backed migrations.** A release that adds a script has done nothing
  until something runs it. Naming the script in the manifest makes it a step
  the updater knows about; pinning its SHA-256 there is what makes executing it
  defensible. It still does not run without `--allow-migration-scripts`.
- **Installation diagnostics in `doctor`**, distinguishing `complete`,
  `update-available`, `migration-required`, `interrupted`, `broken` and
  `not-installed`, plus version skew between the CLI, the payload and the
  installed skills, and the specific files that are missing, modified, or left
  over from an earlier version.
- **The skills ship inside the wheel.** `uv tool install git+...` now yields a
  CLI that already has the payload it is about to copy, so the two can never be
  different versions of the project.

### Added - Windows-native Codex with a WSL toolchain

- **`--target windows-codex`.** Codex running as a Windows application cannot
  see `/home/you/.agents/skills`, so a skills directory that is obviously
  correct from the WSL terminal is invisible to the process reading it. The
  installer converts paths with `wslpath`, asks Windows for `%USERPROFILE%`
  rather than guessing at `/mnt/c/Users/<login>`, and copies the files in.
- **Copies, not symlinks.** A Windows symlink into the WSL filesystem needs
  Developer Mode to create, breaks when the distribution is not running, and
  resolves through a 9P server the Codex process may not reach.
- **Case-insensitive target resolution**, so `.Agents\Skills` is recognised as
  the installation already there instead of becoming a second one beside it.
- **`meta-ads-agent mcp-config`**, which writes only the
  `[mcp_servers.meta-ads]` block into a Codex `config.toml`. The block is
  fenced and spliced in by text; every other line, including other servers and
  the user's comments, is preserved byte for byte.
- **`meta-ads-agent open-url`**, handing OAuth to the Windows browser through
  `explorer.exe`. There is deliberately no Linux browser fallback: a browser
  inside WSL has a different profile, so the round trip would not complete.
- Nothing is installed on the Windows side. Python, Node, uv, pip, npm and the
  repository all stay in WSL, and a test asserts the installer never invokes a
  package manager across the boundary.
- [install-windows-wsl.md](docs/getting-started/install-windows-wsl.md), with
  one install command and one update command, both safe to re-run.

### Fixed

- **Skills referenced files that do not exist once installed.** Eighteen
  references across six skills pointed at `docs/`, `templates/`, `config/`, or
  another skill by a path that only resolves in a repository checkout. They
  broke in every install shape, including the full plugin - the repository was
  simply always there during development. Every path-shaped reference inside a
  skill now resolves inside that same skill; cross-skill and repository
  pointers are named in prose plus an absolute URL.
- `meta-ads-campaign` pointed at `templates/campaign/campaign-plan.yaml` for
  the plan schema, which a standalone skill install does not have.
- `meta-ads-core` sent a user with no MCP connection to
  `docs/getting-started/connect-meta-mcp.md`, likewise absent.
- `meta-ads-tracking` referenced `skills/meta-ads-core/references/safety-policy.md`
  as a repository-root path. It resolved under no install method, including a
  checkout, because nothing tells an agent where the root is.
- The campaign workflow required `meta-ads-agent validate-plan` while the CLI
  was documented as optional and does not ship with the skills, so the
  documented happy path ended at a command most users cannot run.

### Added

- **Preflight checks in every skill**, generated from `packaging/shared/`. The
  official Ads MCP and the local CLI are now checked separately, at the start
  of the work: the MCP by listing tools for names beginning `ads_`, the CLI by
  `meta-ads-agent --version`. "command not found" is treated as the normal
  answer, and no skill may print a `meta-ads-agent` command before the probe.
- **A stated policy for building with no CLI.** Audits, reporting, Ad Library
  research, previews, tracking diagnosis, creative, and optimisation diagnosis
  work through the MCP alone. Campaign writes stop at the plan, because plan
  validation is the gate that catches minor-unit currency arithmetic, a budget
  on two levels, an identity or dataset that is not on the account, and missing
  EU transparency fields - and the user is given four concrete routes forward
  rather than a dead end. No safety rule was relaxed to make this work.
- `skills/meta-ads-core/references/connect-meta-mcp.md` - the host-neutral
  connection guide, inside the skill, so a disconnected session has something
  to act on.
- `scripts/check_skill_packaging.py` - installs the skills the way a host
  would (whole tree, and each directory on its own) into a temporary
  directory, then resolves every reference from there, checks every
  `meta-ads-agent` command named in a skill against the real argument parser,
  and checks the required shared blocks are present. No network, no Meta
  account.
- `scripts/sync_skill_blocks.py` - renders `packaging/shared/*.md` into the
  skills that declare the markers. `--check` runs in CI, so a hand-edited copy
  fails the build.
- `tests/test_packaging.py` - 64 tests over the install shapes, the CLI-present
  and CLI-absent paths, `doctor`'s MCP detection with a controlled `HOME`, and
  the template mapping. Includes negative tests, so the guards are known to
  fail when they should.
- `docs/reference/packaging.md` - the supported install shapes, the rules the
  checks enforce, and what works without the CLI.
- CI now verifies the documented no-install validation route
  (`uvx --from . meta-ads-agent validate-plan …`) against the checkout.

### Changed

- **Templates moved into the skills that document them**, so there is still
  exactly one copy of each: `brand.yaml`, `voice.md`, `account.yaml` and
  `offer.yaml` to `skills/meta-ads-core/assets/`, `campaign-plan.yaml` to
  `skills/meta-ads-campaign/assets/`. The root `templates/` directory is gone;
  the wheel gets its copy through a build-time `force-include`, so
  `meta-ads-agent init` is unchanged. A test fails if `templates/` reappears.
- Install documentation now states the three supported install shapes and what
  each of them gives you, rather than implying the CLI is optional for
  everything.

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
  pinned Gitleaks over tree and history, and `.gitignore` assertions. Runs on
  every push to `master` and every pull request, and is green on GitHub's
  runners.
- The capability map was spot-checked against Meta's live documentation on
  2026-09-18: the six fallback gaps all still hold.
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

[Unreleased]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bartlomiejborzucki/meta-ads-agent/releases/tag/v0.1.0
