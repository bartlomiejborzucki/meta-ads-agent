# CLI reference

`meta-ads-agent` is deliberately small. Meta's official Ads MCP is the primary
execution layer and your agent calls it directly; these commands cover what is
better done in code than in a conversation: local prerequisites, drafting and
validating a plan, turning it into MCP arguments, recording what was built, and
report arithmetic. None of them writes to Meta except the deprecated `api`
commands, which the MCP has made unnecessary since 2026-11-04.

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

## new-plan

```bash
meta-ads-agent new-plan --slug SLUG --budget AMOUNT [--offer OFFER]
  [--objective O] [--optimization-goal G] [--budget-type daily|lifetime]
  [--budget-level campaign|ad_set] [--countries PL,DE] [--age-min N] [--age-max N]
  [--assets FILE...] [--image-hash HASH]... [--video-id ID]... [--copy FILE]
  [--split auto|per-asset|per-variant|matrix|multi-variant] [--name NAME]
  [--url URL] [--page-id ID] [--instagram-account-id ID] [--account act_ID]
  [--currency CODE] [--end DATE] [--brand-file FILE] [--write] [--json]
```

Drafts a plan from what the workspace already knows, so the same ids and URLs
are not typed again for every campaign. Each value comes from the nearest place
that has it:

1. a flag;
2. the offer brief (`offers/<OFFER>.yaml`): its landing page and call to action;
3. `brand.yaml`: `account.*` (ad account, Page, Instagram account, dataset and
   conversion event, countries, objective, call to action),
   `default_destination_url`, `dsa`, `special_ad_category`, `advantage_defaults`,
   and the naming and UTM templates;
4. the cached account: its id and currency, and its Page or Instagram account
   when it has exactly one.

**It invents nothing.** A value found nowhere is listed as missing, with where
to put it, and no plan is drafted (exit 2). It does not choose an optimisation
goal, an audience beyond countries and ages, or placements: those are added to
the plan afterwards. The output says where each value came from.

Copy comes from `--copy`, or from `campaigns/<slug>/copy.yaml` - a YAML
list of variants (`angle`, `primary_text`, and optionally `headline`,
`description`, `cta_type`), or the same under a `variants:` key. Assets are
local files (`--assets`, written into the plan relative to the plan's own
directory) or media already on the account (`--image-hash`, `--video-id`).

`--split` says how copy and assets become ads:

| Split | Ads | Use |
| --- | --- | --- |
| `per-asset` | one per asset, same copy | comparing visuals |
| `per-variant` | one per copy variant, same asset | comparing angles |
| `matrix` | one per pairing | each pairing reported separately; they share the ad set's budget |
| `multi-variant` | one, with every asset and text | Meta mixes them; no per-pairing numbers |

`auto` (the default) picks `per-asset` or `per-variant` when only one of the
two has several, and refuses when both do: that is a choice between two
different tests, and it is yours.

Names and UTMs are rendered straight away, so there is no separate
`render-plan` step. Without `--write` the plan is printed; with it, it is saved
as `.meta-ads/campaigns/<slug>/plan.yaml`, and an existing plan there is never
overwritten (exit 1). Validate it next.

## duplicate-plan

```bash
meta-ads-agent duplicate-plan SOURCE --slug SLUG [--name NAME] [--currency CODE]
  [--account act_ID] [--write] [--json]
```

A campaign the agent read from Meta - campaign, ad sets, ads and creatives,
saved as JSON in the Marketing API's field names
([the shape](../../skills/meta-ads-campaign/references/duplicate-input.md)) -
becomes a new plan. Budgets and bids are converted from minor units to display
amounts, so a currency is required when any is set. Every status is PAUSED;
schedules are not copied; targeting keys the plan does not model are kept in
`targeting.raw`. Placements become the plan's `positions`, or `platforms` when
the source took whole platforms; a mix of the two stays in `targeting.raw`, with
a note. A multi-variant creative is refused, naming the ad. Without
`--write` the plan is printed; with it, it is saved as
`.meta-ads/campaigns/<slug>/plan.yaml`, and an existing plan there is never
overwritten (exit 1). Exit 2 when the source cannot be read or mapped, or
`--write` finds no workspace.

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

`{date}` is the plan's `created_at`, so rendering twice gives the same answer -
as a calendar day in the ad account's timezone when the account is cached
(`cache-account`), otherwise in UTC. An unknown token, or one with no value (no
`offer` in the plan, say), is an error naming it rather than an empty string in
a name; a UTM template is only rendered for a parameter the URL lacks.

Meta's own delivery-time macros - `{{ad.name}}`, `{{ad.id}}`, `{{adset.name}}`,
`{{adset.id}}`, `{{campaign.name}}`, `{{campaign.id}}`, `{{placement}}`,
`{{site_source_name}}` - are left exactly as written, in a template and in a
URL. Any other doubled braces around a token name are refused: they would come
out as a token, and be expanded by the next render.

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

