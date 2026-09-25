# CLI reference

`meta-ads-agent` is deliberately small. Meta's official Ads MCP is the primary
execution layer and your agent calls it directly; these commands cover local
prerequisites, validation, state, and the few capabilities the official MCP does
not expose.

Global: `--version`, and `--help` on every command.

## doctor

```bash
meta-ads-agent doctor [--json] [--path DIR]
```

Checks Python, `uv`, `git`, `ffprobe`, the package and its capability registry,
the configured Graph API version, whether Claude Code or Codex is on `PATH`,
whether a Meta MCP server is configured, the brand workspace and its privacy,
and the optional fallback dependencies.

Reports three readiness states separately, because they need different fixes:

| State | Meaning |
| --- | --- |
| `READY FOR MCP` | everything needed for the default path |
| `READY FOR API FALLBACK` | the extra and a token are present |
| `MISSING OPTIONAL FALLBACK CONFIG` | normal, and not a problem |

**Absent fallback credentials are never an error.** Most users never need them.

Never prints a token. A configured secret is shown as a hash and a length, so
you can tell which token is set without the value appearing anywhere.

The MCP check looks at host configuration files for a reference to
`mcp.facebook.com/ads`. It confirms configuration, not a live session - only a
running agent can prove that. Exit `1` only on a hard failure.

## init

```bash
meta-ads-agent init [--path DIR] [--brand NAME] [--force] [--check]
```

Creates `.meta-ads/` in the current project, seeded from the bundled templates,
and writes a `.gitignore` inside it so the workspace is private by default.

Safe to re-run: existing files are kept unless `--force`. `--check` validates an
existing workspace instead of creating one, and exits `1` if a file fails
validation.

## capabilities

```bash
meta-ads-agent capabilities [NAME] [--json] [--area AREA] [--gaps] [--validate]
  [--compare TOOL_LIST]
```

Prints the capability registry: who owns each capability, its risk class,
whether it needs approval, MCP tool hints, and the CLI command for gaps.

```bash
meta-ads-agent capabilities --gaps               # what the fallback covers
meta-ads-agent capabilities local_video_upload   # one capability, with the reason
meta-ads-agent capabilities --validate           # check the registry, flag stale entries
```

This is the project's **recorded** mapping, not live introspection of a
connected MCP session. The output says so. To see what a session actually
exposes, ask your agent to list its tools - and then hand that list to
`--compare` (a file, or `-` for stdin), which reports what the session lacks,
what it has that the map does not, and which new tools may close a fallback
gap. It exits 1 when the session and the map differ, and changes nothing.

## render-plan

```bash
meta-ads-agent render-plan PLAN [--brand-file FILE] [--write] [--json]
```

Applies the `naming` and `utm` templates in `brand.yaml` to a plan. Any
campaign, ad set or ad name containing `{brand}`, `{objective}`, `{offer}`,
`{date}`, `{audience}` or `{variant}` is expanded, and each destination URL
gets the brand's UTM parameters plus the ad set's own `tracking.utm`, **only
where the URL does not already carry them** - a parameter already in the URL
is never overwritten. With no `brand.yaml`, only `tracking.utm` applies.

`{date}` is the plan's `created_at`, so rendering twice gives the same answer.
An unknown token, or one with no value (no `offer` in the plan, say), is an
error naming it rather than an empty string in a name.

Prints every change. `--write` saves the rendered plan over `plan.yaml`
(comments in the file are not kept); without it nothing is written.
`validate-plan` refuses a plan that still has unexpanded tokens in a name or
URL, so render first.

## validate-plan

```bash
meta-ads-agent validate-plan PLAN [--account-file F] [--brand-file F]
                                  [--json] [--skip-assets] [--strict]
```

| Exit | Meaning |
| --- | --- |
| 0 | valid; warnings may be present |
| 1 | blocked by at least one error |
| 2 | the file could not be read or parsed |

Checks platform constraints only: account state and payability, currency match,
budget conversion and level, Page and Instagram identity, dataset and event
presence, destination reachability, EU transparency fields, special-category
consistency, and local asset type and dimensions.

Errors block. Warnings are things a human should see, not things Meta will
reject. `--strict` treats warnings as failure, which is useful in CI and
usually wrong interactively.

Also reports which layer will perform each step, so you learn where the
fallback is involved **before** a build stops halfway for want of a token.

Account and brand files default to the workspace. Local asset paths in a plan
resolve against the **plan's** directory, so a workspace is portable.

