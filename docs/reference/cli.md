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
exposes, ask your agent to list its tools.

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
meta-ads-agent state [SLUG] [--json] [--list]
```

Read-only and offline. Without a slug, lists campaigns. With one, shows the
stage, every created object with its provider and status, any recorded
failures and whether they were retry-safe, and what a resume would do next.

Exits `1` if the plan changed after objects were created - continuing would
apply a different plan to existing structure.

It never contacts Meta. The reconciliation read belongs to the agent through
the MCP, and the output says so.

## api

The fallback. Needs the `api` extra and `META_ACCESS_TOKEN`. Every subcommand
takes `--account`, `--json`, and `--dry-run`.

**Dry runs work before any credentials exist** - that is their point.

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
meta-ads-agent api create-creative (--video | --post | --variants)
  --name NAME [--page-id ID] [--video-id ID] [--post-id ID]
  [--image-hash HASH ...] [--url URL] [--primary-text TEXT]
  [--headline TEXT] [--cta TYPE] [--instagram-account-id ID]
```

`--post` promotes an existing Facebook Page post via `object_story_id`, which
preserves its engagement. Recreating the content as a new dark post would not.

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