Checks platform constraints: account state and payability, currency match,
budget conversion and level, Page and Instagram identity, dataset and event
presence, the destination URL's shape (https, a public host, no unfilled
template - it makes no network request, so it does not prove the page loads),
EU transparency fields, special-category consistency, the limits of a
multi-variant creative, and local assets: that each file is the kind the plan
uses it as, by its contents, and its dimensions.

And the advertiser's own rule: a phrase listed under `banned_phrases` in
`brand.yaml`, in any primary text, headline, description or carousel card, is an
error (`copy.banned_phrase`), whatever its case or spacing.

One warning is about fit, not validity: an asset pinned to a placement, or an ad
set whose manual placements are all Stories and Reels or all Feed, with a file
whose shape does not match (`asset.aspect_placement`). With automatic placements
it says nothing; the preview is the evidence there.

A `brand.yaml` in the workspace that cannot be read is an error
(`brand.unreadable`), not a missing file: the checks that read it did not run.

Errors block. Warnings are things a human should see, not things Meta will
reject. `--strict` treats warnings as failure, which is useful in CI and
usually wrong interactively.

Also reports which layer will perform each step, so you learn where the
fallback is involved **before** a build stops halfway for want of a token.

Account and brand files default to the workspace. Local asset paths in a plan
resolve against the **plan's** directory, so a workspace is portable.

## plan-calls

```bash
meta-ads-agent plan-calls PLAN [--account-file F] [--brand-file F]
                               [--skip-assets] [--json]
```

A validated plan, as the Meta MCP calls that build it, in order: campaign, ad
sets, uploads, creatives, ads. It does the translation that used to happen in
the conversation:

- budgets, bids and spend caps in **minor units**, with the cached account's own
  currency offset;
- `targeting`, `promoted_object` and an ad's `creative` as **JSON-encoded
  strings**. What the plan models (countries, ages, audiences, placements) wins
  over the same key in `targeting.raw`;
- the ad account id without `act_`;
- one flat parameter set per creative: a single image or video, `cards` for a
  carousel, `multi_media` for several assets, `placement_customizations` for
  assets pinned to placements; an existing post goes inline in `ads_create_ad`;
- an id that does not exist yet as `<id:PLAN_REF>` - `<id:campaign>`,
  `<id:ad_sets[0]>` - with `refs` naming the arguments that carry one.

Each call also carries `needs`: what has to be decided first. It does not guess
an optimisation goal, a video's thumbnail, or the reason Advantage+ audience is
off. `complete` is false while any remaining call needs something.

Objects already recorded in state are marked `done` and their ids filled in, so
a resumed build continues where it stopped. A local file already in the asset
manifest is not uploaded again. Each call ends with the `record` command to run
when Meta returns the id.

The plan is validated first, with the same checks as `validate-plan`: a plan
with errors, or one that changed after objects were created, produces no calls
(exit 1).

**The argument names are dated.** They follow Meta's tool schemas as read on
the day the output states (`schema_read`); Meta changes those without notice,
and this command has not been run against a live account. If a call is
rejected, the error is right. It leaves out the fields every Meta call carries
about the conversation (`client_conversation_id`, `advertiser_job`, ...), which
the agent fills per call. It changes nothing and calls nothing.

## record

```bash
meta-ads-agent record object SLUG --type campaign|ad_set|ad|creative|image|video
  --id ID --plan-ref REF [--name N] [--parent-id ID] [--status S]
  [--provider official_mcp|api_fallback] [--json]
meta-ads-agent record asset SLUG --file FILE (--image-hash H | --video-id V)
  [--plan-ref REF] [--json]
meta-ads-agent record stage SLUG validated|previewed|qa_passed|awaiting_approval [--json]
meta-ads-agent record failure SLUG --stage STAGE --message TEXT [--code N]
  [--subcode N] [--plan-ref REF] [--retry-safe] [--json]
meta-ads-agent record activation SLUG [--json]
```

Writes what happened on Meta into `campaigns/<slug>/state.json`, through the
state store: one writer at a time, two sessions' ids merged rather than
overwritten, and the ids tied to a fingerprint of the plan that produced them.
It calls nothing - the agent's MCP calls act, this records.

- **object** - an id Meta returned, against the plan element it is for
  (`--plan-ref`, as `plan-calls` names it). Recording the same id again changes
  nothing. A different id for an element that already has one is refused (exit
  1): both exist on Meta until someone looks. A status of ACTIVE is refused;
  PAUSED and DRAFT are recorded as given. The stage follows from what is
  recorded - there is no stage to set by hand during a build.
- **asset** - a local file's identity on Meta, into the asset manifest, keyed by
  the file's contents and the account: the next `plan-calls` uses it instead of
  uploading again. With `--plan-ref` it is recorded in state too.
- **stage** - the stages that have no object: `validated`, `previewed`,
  `qa_passed`, `awaiting_approval`. A stage never moves backwards.
