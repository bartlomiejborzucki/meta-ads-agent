"""Argument parsing and dispatch for ``meta-ads-agent``.

argparse rather than a CLI framework: the dependency list stays at validation
and YAML, which is what makes the default install credential-free and small.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import sys
from decimal import Decimal, InvalidOperation

from meta_ads_agent import __version__
from meta_ads_agent.cli.output import fail
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.redaction import redact

_EPILOG = """\
This CLI is deliberately small.
Meta's official Ads MCP is the primary execution layer, and your agent calls
it directly. These commands cover local prerequisites, plan scaffolding and
validation, state, and report arithmetic. The `api` commands are deprecated:
the MCP has covered what they did since 2026-11-04.

  meta-ads-agent doctor              is everything ready?
  meta-ads-agent install             copy the skills where your agent reads them
  meta-ads-agent upgrade             update the skills, then migrate the workspace
  meta-ads-agent migrate             workspace migrations only
  meta-ads-agent init                create the brand workspace
  meta-ads-agent capabilities        what routes where
  meta-ads-agent render-plan FILE    apply brand naming and UTM templates
  meta-ads-agent duplicate-plan FILE a campaign read from Meta, as a new plan
  meta-ads-agent validate-plan FILE  check a plan before anything is created
  meta-ads-agent state [SLUG]        what exists, and how to resume
  meta-ads-agent report ...          compare periods, placements, fatigue, pacing, power
  meta-ads-agent api ...             the Marketing API fallback

