"""Argument parsing and dispatch for ``meta-ads-agent``.

argparse rather than a CLI framework: the dependency list stays at validation
and YAML, which is what makes the default install credential-free and small.
"""

from __future__ import annotations

import argparse
import sys

from meta_ads_agent import __version__
from meta_ads_agent.cli.output import fail
from meta_ads_agent.errors import MetaAdsAgentError

_EPILOG = """\
This CLI is deliberately small.
Meta's official Ads MCP is the primary execution layer, and your agent calls
it directly. These commands only cover local prerequisites, validation, state,
and the few capabilities the official MCP does not expose.

  meta-ads-agent doctor              is everything ready?
  meta-ads-agent init                create the brand workspace
  meta-ads-agent capabilities        what routes where
  meta-ads-agent validate-plan FILE  check a plan before anything is created
  meta-ads-agent state [SLUG]        what exists, and how to resume
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

    api: argparse.ArgumentParser = _add_api_parser(subparsers)
    # Stashing the bound print_help lets `meta-ads-agent api` with no
    # subcommand show the right help without poking at argparse internals.
    api.set_defaults(api_help=api.print_help)
    return parser


def _add_api_parser(
    subparsers: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> argparse.ArgumentParser:
    api: argparse.ArgumentParser = subparsers.add_parser(
        "api",
        help="Marketing API fallback for capabilities the official MCP lacks",
        description=(
            "These commands use the official Meta Business SDK and need "
            "META_ACCESS_TOKEN plus the [api] extra. They exist only for gaps "
            "in Meta's official Ads MCP - run 'meta-ads-agent capabilities "
            "--gaps' to see which. They are not a way around the approval model."
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
        help="upload a local image (MCP has no local-file ingestion)",
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
        help="create a video, existing-post, or multi-variant creative",
    )
    mode_group = creative.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--video", action="store_true", help="single-video creative")
    mode_group.add_argument(
        "--post", action="store_true", help="promote an existing Facebook Page post"
    )
    mode_group.add_argument(
        "--variants", action="store_true", help="multi-variant creative (asset_feed_spec)"
    )
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

    delete = api_sub.add_parser(
        "delete",
        parents=[common_parent],
        help="delete a campaign, ad set, or ad (prefer pausing)",
        description=(
            "Meta's official MCP has no delete tool, so this is a real gap - "
            "but deleted objects lose their optimisation history permanently "
            "while paused objects keep it. Requires --approved and a reason."
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

    try:
        return _dispatch(args, parser)
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 1
    except KeyboardInterrupt:
        fail("interrupted. Nothing was left half-written - state is flushed after each step.")
        return 130


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

    if args.command == "state":
        from meta_ads_agent.cli.state_cmd import run_state

        return run_state(args.slug, as_json=args.json, list_all=args.list)

    if args.command == "api":
        return _dispatch_api(args, parser)

    parser.print_help()
    return 2


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
        mode = "video" if args.video else "post" if args.post else "variants"
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


if __name__ == "__main__":
    sys.exit(main())