- **failure** - a call that failed. Without `--retry-safe` it is recorded as
  not safe to retry: a timeout does not say whether the object was created, so
  the next step is to query Meta.
- **activation** - the campaign was published or activated.

Exit 1 when the plan changed after objects were created, or another id is
already recorded for that element; exit 2 for bad input, or no workspace or
plan for that slug.

## cache-account

```bash
meta-ads-agent cache-account FILE|- [--account act_ID] [--pages IDS]
  [--instagram-accounts IDS] [--datasets IDS] [--json]
```

Saves account facts the agent read from Meta (`ads_get_ad_accounts`) where
`validate-plan`, `render-plan`, `new-plan` and `plan-calls` look for them. Takes
one account object, a list, or `{"data": [...]}`; with several, `--account`
picks one. It keeps the facts a plan is checked against - currency and its
offset, timezone, status, minimum daily budget - and drops everything else.
`--pages`, `--instagram-accounts` and `--datasets` add the ids read with the
other discovery tools, comma-separated, so the validator can check a plan's
identities against them.

The first account goes to `.meta-ads/account.yaml`; a second gets
`.meta-ads/accounts/<id>.yaml`, so one account's facts never validate another's
plan. The file is stamped with the time it was read: it is a cache, and Meta
stays authoritative.

## state

```bash
meta-ads-agent state [SLUG] [--json] [--list] [--account ACT_ID]
```

Read-only and offline. Without a slug, lists campaigns. With one, shows the
stage, every created object with its provider and status, any recorded
failures and whether they were retry-safe, and what a resume would do next.

Exits `1` if the plan changed after objects were created - continuing would
apply a different plan to existing structure. A plan edited before anything
exists is not drift.

It never contacts Meta. The reconciliation read belongs to the agent through
the MCP, and the output says so.

## report

```bash
meta-ads-agent report compare INSIGHTS --days N [--end DATE | --boundary DATE]
  [--result-event ACTION_TYPE] [--attribution-days N] [--currency CODE]
  [--level ad|adset|campaign|account] [--brand-file FILE] [--json]
meta-ads-agent report breakdown INSIGHTS [--days N] [--end DATE]
  [--result-event ACTION_TYPE] [--currency CODE] [--level LEVEL] [--brand-file FILE] [--json]
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
- **breakdown** - rows exported with `publisher_platform` and
  `platform_position` breakdowns: each placement's spend, share of spend,
  and cost per result (per link click without `--result-event`), indexed
  against all placements at 100 and labelled `cheaper`, `costlier`,
  `in line`, `insufficient` or `unavailable`. A row without a placement is
  refused, since it repeats spend the placement rows already hold.
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
meta-ads-agent mcp-config [--client-id APP_ID] [--config FILE | --windows
  [--windows-home DIR]] [--dry-run] [--json]
```

Writes the `[mcp_servers.meta-ads]` block into a Codex `config.toml` - by
default `~/.codex/config.toml`, with `--windows` the Windows profile's copy
from inside WSL. Only that block is written; every other line, including
other servers and comments, is preserved byte for byte. The client id is your
Meta App ID, not a secret. Without `--client-id` the block is written with no
client id, and a warning says Meta will need one.

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

The fallback - **deprecated as of 2026-11-04**, when Meta's MCP came to cover
every one of these
([ADR-012](../architecture/adr/ADR-012-mcp-coverage-and-draft-mode.md)). The
commands still work for one more release and print a warning naming the MCP
tool to use instead; a capability that has no fallback in the registry is
refused. Needs the `api` extra and `META_ACCESS_TOKEN`. Every subcommand
takes `--json` and `--dry-run`, and every one except `delete` uses `--account`
(`delete` accepts it and ignores it: the object's id already names its
account). `123` and `act_123` are the same account. With no `--account` and no
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
`--instagram-media-id`, `--instagram-account-id` and the Page's `--page-id`
(`source_instagram_media_id`, with the Page as `object_id`).
The Instagram post is built as an inert creative. Through the MCP, pass the
post inline in `ads_create_ad`, or use `ads_boost_ig_post`, which documents
that it creates everything PAUSED
([ADR-012](../architecture/adr/ADR-012-mcp-coverage-and-draft-mode.md)).

`--carousel` reads 2 to 10 cards from `--cards`, a JSON list of
`{"image_hash" | "video_id", "headline", "description", "link", "thumbnail_hash"}`,
in order. A video card needs a still: its `thumbnail_hash`, or else one of the
frames Meta generated for the video; with neither it is refused.

`--variants` takes one variant from `--primary-text` / `--headline`, or several
from `--variants-file` (a JSON list shaped like a plan's `variants`).
`--placement HASH=instagram_stories` pins one of its assets to a placement;
at least one must stay unpinned. It takes images or videos, not both: Meta
documents one format per `asset_feed_spec`.

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