## state

```bash
meta-ads-agent state [SLUG] [--json] [--list] [--account ACT_ID]
```

Read-only and offline. Without a slug, lists campaigns. With one, shows the
stage, every created object with its provider and status, any recorded
failures and whether they were retry-safe, and what a resume would do next.

Exits `1` if the plan changed after objects were created - continuing would
apply a different plan to existing structure.

It never contacts Meta. The reconciliation read belongs to the agent through
the MCP, and the output says so.

## report

```bash
meta-ads-agent report compare INSIGHTS --days N [--end DATE | --boundary DATE]
  [--result-event ACTION_TYPE] [--attribution-days N] [--currency CODE]
  [--level ad|adset|campaign|account] [--brand-file FILE] [--json]
meta-ads-agent report fatigue INSIGHTS [--days 7] [--end DATE] [--currency CODE]
  [--brand-file FILE] [--json]
meta-ads-agent report pacing INSIGHTS (--daily-budget AMOUNT | --lifetime-budget AMOUNT)
  [--start DATE] [--end DATE] [--as-of DATE] [--currency CODE] [--level LEVEL] [--json]
```

Read-only and offline arithmetic over insights rows the agent read from Meta.
Input format and thresholds: [report-input.md](report-input.md).

- **compare** - two equal, adjacent windows: the last `--days` ending at
  `--end` (default: the last day in the data), or starting at `--boundary`, the
  day a known change happened. Every rate is recomputed from sums. Each metric
  is labelled `signal`, `noise`, `insufficient` (below a volume floor),
  `observed` (a count) or `unavailable`, and the metric chain's documented
  rules are read off those labels. Incomplete windows, entities live in only
  one window, and a current window still inside `--attribution-days` are
  flagged.
- **fatigue** - per ad: CTR against its own best earlier window of the same
  length, the frequency condition (from a window-long row, else `unknown`),
  spend since the decline began, days with delivery, and which siblings in
  the ad set held up. Below the click floor: insufficient evidence.
- **pacing** - a daily budget's utilisation and the days far under or over
  it, or a lifetime budget's spend against a straight-line schedule, the
  projection at the current rate, and the daily spend needed to finish.
  Amounts are display amounts in the account currency.

```bash
meta-ads-agent report power --baseline-rate RATE --units-per-day N
  (--days D | --lift L) [--cells 2] [--alpha 0.05] [--power 0.8] [--json]
```

- **power** - before an A/B test splits live delivery: the smallest relative
  lift a test of `--days` can detect, or the days needed to detect `--lift`.
  Two-sided, two proportions, each cell against the control, alpha divided
  among the comparisons. The rate is the metric's own (conversions per click);
  the units are its denominator per day per cell. Needs no insights file. When
  even a doubling is out of reach it says the test cannot answer.

None of them concludes anything. They print the numbers and the rule behind
each label; the report, optimise and experiments skills interpret them.

## install

```bash
meta-ads-agent install [--target agents|windows-codex|path] [--path DIR]
  [--windows-home DIR] [--dry-run] [--force] [--no-backup] [--json]
```

Copies the skills shipped inside the installed package into a directory an
agent reads, and verifies every file against `release-manifest.json`.
`agents` (the default) is `~/.agents/skills`; `windows-codex` is the Windows
user profile seen from WSL; `path` is `--path`. Safe to re-run: a current
installation is left alone and a partial one is completed. `--force` rewrites
files that already match. Detail, including the update order and what
`--no-backup` gives up: [packaging.md](packaging.md).

## upgrade

```bash
meta-ads-agent upgrade [--target ...] [--path DIR] [--workspace DIR]
  [--allow-migration-scripts] [--rollback] [--dry-run] [--json]
```

The skills first, then any outstanding workspace migrations. The installed
version is recorded only after every file is verified, so an interrupted
upgrade reports itself as interrupted. Re-running finishes it; `--rollback`
restores the backup it took first and stops.

## migrate

```bash
meta-ads-agent migrate [--workspace DIR] [--allow-migration-scripts]
  [--dry-run] [--json]
```

Workspace migrations only, applied once each and recorded in
`.meta-ads/.migrations.json` as each succeeds. The workspace is copied aside
before the first change. A migration carried out by a script shipped in the
payload runs only with `--allow-migration-scripts`, and only if the script's
SHA-256 matches the manifest.

## mcp-config