Docs: docs/getting-started/
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meta-ads-agent",
        description=(
            "Deterministic helpers for operating Meta Ads through Meta's "
            "official Ads MCP, with a narrow Marketing API fallback."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"meta-ads-agent {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # -- doctor ------------------------------------------------------------
    doctor = subparsers.add_parser(
        "doctor",
        help="check local prerequisites and MCP connection status",
        description=(
            "Reports readiness separately for the official MCP path and the "
            "optional API fallback. Missing fallback credentials are not an "
            "error - most users never need them."
        ),
    )
    doctor.add_argument("--json", action="store_true", help="machine-readable output")
    doctor.add_argument("--path", help="check the workspace at this project path")

    # -- init --------------------------------------------------------------
    init = subparsers.add_parser(
        "init",
        help="create the .meta-ads/ brand workspace",
        description=(
            "Creates a private brand workspace in the current project, seeded "
            "from templates. Safe to re-run: existing files are kept."
        ),
    )
    init.add_argument("--path", help="project directory (default: current)")
    init.add_argument("--brand", help="brand name to pre-fill in brand.yaml")
    init.add_argument("--force", action="store_true", help="overwrite existing template files")
    init.add_argument(
        "--check", action="store_true", help="validate an existing workspace instead of creating"
    )

    # -- capabilities ------------------------------------------------------
    caps = subparsers.add_parser(
        "capabilities",
        help="show which layer owns which capability",
        description=(
            "Prints the project's recorded capability mapping. This is not live "
            "introspection of a connected MCP session - only a running agent "
            "can do that."
        ),
    )
    caps.add_argument("name", nargs="?", help="show one capability in detail")
    caps.add_argument("--json", action="store_true")
    caps.add_argument("--area", help="filter by area, e.g. creatives")
    caps.add_argument("--gaps", action="store_true", help="only the gaps the API fallback covers")
    caps.add_argument(
        "--validate", action="store_true", help="check the registry and flag stale entries"
    )
    caps.add_argument(
        "--compare",
        metavar="TOOL_LIST",
        help=(
            "compare a live session's tool list (a file, or - for stdin) with the map; "
            "exit 1 if they differ"
        ),
    )

    # -- validate-plan -----------------------------------------------------
    validate = subparsers.add_parser(
        "validate-plan",
        help="validate a campaign plan before any write",
        description=(
            "Checks platform constraints: account state, currency, budget "
            "level, identities, tracking, EU transparency, special categories, "
            "and local assets. Errors block; warnings do not."
        ),
    )
    validate.add_argument("plan", help="path to plan.yaml")
    validate.add_argument("--account-file", help="cached account facts (default: workspace)")
    validate.add_argument("--brand-file", help="brand config (default: workspace)")
    validate.add_argument("--json", action="store_true")
    validate.add_argument(
        "--skip-assets", action="store_true", help="do not read local asset files"
    )
    validate.add_argument("--strict", action="store_true", help="treat warnings as failure")

    # -- render-plan -------------------------------------------------------
    render = subparsers.add_parser(
        "render-plan",
        help="apply brand naming and UTM templates to a plan",
        description=(
            "Expands {brand}, {objective}, {offer}, {date}, {audience} and "
            "{variant} in names, and appends brand UTMs to destination URLs that "
            "lack them. Prints every change; writes only with --write."
        ),
    )
    render.add_argument("plan", help="path to plan.yaml")
    render.add_argument("--brand-file", help="brand config (default: workspace)")
    render.add_argument("--write", action="store_true", help="save the rendered plan")
    render.add_argument("--json", action="store_true")

    # -- duplicate-plan ----------------------------------------------------
    duplicate = subparsers.add_parser(
        "duplicate-plan",
        help="turn a campaign read from Meta into a new plan, everything PAUSED",
        description=(
            "Reads a campaign, its ad sets, ads and creatives, saved as JSON in the "
            "Marketing API's field names "
            "(skills/meta-ads-campaign/references/duplicate-input.md), and "
            "builds a new plan. Budgets and bids become display amounts; schedules "
            "are not copied. Prints the plan; writes only with --write."
        ),
    )
    duplicate.add_argument("source", help="the source campaign as JSON")
    duplicate.add_argument("--slug", required=True, help="slug for the new plan")
    duplicate.add_argument("--name", help="new campaign name (default: the source's + ' (copy)')")
    duplicate.add_argument("--currency", help="account currency, to read budgets and bids")
    duplicate.add_argument("--account", help="ad account, when the source does not say")
    duplicate.add_argument("--write", action="store_true", help="save it in the workspace")
    duplicate.add_argument("--json", action="store_true")

    # -- new-plan ----------------------------------------------------------
    new_plan = subparsers.add_parser(
        "new-plan",
        help="draft a plan from the offer, brand.yaml and the cached account",
        description=(
            "Fills a campaign plan from what the workspace already knows: the offer's "
            "landing page and call to action, brand.yaml's account defaults (Page, "
            "Instagram account, dataset, countries, objective), EU transparency fields, "
            "special ad categories and Advantage preferences, and the cached account's "
            "id and currency. A flag overrides any of them. Nothing is invented: what is "
            "missing is listed, with where to put it. Prints the plan; writes only with "
            "--write."
        ),
    )
    new_plan.add_argument("--slug", required=True, help="slug for the new plan")
    new_plan.add_argument(
        "--budget", required=True, type=_amount, help="display amount, e.g. 70 for 70.00"
    )
    new_plan.add_argument("--budget-type", choices=("daily", "lifetime"), default="daily")
    new_plan.add_argument(
        "--budget-level",
        choices=("campaign", "ad_set"),
        default="campaign",
        help="where the budget sits (default: campaign)",
    )
    new_plan.add_argument("--offer", help="offer brief to promote: offers/<OFFER>.yaml")
    new_plan.add_argument(
        "--name", help="campaign name (default: brand.yaml's naming template, rendered)"
    )
    new_plan.add_argument("--objective", help="e.g. OUTCOME_SALES (default: brand.yaml)")
    new_plan.add_argument("--optimization-goal", help="valid for the objective; no default")
    new_plan.add_argument("--countries", help="comma-separated, e.g. PL,DE (default: brand.yaml)")
    new_plan.add_argument("--age-min", type=int)
    new_plan.add_argument("--age-max", type=int)
    new_plan.add_argument("--currency", help="account currency (default: the cached account's)")
    new_plan.add_argument("--account", help="ad account (default: brand.yaml, or the cached one)")
    new_plan.add_argument("--page-id", help="Facebook Page (default: brand.yaml)")
    new_plan.add_argument("--instagram-account-id", help="Instagram account (default: brand.yaml)")
    new_plan.add_argument("--url", help="destination (default: the offer's landing page)")
    new_plan.add_argument(
        "--assets", nargs="+", default=[], metavar="FILE", help="local images or videos"
    )
    new_plan.add_argument(
        "--image-hash", action="append", default=[], help="an image already on the account"
    )
    new_plan.add_argument(
        "--video-id", action="append", default=[], help="a video already on the account"
    )
    new_plan.add_argument(
        "--copy",
        help="YAML list of copy variants (default: campaigns/<slug>/copy.yaml)",
    )
    new_plan.add_argument(
        "--split",
        choices=("auto", "per-asset", "per-variant", "matrix", "multi-variant"),
        default="auto",
        help=(
            "how copy and assets become ads: one ad per asset, one per variant, one per "
            "pairing (matrix), or one ad Meta mixes (multi-variant). auto picks the only "
            "sensible one, and asks when there are several of both"
        ),
    )
    new_plan.add_argument("--end", type=_date, help="last day; required for a lifetime budget")
    new_plan.add_argument("--brand-file", help="brand config (default: workspace)")
    new_plan.add_argument("--write", action="store_true", help="save it in the workspace")
    new_plan.add_argument("--json", action="store_true")

    # -- report ------------------------------------------------------------
    report = subparsers.add_parser(
        "report",
        help="insights arithmetic: period comparison, fatigue signals, pacing",
        description=(
            "Read-only and offline. Takes insights JSON the agent read from Meta "
            "(daily rows, time_increment=1) and prints numbers with the rules that "
            "produced each label. Interpretation stays with the report and optimise "
            "skills. Input format: docs/reference/report-input.md."
        ),
    )
    report_sub = report.add_subparsers(dest="report_command", metavar="<analysis>")
    report_common = argparse.ArgumentParser(add_help=False)
    report_common.add_argument("insights", help="insights JSON file")
    report_common.add_argument("--currency", help="account currency, for labelling amounts")
    report_common.add_argument("--json", action="store_true")
    # `fatigue` is per ad by definition and always reads ad rows. It accepted
    # --level and ignored it; the flag stays (flag names are not removed within
    # a major version) and now says so.
    report_level = argparse.ArgumentParser(add_help=False)
    report_level.add_argument(
        "--level",
        choices=("ad", "adset", "campaign", "account"),
        help="use only rows of this level; needed when the export mixes levels",
    )

    compare = report_sub.add_parser(
        "compare",
        parents=[report_common, report_level],
        help="two equal-length periods, rates from sums, noise and volume stated",
    )
    compare.add_argument("--days", type=int, required=True, help="length of each window")
    where = compare.add_mutually_exclusive_group()
    where.add_argument("--end", type=_date, help="last day of the current window")
    where.add_argument(
        "--boundary", type=_date, help="first day after a known change; windows meet here"
    )
    compare.add_argument(
        "--result-event",
        help="action_type counted as a result, e.g. offsite_conversion.fb_pixel_lead",
    )
    compare.add_argument(
        "--attribution-days", type=int, help="click attribution window in days, e.g. 7"
    )
    compare.add_argument("--brand-file", help="brand config for thresholds (default: workspace)")

    breakdown = report_sub.add_parser(
        "breakdown",
        parents=[report_common, report_level],
        help="each placement's cost per result (or per click) indexed against the whole",
    )
    breakdown.add_argument("--days", type=int, help="last N days only (default: every row)")
    breakdown.add_argument("--end", type=_date, help="last day of the window")
    breakdown.add_argument(
        "--result-event",
        help="action_type counted as a result; without it placements are indexed on CPC",
    )
    breakdown.add_argument("--brand-file", help="brand config for thresholds (default: workspace)")

    fatigue = report_sub.add_parser(
        "fatigue",
        parents=[report_common],
        help="per-ad CTR vs its own baseline, frequency, spend since decline, siblings",
    )
    fatigue.add_argument("--days", type=int, default=7, help="window length (default 7)")
    fatigue.add_argument(
        "--level",
        choices=("ad", "adset", "campaign", "account"),
        help="deprecated and ignored: fatigue is always read per ad",
    )
    fatigue.add_argument("--end", type=_date, help="last day of the current window")
    fatigue.add_argument("--brand-file", help="brand config for thresholds (default: workspace)")

    pacing = report_sub.add_parser(
        "pacing",
        parents=[report_common, report_level],
        help="spend against a daily or lifetime budget",
    )
    budget_kind = pacing.add_mutually_exclusive_group(required=True)
    budget_kind.add_argument("--daily-budget", type=_amount, help="display amount per day")
    budget_kind.add_argument("--lifetime-budget", type=_amount, help="display amount in total")
    pacing.add_argument("--start", type=_date, help="first day (lifetime: schedule start)")
    pacing.add_argument("--end", type=_date, help="last day (lifetime: schedule end)")
    pacing.add_argument(
        "--as-of", type=_date, help="lifetime: the day to pace to (default: last in data)"
    )

    power = report_sub.add_parser(
        "power",
        help="the smallest lift a test can detect, or the days it needs",
        description=(
            "Before splitting live delivery into a test: two-sided, two-proportion "
            "power arithmetic, each cell against the control, alpha divided among "
            "the comparisons. Needs no insights file."
        ),
    )
    power.add_argument(
        "--baseline-rate", type=float, required=True, help="control's rate, e.g. 0.03 for 3%%"
    )
    power.add_argument(
        "--units-per-day",
        type=float,
        required=True,
        help="the rate's denominator per day per cell (clicks, or impressions)",
    )
    power.add_argument("--cells", type=int, default=2, help="cells including control (default 2)")
    target = power.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--days", type=float, help="how long it would run: gives the lift it can see"
    )
    target.add_argument("--lift", type=float, help="the lift to detect, e.g. 0.1: gives the days")
    power.add_argument("--alpha", type=float, default=0.05)
    power.add_argument("--power", type=float, default=0.8)
    power.add_argument("--json", action="store_true")

    # -- state -------------------------------------------------------------
    state = subparsers.add_parser(
        "state",
        help="inspect campaign state and plan a resume",
        description=(
            "Read-only and offline. Reports what this tool recorded and where a "
            "resume would pick up. Meta remains authoritative - re-read before "
            "mutating."
        ),
    )
    state.add_argument("slug", nargs="?", help="campaign slug (omit to list all)")
    state.add_argument("--json", action="store_true")
    state.add_argument("--list", action="store_true", help="list all campaigns")
    state.add_argument("--account", help="list only this ad account's campaigns")

    _add_build_parsers(subparsers)
    _add_install_parsers(subparsers)

    api: argparse.ArgumentParser = _add_api_parser(subparsers)
    # Stashing the bound print_help lets `meta-ads-agent api` with no
    # subcommand show the right help without poking at argparse internals.
    api.set_defaults(api_help=api.print_help)
    return parser


