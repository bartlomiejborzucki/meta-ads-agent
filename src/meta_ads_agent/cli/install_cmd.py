"""``install``, ``upgrade``, ``migrate``, ``mcp-config`` and ``open-url``.

Codex runs nothing for us after an install. Its plugin cache is keyed by
version, its only documented hook is ``SessionStart``, and it skips even that
until the user has reviewed and trusted the definition. So the update path is
a command the user runs, and the job of these commands is to make running it
boring: idempotent, interruptible, and honest about what it did.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meta_ads_agent import __version__
from meta_ads_agent.cli.output import echo, emit_json, fail, heading, warn
from meta_ads_agent.errors import ConfigError, MetaAdsAgentError, StateError
from meta_ads_agent.install import packaged
from meta_ads_agent.install.engine import apply_install, plan_install, rollback
from meta_ads_agent.install.migrations import (
    MigrationLedger,
    MigrationRun,
    collect_migrations,
    run_migrations,
)
from meta_ads_agent.install.state import InstallState
from meta_ads_agent.install.targets import InstallTarget, resolve_target
from meta_ads_agent.install.wsl import WslBridge, merge_codex_config
from meta_ads_agent.workspace import Workspace

MCP_SERVER_NAME = "meta-ads"
MCP_URL = "https://mcp.facebook.com/ads"


def _target(args: Any) -> InstallTarget:
    return resolve_target(
        getattr(args, "target", "agents") or "agents",
        path=getattr(args, "path", None),
        windows_home=getattr(args, "windows_home", None),
    )


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------
def _install_payload(
    *,
    target_kind: str = "agents",
    path: str | None = None,
    windows_home: str | None = None,
    force: bool = False,
    no_backup: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Do the install (unless dry) and describe it, without printing."""
    target = resolve_target(target_kind, path=path, windows_home=windows_home)
    manifest = packaged.release_manifest()
    source = packaged.payload_source()
    plan = plan_install(manifest, source, target, force=force)

    if dry_run:
        return plan.as_dict()
    if plan.action == "up-to-date" and not plan.resuming:
        return {**plan.as_dict(), "verification": {"complete": True}}

    result = apply_install(
        plan,
        source,
        method="sync-windows" if target.is_windows else "sync",
        backup=not no_backup,
    )
    return result.as_dict()