```bash
meta-ads-agent mcp-config --client-id APP_ID [--config FILE | --windows
  [--windows-home DIR]] [--dry-run] [--json]
```

Writes the `[mcp_servers.meta-ads]` block into a Codex `config.toml` - by
default `~/.codex/config.toml`, with `--windows` the Windows profile's copy
from inside WSL. Only that block is written; every other line, including
other servers and comments, is preserved byte for byte. The client id is your
Meta App ID, not a secret.

## open-url

```bash
meta-ads-agent open-url URL [--json]
```

Opens an `https` URL in the Windows browser from inside WSL, so an OAuth
round trip lands in the profile you are already signed into. Neither launcher
it tries (`explorer.exe`, then `rundll32.exe url.dll,FileProtocolHandler`)
goes through a shell, so the `&` in an OAuth URL reaches the browser intact.
There is no Linux browser fallback: if neither is found, the URL is printed
for you to open by hand. See
[install-windows-wsl.md](../getting-started/install-windows-wsl.md).

## api

The fallback. Needs the `api` extra and `META_ACCESS_TOKEN`. Every subcommand
takes `--json` and `--dry-run`; every one except `delete` takes `--account`
(`123` and `act_123` are the same account). With no `--account` and no
`META_AD_ACCOUNT_ID`, a real call is refused before anything is sent.

**Dry runs of uploads and creatives work before any credentials exist** -
that is their point. A `delete` dry run is the exception: it reads the object
from Meta to refuse an ACTIVE one, so it needs a token.

```bash
meta-ads-agent api upload-image PATH
meta-ads-agent api upload-video PATH [--no-wait] [--timeout SECONDS]
```

Deduplicated by content fingerprint per ad account: the same bytes upload once,
ever. Video upload waits for Meta to finish transcoding, and records the id
**before** waiting, so a timeout never causes a re-upload. `--no-wait` returns
as soon as the id exists, which is only useful if you will poll separately - a
creative built against an unprocessed video is rejected.

```bash
meta-ads-agent api create-creative (--video | --post | --variants | --carousel)
  --name NAME [--page-id ID] [--video-id ID] [--post-id ID]
  [--instagram-media-id ID] [--image-hash HASH ...] [--url URL]
  [--primary-text TEXT] [--headline TEXT] [--cta TYPE]
  [--instagram-account-id ID] [--cards FILE] [--variants-file FILE]
  [--placement ASSET=PLACEMENT ...]
```

`--post` promotes an existing post, preserving its engagement: a Facebook Page
post with `--post-id` (`object_story_id`), or an Instagram post with
`--instagram-media-id` and `--instagram-account-id` (`source_instagram_media_id`).
The Instagram post is built as an inert creative rather than through
`ads_boost_ig_post`, whose ability to create a paused boost Meta does not
document ([ADR-010](../architecture/adr/ADR-010-carousel-and-instagram-posts.md)).

`--carousel` reads 2 to 10 cards from `--cards`, a JSON list of
`{"image_hash" | "video_id", "headline", "description", "link"}`, in order.

`--variants` takes one variant from `--primary-text` / `--headline`, or several
from `--variants-file` (a JSON list shaped like a plan's `variants`).
`--placement HASH=instagram_stories` pins one of its assets to a placement;
at least one must stay unpinned.

```bash
meta-ads-agent api delete OBJECT_ID --type (campaign|ad_set|ad)
  --reason TEXT --approved
```

Requires both `--reason` and `--approved`, and refuses an ACTIVE object
outright. Deleted objects lose their optimisation history permanently; paused
objects keep it, so pausing is almost always the better answer.

There is no generic "run any Graph call" command. Adding one would void every
guardrail in the project.

## Environment variables

| Variable | Needed for |
| --- | --- |
| `META_ACCESS_TOKEN` | any `api` subcommand |
| `META_AD_ACCOUNT_ID` | convenience; avoids `--account` |
| `META_APP_ID`, `META_APP_SECRET` | rarely - some token flows |
| `META_GRAPH_API_VERSION` | overriding the tested default (`v26.0`) |
| `META_ADS_WORKSPACE` | sharing one workspace across checkouts |
| `META_ADS_AGENT_HOST` | labelling the action log with the host |
| `NO_COLOR` | plain output |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success, including a completed dry run |
| 1 | an operation failed, or validation found an error |
| 2 | bad usage, an unparseable file, or a refused guardrail |
| 130 | interrupted |