def _add_build_parsers(
    subparsers: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> None:
    """plan-calls, record and cache-account: the build's bookkeeping, in code.

    None of them calls Meta. `plan-calls` says what to send; the agent sends it
    through the MCP; `record` writes down what came back.
    """
    calls = subparsers.add_parser(
        "plan-calls",
        help="a validated plan as the Meta MCP calls that build it",
        description=(
            "Prints the tool and arguments for every object the plan needs, in build "
            "order: budgets in minor units, targeting and creative as JSON strings, ids "
            "that do not exist yet as <id:PLAN_REF>. Objects already recorded are marked "
            "done. The plan is validated first; a plan with errors produces no calls. "
            "Argument names follow Meta's tool schemas as read on a stated date - a "
            "rejected call is settled by its error. Changes nothing, calls nothing."
        ),
    )
    calls.add_argument("plan", help="path to plan.yaml")
    calls.add_argument("--account-file", help="cached account facts (default: workspace)")
    calls.add_argument("--brand-file", help="brand config (default: workspace)")
    calls.add_argument("--skip-assets", action="store_true", help="do not read local asset files")
    calls.add_argument("--json", action="store_true")

    record = subparsers.add_parser(
        "record",
        help="write an id, stage or failure from a build into campaign state",
        description=(
            "Records what happened on Meta, through the state store: one writer at a "
            "time, two sessions merged rather than overwritten, ids tied to the plan "
            "that produced them. Calls nothing - the agent's MCP calls act, this records."
        ),
    )
    record_sub = record.add_subparsers(dest="record_command", metavar="<what>")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("slug", help="campaign slug")
    common.add_argument("--json", action="store_true")

    obj = record_sub.add_parser(
        "object", parents=[common], help="an id Meta returned, against its plan element"
    )
    obj.add_argument(
        "--type",
        required=True,
        dest="object_type",
        choices=("campaign", "ad_set", "ad", "creative", "image", "video"),
    )
    obj.add_argument("--id", required=True, dest="object_id", help="the id Meta returned")
    obj.add_argument(
        "--plan-ref",
        required=True,
        help="the plan element, as plan-calls names it: campaign, ad_sets[0], ad_sets[0].ads[1]",
    )
    obj.add_argument("--name")
    obj.add_argument("--parent-id", help="the campaign of an ad set, the ad set of an ad")
    obj.add_argument("--status", help="the status Meta reported: PAUSED, or DRAFT")
    obj.add_argument("--provider", choices=("official_mcp", "api_fallback"), default="official_mcp")

    stage = record_sub.add_parser(
        "stage", parents=[common], help="a stage with no object of its own"
    )
    stage.add_argument(
        "stage",
        choices=("validated", "previewed", "qa_passed", "awaiting_approval"),
        help="object stages follow from `record object`; activation has its own command",
    )

    failure = record_sub.add_parser(
        "failure", parents=[common], help="a call that failed, and whether a retry is safe"
    )
    failure.add_argument(
        "--stage",
        required=True,
        choices=(
            "campaign_created",
            "ad_sets_created",
            "assets_uploaded",
            "creatives_created",
            "ads_created",
            "previewed",
            "activated",
        ),
        help="the stage the failed call belonged to",
    )
    failure.add_argument("--message", required=True)
    failure.add_argument("--code", type=int, help="Meta's error code")
    failure.add_argument("--subcode", type=int, help="Meta's error subcode")
    failure.add_argument("--plan-ref", help="the plan element the call was for")
    failure.add_argument(
        "--retry-safe",
        action="store_true",
        help=(
            "Meta refused the call outright, so nothing was created. Leave it off after "
            "a timeout or an unclear answer: the object may exist"
        ),
    )

    record_sub.add_parser(
        "activation", parents=[common], help="the campaign was published or activated"
    )

    asset = record_sub.add_parser(
        "asset", parents=[common], help="a local file's id on Meta, so it uploads once"
    )
    asset.add_argument("--file", required=True, help="the local file that was uploaded")
    asset.add_argument("--image-hash")
    asset.add_argument("--video-id")
    asset.add_argument("--plan-ref", help="also record it in state against this plan element")
    asset.add_argument(
        "--provider", choices=("official_mcp", "api_fallback"), default="official_mcp"
    )
    record.set_defaults(record_help=record.print_help)

    cache = subparsers.add_parser(
        "cache-account",
        help="save account facts read from Meta for the validator",
        description=(
            "Takes the account as Meta returned it (ads_get_ad_accounts) - one object, a "
            'list, or {"data": [...]} - and writes the facts validate-plan checks a plan '
            "against: currency and its offset, timezone, status, minimum budget. Unknown "
            "fields are dropped. A second account gets accounts/<id>.yaml."
        ),
    )
    cache.add_argument("source", help="JSON file, or - for stdin")
    cache.add_argument("--account", help="which account, when the input has several")
    cache.add_argument("--pages", help="comma-separated Page ids available to the account")
    cache.add_argument("--instagram-accounts", help="comma-separated Instagram account ids")
    cache.add_argument("--datasets", help="comma-separated dataset (pixel) ids")
    cache.add_argument("--json", action="store_true")


def _add_install_parsers(
    subparsers: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> None:
    """Install, upgrade, migrate, and the two Windows hand-offs.

    A host does not run anything for us after it copies a plugin in, so the
    update path has to be a command somebody types. Keeping it in the CLI
    also keeps it testable, which a host hook would not be.
    """
    target_parent = argparse.ArgumentParser(add_help=False)
    target_parent.add_argument(
        "--target",
        choices=["agents", "windows-codex", "path"],
        default="agents",
        help=(
            "where the skills go: 'agents' for ~/.agents/skills, 'windows-codex' "
            "for the Windows user profile seen from WSL, 'path' for --path"
        ),
    )
    target_parent.add_argument("--path", help="explicit skills directory (with --target path)")
    target_parent.add_argument(
        "--windows-home", help="POSIX path of the Windows user profile, e.g. /mnt/c/Users/you"
    )
    target_parent.add_argument("--json", action="store_true")
    target_parent.add_argument(
        "--dry-run", action="store_true", help="show what would change, write nothing"
    )

    install = subparsers.add_parser(
        "install",
        parents=[target_parent],
        help="copy the skills into a directory your agent reads",
        description=(
            "Copies the skill payload and verifies every file against the "
            "release manifest. Safe to re-run: an install that is already "
            "current does nothing, and a partial one is completed."
        ),
    )
    install.add_argument(
        "--force", action="store_true", help="rewrite every file, even ones that already match"
    )
    install.add_argument(
        "--no-backup", action="store_true", help="do not archive the current installation first"
    )

    upgrade = subparsers.add_parser(
        "upgrade",
        parents=[target_parent],
        help="update the skills, then run any outstanding workspace migrations",
        description=(
            "The skills first, the workspace second. The installed version is "
            "recorded only after every file has been verified, so an upgrade "
            "that is interrupted reports itself as interrupted rather than as "
            "done."
        ),
    )
    upgrade.add_argument("--workspace", help="workspace to migrate (default: the one found here)")
    upgrade.add_argument(
        "--allow-migration-scripts",
        action="store_true",
        help="permit migrations carried out by a script shipped in the payload",
    )
    upgrade.add_argument(
        "--rollback", action="store_true", help="restore the most recent backup and stop"
    )

    migrate = subparsers.add_parser(
        "migrate",
        help="apply outstanding workspace migrations, once each",
        description=(
            "Operates on .meta-ads/ only. The workspace is copied aside before "
            "the first change, every migration checks whether its effect is "
            "already present, and the ledger records each one as it succeeds."
        ),
    )
    migrate.add_argument("--workspace", help="workspace directory (default: the one found here)")
    migrate.add_argument("--json", action="store_true")
    migrate.add_argument("--dry-run", action="store_true", help="list what would run")
    migrate.add_argument(
        "--allow-migration-scripts",
        action="store_true",
        help="permit migrations carried out by a script shipped in the payload",
    )

    mcp = subparsers.add_parser(
        "mcp-config",
        help="add the Meta Ads MCP server to a Codex config.toml",
        description=(
            "Writes only the [mcp_servers.meta-ads] block. Every other line of "
            "the file is preserved byte for byte - it is the user's config, not "
            "ours."
        ),
    )
    mcp.add_argument("--client-id", help="your Meta App ID, used as the OAuth client id")
    mcp.add_argument(
        "--windows",
        action="store_true",
        help="write to the Windows profile's .codex/config.toml, from inside WSL",
    )
    mcp.add_argument("--windows-home", help="POSIX path of the Windows user profile")
    mcp.add_argument("--config", help="explicit config.toml path")
    mcp.add_argument("--json", action="store_true")
    mcp.add_argument("--dry-run", action="store_true")

    open_url = subparsers.add_parser(
        "open-url",
        help="open a URL in the Windows browser (for OAuth from inside WSL)",
        description=(
            "Hands the URL to explorer.exe so it lands in the Windows browser "
            "profile the user is already signed into. There is no Linux "
            "browser fallback: a browser inside WSL has a different profile, "
            "so the OAuth round trip would not complete."
        ),
    )
    open_url.add_argument("url", help="https URL to open")
    open_url.add_argument("--json", action="store_true")


def _add_api_parser(
    subparsers: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> argparse.ArgumentParser:
    api: argparse.ArgumentParser = subparsers.add_parser(
        "api",
        help="deprecated Marketing API fallback; Meta's MCP now does all of this",
        description=(
            "DEPRECATED. These commands use the official Meta Business SDK and need "
            "META_ACCESS_TOKEN plus the [api] extra. They were written for gaps in "
            "Meta's official Ads MCP, which has covered every one since 2026-11-04 "
            "('meta-ads-agent capabilities --gaps' lists none); they remain for one "
            "release, for a terminal host with a local file and no public URL. They "
            "are not a way around the approval model."
        ),
    )
    api_sub = api.add_subparsers(dest="api_command", metavar="<subcommand>")

    common_parent = argparse.ArgumentParser(add_help=False)
    common_parent.add_argument("--account", help="ad account id (act_...)")
    common_parent.add_argument("--json", action="store_true")
    common_parent.add_argument(
        "--dry-run", action="store_true", help="describe what would happen, change nothing"
    )

    image = api_sub.add_parser(
        "upload-image",
        parents=[common_parent],
        help="upload a local image (deprecated: the MCP's ads_creative_upload_media does this)",
    )
    image.add_argument("path", help="local image file")

    video = api_sub.add_parser(
        "upload-video",
        parents=[common_parent],
        help="upload a local video and wait for processing",
    )
    video.add_argument("path", help="local video file")
    video.add_argument(
        "--no-wait",
        action="store_true",
        help="return as soon as the id exists (a creative will reject it until ready)",
    )
    video.add_argument(
        "--timeout", type=float, default=900.0, help="seconds to wait for processing"
    )

    creative = api_sub.add_parser(
        "create-creative",
        parents=[common_parent],
        help="create a video, existing-post, multi-variant, or carousel creative",
    )
    mode_group = creative.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--video", action="store_true", help="single-video creative")
    mode_group.add_argument(
        "--post",
        action="store_true",
        help="promote an existing post: a Facebook Page post or an Instagram post",
    )
    mode_group.add_argument(
        "--variants", action="store_true", help="multi-variant creative (asset_feed_spec)"
    )
    mode_group.add_argument("--carousel", action="store_true", help="2 to 10 cards, from --cards")
    creative.add_argument("--name", required=True, help="creative name")
    creative.add_argument("--page-id", help="Facebook Page id")
    creative.add_argument("--video-id", help="uploaded video id")
    creative.add_argument("--post-id", help="existing post id, e.g. 1234_5678")
    creative.add_argument(
        "--image-hash",
        action="append",
        default=[],
        dest="image_hashes",
        help="image hash (repeatable)",
    )
    creative.add_argument("--url", dest="destination_url", help="destination URL")
    creative.add_argument("--primary-text", help="primary text")
    creative.add_argument("--headline", help="headline")
    creative.add_argument("--cta", help="call-to-action type, e.g. SIGN_UP")
    creative.add_argument("--instagram-account-id", help="Instagram identity")
    creative.add_argument("--instagram-media-id", help="existing Instagram post (with --post)")
    creative.add_argument("--cards", dest="cards_file", help="carousel cards, a JSON list")
    creative.add_argument("--variants-file", help="copy variants, a JSON list (with --variants)")
    creative.add_argument(
        "--placement",
        action="append",
        default=[],
        dest="placements",
        metavar="ASSET=PLACEMENT",
        help="pin an image hash or video id to a placement (with --variants, repeatable)",
    )

    delete = api_sub.add_parser(
        "delete",
        parents=[common_parent],
        help="delete a campaign, ad set, or ad (prefer pausing)",
        description=(
            "Deprecated: through the MCP a delete is ads_update_entity with "
            "status DELETED. Deleted objects lose their optimisation history "
            "permanently while paused objects keep it. Requires --approved - "
            "pass it only after the user approved this deletion - and a reason."
        ),
    )
    delete.add_argument("object_id", help="object id to delete")
    delete.add_argument(
        "--type", required=True, choices=["campaign", "ad_set", "ad"], dest="object_type"
    )
    delete.add_argument("--reason", required=True, help="why pausing is insufficient")
    delete.add_argument(
        "--approved",
        action="store_true",
        help="assert the user explicitly approved this deletion",
    )

    return api


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    # The optional ./.env for the API fallback's META_* settings; the
    # environment always wins (meta_ads_agent.envfile).
    from meta_ads_agent import envfile

    envfile.apply()

    # Imported here, not at module level: the packaging checks load this
    # module for its argument parser under a bare Python, with no pydantic.
    from pydantic import ValidationError as PydanticValidationError

    try:
        return _dispatch(args, parser)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1
    except PydanticValidationError as exc:
        # A bad value on the command line (``--cta sign_up``) reaches a model
        # before it reaches Meta. That is a usage error, not a crash.
        fail(redact(str(exc)))
        return 2
    except KeyboardInterrupt:
        fail("interrupted. Nothing was left half-written - state is flushed after each step.")
        return 130


def _date(value: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {value!r}") from exc


def _amount(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"not an amount: {value!r}") from exc
    if not amount.is_finite() or amount <= 0:
        raise argparse.ArgumentTypeError(f"an amount must be positive: {value!r}")
    return amount


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    # Imported lazily so `--help` and `doctor` stay fast and so a missing
    # optional dependency cannot break unrelated commands.
    if args.command == "doctor":
        from meta_ads_agent.cli.doctor import run_doctor

        return run_doctor(as_json=args.json, workspace_hint=args.path)

    if args.command == "init":
        from meta_ads_agent.cli.init_cmd import run_init

        return run_init(
            path=args.path, brand_name=args.brand, force=args.force, check_only=args.check
        )

    if args.command == "capabilities":
        from meta_ads_agent.cli.capabilities_cmd import run_capabilities

        return run_capabilities(
            as_json=args.json,
            validate=args.validate,
            area=args.area,
            gaps_only=args.gaps,
            capability=args.name,
            compare_with=args.compare,
        )

    if args.command == "validate-plan":
        from meta_ads_agent.cli.validate_cmd import run_validate_plan

        return run_validate_plan(
            args.plan,
            account_path=args.account_file,
            brand_path=args.brand_file,
            as_json=args.json,
            skip_assets=args.skip_assets,
            strict=args.strict,
        )

    if args.command == "render-plan":
        from meta_ads_agent.cli.render_cmd import run_render_plan

        return run_render_plan(
            args.plan, brand_path=args.brand_file, write=args.write, as_json=args.json
        )

    if args.command == "duplicate-plan":
        from meta_ads_agent.cli.duplicate_cmd import run_duplicate_plan

        return run_duplicate_plan(
            args.source,
            slug=args.slug,
            name=args.name,
            currency=args.currency,
            account=args.account,
            write=args.write,
            as_json=args.json,
        )

    if args.command == "new-plan":
        from meta_ads_agent.cli.new_plan_cmd import run_new_plan

        return run_new_plan(
            slug=args.slug,
            budget=args.budget,
            offer_slug=args.offer,
            objective=args.objective,
            budget_type=args.budget_type,
            budget_level=args.budget_level,
            currency=args.currency,
            countries=args.countries,
            age_min=args.age_min,
            age_max=args.age_max,
            account_id=args.account,
            page_id=args.page_id,
            instagram_account_id=args.instagram_account_id,
            url=args.url,
            optimization_goal=args.optimization_goal,
            assets=args.assets,
            image_hashes=args.image_hash,
            video_ids=args.video_id,
            copy_path=args.copy,
            split=args.split,
            name=args.name,
            end=args.end,
            brand_path=args.brand_file,
            write=args.write,
            as_json=args.json,
        )

    if args.command == "plan-calls":
        from meta_ads_agent.cli.plan_calls_cmd import run_plan_calls

        return run_plan_calls(
            args.plan,
            account_path=args.account_file,
            brand_path=args.brand_file,
            as_json=args.json,
            skip_assets=args.skip_assets,
        )

    if args.command == "record":
        return _dispatch_record(args)

    if args.command == "cache-account":
        from meta_ads_agent.cli.record_cmd import run_cache_account

        return run_cache_account(
            args.source,
            account=args.account,
            pages=args.pages,
            instagram_accounts=args.instagram_accounts,
            datasets=args.datasets,
            as_json=args.json,
        )

    if args.command == "report":
        return _dispatch_report(args, parser)

    if args.command == "state":
        from meta_ads_agent.cli.state_cmd import run_state

        return run_state(args.slug, as_json=args.json, list_all=args.list, account=args.account)

    if args.command in ("install", "upgrade", "migrate", "mcp-config", "open-url"):
        return _dispatch_install(args)

    if args.command == "api":
        return _dispatch_api(args, parser)

    parser.print_help()
    return 2


def _dispatch_record(args: argparse.Namespace) -> int:
    from meta_ads_agent.cli import record_cmd

    what = args.record_command
    if what == "object":
        return record_cmd.run_record_object(
            args.slug,
            object_type=args.object_type,
            object_id=args.object_id,
            plan_ref=args.plan_ref,
            name=args.name,
            parent_id=args.parent_id,
            status=args.status,
            provider=args.provider,
            as_json=args.json,
        )
    if what == "stage":
        return record_cmd.run_record_stage(args.slug, stage=args.stage, as_json=args.json)
    if what == "failure":
        return record_cmd.run_record_failure(
            args.slug,
            stage=args.stage,
            message=args.message,
            code=args.code,
            subcode=args.subcode,
            retry_safe=args.retry_safe,
            plan_ref=args.plan_ref,
            as_json=args.json,
        )
    if what == "activation":
        return record_cmd.run_record_activation(args.slug, as_json=args.json)
    if what == "asset":
        return record_cmd.run_record_asset(
            args.slug,
            file=args.file,
            image_hash=args.image_hash,
            video_id=args.video_id,
            plan_ref=args.plan_ref,
            provider=args.provider,
            as_json=args.json,
        )
    args.record_help()
    return 2


def _dispatch_install(args: argparse.Namespace) -> int:
    from meta_ads_agent.cli import install_cmd

    if args.command == "install":
        return install_cmd.run_install(
            target_kind=args.target,
            path=args.path,
            windows_home=args.windows_home,
            force=args.force,
            no_backup=args.no_backup,
            dry_run=args.dry_run,
            as_json=args.json,
        )

    if args.command == "upgrade":
        return install_cmd.run_upgrade(
            target_kind=args.target,
            path=args.path,
            windows_home=args.windows_home,
            workspace_path=args.workspace,
            allow_scripts=args.allow_migration_scripts,
            do_rollback=args.rollback,
            dry_run=args.dry_run,
            as_json=args.json,
        )

    if args.command == "migrate":
        return install_cmd.run_migrate(
            workspace_path=args.workspace,
            allow_scripts=args.allow_migration_scripts,
            dry_run=args.dry_run,
            as_json=args.json,
        )

    if args.command == "mcp-config":
        return install_cmd.run_mcp_config(
            client_id=args.client_id,
            windows=args.windows,
            windows_home=args.windows_home,
            config_path=args.config,
            dry_run=args.dry_run,
            as_json=args.json,
        )

    return install_cmd.run_open_url(args.url, as_json=args.json)


def _dispatch_api(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from meta_ads_agent.cli import api_cmd

    if not getattr(args, "api_command", None):
        api_help = getattr(args, "api_help", None)
        if callable(api_help):
            api_help()
        else:
            parser.print_help()
        return 0

    if args.api_command == "upload-image":
        return api_cmd.run_upload_image(
            args.path, account=args.account, dry_run=args.dry_run, as_json=args.json
        )

    if args.api_command == "upload-video":
        return api_cmd.run_upload_video(
            args.path,
            account=args.account,
            dry_run=args.dry_run,
            as_json=args.json,
            wait=not args.no_wait,
            timeout=args.timeout,
        )

    if args.api_command == "create-creative":
        mode = (
            "video"
            if args.video
            else "post"
            if args.post
            else "carousel"
            if args.carousel
            else "variants"
        )
        return api_cmd.run_create_creative(
            mode=mode,
            name=args.name,
            account=args.account,
            page_id=args.page_id,
            video_id=args.video_id,
            post_id=args.post_id,
            image_hashes=args.image_hashes,
            destination_url=args.destination_url,
            primary_text=args.primary_text,
            headline=args.headline,
            cta=args.cta,
            instagram_account_id=args.instagram_account_id,
            dry_run=args.dry_run,
            as_json=args.json,
            instagram_media_id=args.instagram_media_id,
            cards_file=args.cards_file,
            variants_file=args.variants_file,
            placements=args.placements,
        )

    if args.api_command == "delete":
        return api_cmd.run_delete(
            args.object_id,
            object_type=args.object_type,
            reason_text=args.reason,
            approved=args.approved,
            dry_run=args.dry_run,
            as_json=args.json,
        )

    return 2


def _dispatch_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from meta_ads_agent.cli import report_cmd

    if args.report_command == "compare":
        return report_cmd.run_compare(
            args.insights,
            days=args.days,
            end=args.end,
            boundary=args.boundary,
            result_event=args.result_event,
            currency=args.currency,
            attribution_days=args.attribution_days,
            brand_path=args.brand_file,
            as_json=args.json,
            level=args.level,
        )
    if args.report_command == "breakdown":
        return report_cmd.run_breakdown(
            args.insights,
            days=args.days,
            end=args.end,
            result_event=args.result_event,
            currency=args.currency,
            brand_path=args.brand_file,
            as_json=args.json,
            level=args.level,
        )
    if args.report_command == "fatigue":
        if args.level and args.level != "ad":
            from meta_ads_agent.cli.output import warn

            warn(
                f"--level {args.level} is ignored: fatigue is always read per ad. "
                "The flag is deprecated here."
            )
        return report_cmd.run_fatigue(
            args.insights,
            days=args.days,
            end=args.end,
            currency=args.currency,
            brand_path=args.brand_file,
            as_json=args.json,
        )
    if args.report_command == "pacing":
        return report_cmd.run_pacing(
            args.insights,
            daily_budget=args.daily_budget,
            lifetime_budget=args.lifetime_budget,
            start=args.start,
            end=args.end,
            as_of=args.as_of,
            currency=args.currency,
            as_json=args.json,
            level=args.level,
        )
    if args.report_command == "power":
        return report_cmd.run_power(
            baseline_rate=args.baseline_rate,
            units_per_day=args.units_per_day,
            cells=args.cells,
            days=args.days,
            lift=args.lift,
            alpha=args.alpha,
            power=args.power,
            as_json=args.json,
        )
    # No analysis named: show what there is, and say so with the exit code.
    # argparse's --help exits 0 by itself, which read as success to a script.
    with contextlib.suppress(SystemExit):
        parser.parse_args(["report", "--help"])
    return 2


if __name__ == "__main__":
    sys.exit(main())