def run_install(
    *,
    target_kind: str = "agents",
    path: str | None = None,
    windows_home: str | None = None,
    force: bool = False,
    no_backup: bool = False,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    if as_json:
        emit_json(
            _install_payload(
                target_kind=target_kind,
                path=path,
                windows_home=windows_home,
                force=force,
                no_backup=no_backup,
                dry_run=dry_run,
            )
        )
        return 0

    target = resolve_target(target_kind, path=path, windows_home=windows_home)
    manifest = packaged.release_manifest()
    source = packaged.payload_source()
    plan = plan_install(manifest, source, target, force=force)

    if dry_run:
        _render_plan(plan)
        echo("")
        echo("  dry run - nothing was written.")
        return 0

    if plan.action == "up-to-date" and not plan.resuming:
        _render_plan(plan)
        return 0

    result = apply_install(
        plan,
        source,
        method="sync-windows" if target.is_windows else "sync",
        backup=not no_backup,
    )
    _render_plan(plan)
    heading("Result")
    echo(f"  version    {manifest.version}")
    echo(f"  files      {len(manifest.entries)} verified against the release manifest")
    if result.backup:
        echo(f"  backup     {result.backup}")
    if target.is_windows:
        echo("")
        echo("  The Codex application reads this directory as")
        default_spelling = "%USERPROFILE%" + "\\.agents\\skills"
        echo(f"    {target.windows_path or default_spelling}")
        echo("  Start a new Codex session: skills load at session start.")
    return 0


def _render_plan(plan: Any) -> None:
    heading(f"meta-ads-agent {plan.action}")
    echo(f"  target     {plan.target.describe()}")
    echo(f"  from       {plan.from_version or 'not installed'}")
    echo(f"  to         {plan.manifest.version}")
    if plan.resuming and plan.state.in_progress:
        progress = plan.state.in_progress
        echo("")
        warn(
            f"the previous update stopped during '{progress.stage}' "
            f"({progress.from_version} -> {progress.to_version}, started {progress.started_at}). "
            "Continuing from the package; nothing was left marked as current."
        )
    echo("")
    echo(f"  new        {len(plan.added)}")
    echo(f"  changed    {len(plan.updated)}")
    echo(f"  unchanged  {len(plan.unchanged)}")
    echo(f"  removed    {len(plan.removed)} file(s), {len(plan.removed_skills)} skill(s)")
    for group, label in (
        (plan.added, "new"),
        (plan.updated, "changed"),
        (plan.removed, "removed"),
    ):
        for item in sorted(group)[:12]:
            echo(f"    {label:<8} {item}", "dim")
        if len(group) > 12:
            echo(f"    {'':<8} ... and {len(group) - 12} more", "dim")
    for skill in sorted(plan.removed_skills):
        echo(f"    dropped  {skill}/ (no longer part of this release)", "dim")


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------
def run_upgrade(
    *,
    target_kind: str = "agents",
    path: str | None = None,
    windows_home: str | None = None,
    workspace_path: str | None = None,
    allow_scripts: bool = False,
    do_rollback: bool = False,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    target = resolve_target(target_kind, path=path, windows_home=windows_home)

    if do_rollback:
        restored = rollback(target)
        state = InstallState.load(target.root)
        if as_json:
            emit_json({"rolled_back_to": str(restored), "version": state.version})
        else:
            heading("Rolled back")
            echo(f"  restored   {restored}")
            echo(f"  version    {state.version or 'unknown'}")
            echo("  User data in .meta-ads/ was not part of this and is untouched.")
        return 0

    # Code first, then data. A migration that runs against a half-copied
    # payload is a migration reading the wrong schema.
    if not as_json:
        code = run_install(
            target_kind=target_kind, path=path, windows_home=windows_home, dry_run=dry_run
        )
        if code != 0:
            return code
        return run_migrate(
            workspace_path=workspace_path,
            allow_scripts=allow_scripts,
            dry_run=dry_run,
            target_kind=target_kind,
            path=path,
            windows_home=windows_home,
            required=False,
        )

    # One document, not two concatenated ones: a caller parsing our output
    # should not have to split it.
    install_payload = _install_payload(
        target_kind=target_kind, path=path, windows_home=windows_home, dry_run=dry_run
    )
    migration_payload = _migrate_payload(
        workspace_path=workspace_path,
        allow_scripts=allow_scripts,
        dry_run=dry_run,
        target_kind=target_kind,
        path=path,
        windows_home=windows_home,
    )
    emit_json({**install_payload, "migrations": migration_payload})
    return 1 if migration_payload.get("failed") else 0


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------
def _migrate_payload(
    *,
    workspace_path: str | None = None,
    allow_scripts: bool = False,
    dry_run: bool = False,
    target_kind: str = "agents",
    path: str | None = None,
    windows_home: str | None = None,
) -> dict[str, Any]:
    workspace, run = _migrate(
        workspace_path=workspace_path,
        allow_scripts=allow_scripts,
        dry_run=dry_run,
        target_kind=target_kind,
        path=path,
        windows_home=windows_home,
    )
    if run is None:
        return {
            "workspace": str(workspace.root),
            "applied": [],
            "pending": [],
            "note": "no workspace found - nothing to migrate",
        }
    return {"workspace": str(workspace.root), **run.as_dict()}


def _migrate(
    *,
    workspace_path: str | None,
    allow_scripts: bool,
    dry_run: bool,
    target_kind: str,
    path: str | None,
    windows_home: str | None,
) -> tuple[Workspace, MigrationRun | None]:
    workspace = (
        Workspace.at(Path(workspace_path).expanduser())
        if workspace_path
        else Workspace.locate(required=False)
    )
    if not workspace.exists:
        return workspace, None

    manifest = packaged.release_manifest()
    try:
        payload_root = resolve_target(target_kind, path=path, windows_home=windows_home).root
    except ConfigError:
        payload_root = packaged.payload_source()

    migrations = collect_migrations(payload_root=payload_root, refs=manifest.migrations)
    return workspace, run_migrations(
        workspace,
        migrations,
        version=manifest.version,
        allow_scripts=allow_scripts,
        dry_run=dry_run,
    )


def run_migrate(
    *,
    workspace_path: str | None = None,
    allow_scripts: bool = False,
    dry_run: bool = False,
    as_json: bool = False,
    target_kind: str = "agents",
    path: str | None = None,
    windows_home: str | None = None,
    required: bool = True,
) -> int:
    if as_json:
        payload = _migrate_payload(
            workspace_path=workspace_path,
            allow_scripts=allow_scripts,
            dry_run=dry_run,
            target_kind=target_kind,
            path=path,
            windows_home=windows_home,
        )
        emit_json(payload)
        if payload.get("note"):
            return 1 if required else 0
        return 1 if payload.get("failed") else 0

    workspace, run = _migrate(
        workspace_path=workspace_path,
        allow_scripts=allow_scripts,
        dry_run=dry_run,
        target_kind=target_kind,
        path=path,
        windows_home=windows_home,
    )
    if run is None:
        echo("")
        echo(f"  no workspace at {workspace.root} - nothing to migrate.")
        return 1 if required else 0

    heading("Workspace migrations")
    echo(f"  workspace  {workspace.root}")
    for outcome in run.outcomes:
        echo(f"  {outcome.status:<24} {outcome.id}")
        if outcome.detail:
            echo(f"    {outcome.detail}", "dim")
    if run.backup:
        echo("")
        echo(f"  backup     {run.backup}")
        echo("  Taken before the first change. Delete it once you are satisfied.")
    if run.failed:
        echo("")
        fail(f"migration stopped: {run.failed}")
        echo("  Later migrations were not attempted. The workspace backup above")
        echo("  is the state before this run started.")
        return 1
    if not run.outcomes:
        echo("  nothing to do")
    return 0


# ---------------------------------------------------------------------------
# mcp-config
# ---------------------------------------------------------------------------
def run_mcp_config(
    *,
    client_id: str | None = None,
    windows: bool = False,
    windows_home: str | None = None,
    config_path: str | None = None,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    """Write only the ``[mcp_servers.meta-ads]`` block into Codex's config.

    Everything else in that file belongs to the user - other servers, model
    settings, approval policy, their comments. Rewriting the document would
    be the easiest way to implement this and the easiest way to lose
    something they care about, so the block is spliced in by text.
    """
    bridge = WslBridge.detect()
    if config_path:
        target_file = Path(config_path).expanduser()
    elif windows:
        profile = Path(windows_home).expanduser() if windows_home else bridge.windows_home()
        target_file = profile / ".codex" / "config.toml"
    else:
        target_file = Path.home() / ".codex" / "config.toml"

    original = target_file.read_text(encoding="utf-8") if target_file.is_file() else ""
    updated, changed = merge_codex_config(
        original, server=MCP_SERVER_NAME, url=MCP_URL, client_id=client_id
    )

    if as_json:
        emit_json(
            {
                "config": str(target_file),
                "changed": changed,
                "dry_run": dry_run,
                "client_id_set": bool(client_id),
            }
        )
        if not dry_run and changed:
            _write_config(target_file, updated)
        return 0

    heading("Codex MCP configuration")
    echo(f"  file       {target_file}")
    if not changed:
        echo("  already correct - nothing written")
        return 0
    if dry_run:
        echo("  would write this block, leaving the rest of the file alone:")
        echo("")
        for line in merge_codex_config(
            "", server=MCP_SERVER_NAME, url=MCP_URL, client_id=client_id
        )[0].splitlines():
            echo(f"    {line}", "dim")
        return 0

    _write_config(target_file, updated)
    echo(f"  wrote      [mcp_servers.{MCP_SERVER_NAME}]")
    echo(f"  preserved  {len(original.splitlines())} existing line(s)")
    if not client_id:
        warn(
            "no --client-id given, so no OAuth client id was written. Meta's "
            "endpoint needs the App ID of an app you control."
        )
    return 0


def _write_config(path: Path, text: str) -> None:
    from meta_ads_agent.workspace import atomic_write

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, text)


# ---------------------------------------------------------------------------
# open-url
# ---------------------------------------------------------------------------
def run_open_url(url: str, *, as_json: bool = False) -> int:
    """Hand a URL to the Windows browser, never to one inside WSL."""
    bridge = WslBridge.detect()
    try:
        bridge.open_url(url)
    except MetaAdsAgentError as exc:
        if as_json:
            emit_json({"url": url, "opened": False, "error": str(exc)})
        else:
            fail(str(exc))
        return 1
    if as_json:
        emit_json({"url": url, "opened": True})
    else:
        echo(f"  opened in your Windows browser: {url}")
    return 0


# ---------------------------------------------------------------------------
# shared with doctor
# ---------------------------------------------------------------------------
def installation_report(
    *, target_kind: str = "agents", path: str | None = None, windows_home: str | None = None
) -> dict[str, Any]:
    """One structured answer to "is this installation all right".

    ``status`` is one of: ``complete``, ``update-available``,
    ``migration-required``, ``interrupted``, ``broken``, ``not-installed``.
    They need different fixes, so they are different words.
    """
    report: dict[str, Any] = {"cli_version": __version__}
    try:
        manifest = packaged.release_manifest()
    except MetaAdsAgentError as exc:
        return {**report, "status": "broken", "detail": str(exc)}
    report["release_version"] = manifest.version
    report["release_digest"] = manifest.digest

    try:
        target = resolve_target(target_kind, path=path, windows_home=windows_home)
    except MetaAdsAgentError as exc:
        return {**report, "status": "not-installed", "detail": str(exc)}
    report["target"] = target.as_dict()

    state = InstallState.load(target.root)
    report["installed_version"] = state.version
    report["installed_at"] = state.installed_at
    report["method"] = state.method

    if state.interrupted and state.in_progress:
        return {
            **report,
            "status": "interrupted",
            "detail": (
                f"an update from {state.in_progress.from_version} to "
                f"{state.in_progress.to_version} stopped during "
                f"'{state.in_progress.stage}'"
            ),
            "fix": "meta-ads-agent upgrade   (or --rollback to restore the backup)",
        }

    if state.version is None:
        return {
            **report,
            "status": "not-installed",
            "detail": f"no meta-ads skills recorded at {target.root}",
            "fix": "meta-ads-agent install",
        }

    from meta_ads_agent.install.manifest import verify_tree

    verification = verify_tree(manifest, target.root)
    report["verification"] = verification.as_dict()

    if state.version != manifest.version:
        return {
            **report,
            "status": "update-available",
            "detail": f"installed {state.version}, package ships {manifest.version}",
            "fix": "meta-ads-agent upgrade",
        }
    if not verification.complete:
        return {
            **report,
            "status": "broken",
            "detail": (
                f"{len(verification.missing)} file(s) missing, "
                f"{len(verification.modified)} modified, "
                f"{len(verification.orphaned)} left over from an earlier version"
            ),
            "fix": "meta-ads-agent install --force",
        }

    pending = _pending_migrations(manifest)
    report["pending_migrations"] = pending
    if pending:
        return {
            **report,
            "status": "migration-required",
            "detail": f"{len(pending)} workspace migration(s) not applied: {', '.join(pending)}",
            "fix": "meta-ads-agent migrate",
        }

    return {**report, "status": "complete", "detail": f"{manifest.version}, verified"}


def _pending_migrations(manifest: Any) -> list[str]:
    workspace = Workspace.locate(required=False)
    if not workspace.exists:
        return []
    try:
        ledger = MigrationLedger.load(workspace)
    except StateError:
        return ["<ledger unreadable>"]
    declared = [m.id for m in manifest.migrations]
    return [mid for mid in declared if not ledger.has(mid)]
