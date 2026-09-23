"""``meta-ads-agent api ...`` - the Marketing API fallback commands.

Every command here fills a specific gap in Meta's official Ads MCP. None of
them duplicates something the MCP can already do, and each prints why it exists
so the architecture stays visible in the transcript rather than buried in a
design doc.

The same safety model applies as to MCP operations. This CLI is not a way
around the approval gates: destructive and spend-affecting commands support
``--dry-run``, deletion demands a stated reason, and nothing here can activate
an ad.
"""

from __future__ import annotations

import contextlib
from typing import Any

from meta_ads_agent.api.client import ACCOUNT_ENV, ApiClient, normalise_account_id
from meta_ads_agent.api.creatives import (
    create_existing_post_creative,
    create_multi_variant_creative,
    create_video_creative,
)
from meta_ads_agent.api.deletion import DeletableType, delete_object
from meta_ads_agent.api.media import upload_image, upload_video
from meta_ads_agent.capabilities import Provider, RiskLevel, load_registry
from meta_ads_agent.cli.output import echo, emit_json, fail, heading
from meta_ads_agent.errors import ApiFallbackUnavailable, ConfigError, DryRun, MetaAdsAgentError
from meta_ads_agent.models.plan import CopyVariant
from meta_ads_agent.state.actionlog import ActionLog, ActionRecord
from meta_ads_agent.state.assets import AssetStore
from meta_ads_agent.workspace import Workspace


def _client(dry_run: bool) -> ApiClient | None:
    """Build an API client, or None when a dry run can proceed without one.

    A dry run should work before any credentials exist - its whole purpose is
    to let someone see what a command would do before setting up a token.
    """
    try:
        return ApiClient()
    except ApiFallbackUnavailable:
        if dry_run:
            return None
        raise


def _target_account(account: str | None, client: ApiClient | None, dry_run: bool) -> str:
    """The ad account a command acts on, in its one canonical spelling.

    Only a dry run may proceed without one - it describes the call rather
    than making it. A real call with no account is refused here, before the
    placeholder can reach Meta as ``act_<no account configured>``.
    """
    target = account or (client.credentials.ad_account_id if client else None)
    if target:
        return normalise_account_id(target)
    if dry_run:
        return "<no account configured>"
    raise ConfigError(f"No ad account given and {ACCOUNT_ENV} is not set. Pass --account act_<id>.")


def _log_attempt(
    log: ActionLog | None, outcome: str, exc: Exception, attempt: dict[str, Any]
) -> None:
    """Record a dry run or a failure, which the log previously left out.

    A failure is when the log matters most: "did it upload, or not" is the
    first question after an error, and a timeout may have been applied by
    Meta anyway. Logging must never replace the error the user needs to see,
    so a log that cannot be written is ignored here.
    """
    if log is None:
        return
    with contextlib.suppress(OSError, MetaAdsAgentError):
        log.append(
            ActionRecord(provider=Provider.API_FALLBACK, result=outcome, detail=str(exc), **attempt)
        )


def _account_field(target: str) -> dict[str, str]:
    # The dry-run placeholder is not an account and must not be logged as one.
    return {"ad_account_id": target} if target.startswith("act_") else {}


def _context(capability: str) -> tuple[Workspace, AssetStore, ActionLog, str]:
    """Resolve workspace, stores, and the reason this fallback is being used."""
    workspace = Workspace.locate()
    registry = load_registry()
    route = registry.route(capability)
    if route.provider is not Provider.API_FALLBACK:
        raise MetaAdsAgentError(
            f"{capability} routes to {route.provider.value}, not the API "
            "fallback. Use the official MCP for it."
        )
    return workspace, AssetStore(workspace), ActionLog(workspace), route.reason


def run_upload_image(path: str, *, account: str | None, dry_run: bool, as_json: bool) -> int:
    capability = "local_image_upload"
    log: ActionLog | None = None
    attempt: dict[str, Any] = {
        "operation": "upload_image",
        "capability": capability,
        "risk_level": RiskLevel.CREATE_PAUSED,
        "resource_type": "image",
    }
    try:
        _ws, store, log, reason = _context(capability)
        client = _client(dry_run)
        target = _target_account(account, client, dry_run)
        attempt.update(_account_field(target))
        result = upload_image(path, target, client=client, store=store, dry_run=dry_run)
    except DryRun as exc:
        _log_attempt(log, "dry_run", exc, attempt)
        echo(str(exc), "yellow")
        return 0
    except MetaAdsAgentError as exc:
        _log_attempt(log, "failed", exc, attempt)
        fail(str(exc))
        return 1

    log.append(
        ActionRecord(
            operation="upload_image",
            capability=capability,
            risk_level=RiskLevel.CREATE_PAUSED,
            provider=Provider.API_FALLBACK,
            resource_type="image",
            resource_id=result.remote_id,
            ad_account_id=target,
            after={"image_hash": result.remote_id, "reused": result.reused},
            result="skipped" if result.reused else "ok",
            detail=result.detail,
        )
    )

    if as_json:
        emit_json(
            {
                "capability": capability,
                "provider": "api_fallback",
                "reason": reason,
                "image_hash": result.remote_id,
                "reused": result.reused,
                "fingerprint": result.record.fingerprint,
                "detail": result.detail,
            }
        )
        return 0

    heading("Image upload (API fallback)")
    echo(f"  reason      {reason}")
    echo(f"  image_hash  {result.remote_id}")
    echo(f"  reused      {'yes - not re-uploaded' if result.reused else 'no'}")
    echo(f"  detail      {result.detail}")
    return 0


def run_upload_video(
    path: str,
    *,
    account: str | None,
    dry_run: bool,
    as_json: bool,
    wait: bool,
    timeout: float,
) -> int:
    capability = "local_video_upload"
    log: ActionLog | None = None
    attempt: dict[str, Any] = {
        "operation": "upload_video",
        "capability": capability,
        "risk_level": RiskLevel.CREATE_PAUSED,
        "resource_type": "video",
    }
    try:
        _ws, store, log, reason = _context(capability)
        client = _client(dry_run)
        target = _target_account(account, client, dry_run)
        attempt.update(_account_field(target))
        result = upload_video(
            path,
            target,
            client=client,
            store=store,
            dry_run=dry_run,
            wait=wait,
            timeout_seconds=timeout,
        )
    except DryRun as exc:
        _log_attempt(log, "dry_run", exc, attempt)
        echo(str(exc), "yellow")
        return 0
    except MetaAdsAgentError as exc:
        _log_attempt(log, "failed", exc, attempt)
        fail(str(exc))
        return 1

    log.append(
        ActionRecord(
            operation="upload_video",
            capability=capability,
            risk_level=RiskLevel.CREATE_PAUSED,
            provider=Provider.API_FALLBACK,
            resource_type="video",
            resource_id=result.remote_id,
            ad_account_id=target,
            after={"video_id": result.remote_id, "reused": result.reused},
            result="skipped" if result.reused else "ok",
            detail=result.detail,
        )
    )

    if as_json:
        emit_json(
            {
                "capability": capability,
                "provider": "api_fallback",
                "reason": reason,
                "video_id": result.remote_id,
                "reused": result.reused,
                "fingerprint": result.record.fingerprint,
                "detail": result.detail,
            }
        )
        return 0

    heading("Video upload (API fallback)")
    echo(f"  reason      {reason}")
    echo(f"  video_id    {result.remote_id}")
    echo(f"  reused      {'yes - not re-uploaded' if result.reused else 'no'}")
    echo(f"  detail      {result.detail}")
    return 0


def run_create_creative(
    *,
    mode: str,
    name: str,
    account: str | None,
    page_id: str | None,
    video_id: str | None,
    post_id: str | None,
    image_hashes: list[str],
    destination_url: str | None,
    primary_text: str | None,
    headline: str | None,
    cta: str | None,
    instagram_account_id: str | None,
    dry_run: bool,
    as_json: bool,
) -> int:
    capability = {
        "video": "create_video_creative",
        "post": "create_existing_post_creative",
        "variants": "create_multi_variant_creative",
    }[mode]

    log: ActionLog | None = None
    attempt: dict[str, Any] = {
        "operation": f"create_creative:{mode}",
        "capability": capability,
        "risk_level": RiskLevel.CREATE_PAUSED,
        "resource_type": "creative",
    }
    try:
        _ws, _store, log, reason = _context(capability)
        client = _client(dry_run)
        target = _target_account(account, client, dry_run)
        attempt.update(_account_field(target))

        if mode == "post":
            if not post_id:
                fail("--post-id is required for an existing-post creative")
                return 2
            result = create_existing_post_creative(
                client=client,
                ad_account_id=target,
                name=name,
                post_id=post_id,
                instagram_account_id=instagram_account_id,
                dry_run=dry_run,
            )
        else:
            missing = [
                flag
                for flag, value in (
                    ("--page-id", page_id),
                    ("--url", destination_url),
                    ("--primary-text", primary_text),
                )
                if not value
            ]
            if missing:
                fail(f"missing required option(s): {', '.join(missing)}")
                return 2
            variant = CopyVariant(
                angle=headline or "unspecified",
                primary_text=primary_text or "",
                headline=headline,
                cta_type=cta,
            )
            if mode == "video":
                if not video_id:
                    fail("--video-id is required for a video creative")
                    return 2
                result = create_video_creative(
                    client=client,
                    ad_account_id=target,
                    name=name,
                    page_id=page_id or "",
                    video_id=video_id,
                    destination_url=destination_url or "",
                    variant=variant,
                    instagram_account_id=instagram_account_id,
                    dry_run=dry_run,
                )
            else:
                result = create_multi_variant_creative(
                    client=client,
                    ad_account_id=target,
                    name=name,
                    page_id=page_id or "",
                    destination_url=destination_url or "",
                    variants=[variant],
                    image_hashes=image_hashes or None,
                    video_ids=[video_id] if video_id else None,
                    instagram_account_id=instagram_account_id,
                    dry_run=dry_run,
                )
    except DryRun as exc:
        _log_attempt(log, "dry_run", exc, attempt)
        echo(str(exc), "yellow")
        return 0
    except MetaAdsAgentError as exc:
        _log_attempt(log, "failed", exc, attempt)
        fail(str(exc))
        return 1

    log.append(
        ActionRecord(
            operation=f"create_creative:{result.mode}",
            capability=capability,
            risk_level=RiskLevel.CREATE_PAUSED,
            provider=Provider.API_FALLBACK,
            resource_type="creative",
            resource_id=result.creative_id,
            ad_account_id=target,
            after={"creative_id": result.creative_id, "mode": result.mode},
            detail=result.detail,
        )
    )

    if as_json:
        emit_json(
            {
                "capability": capability,
                "provider": "api_fallback",
                "reason": reason,
                "creative_id": result.creative_id,
                "mode": result.mode,
                "detail": result.detail,
            }
        )
        return 0

    heading(f"Creative created: {result.mode} (API fallback)")
    echo(f"  reason       {reason}")
    echo(f"  creative_id  {result.creative_id}")
    echo(f"  detail       {result.detail}")
    echo("")
    echo("  A creative does not spend. Attach it to an ad (PAUSED), preview it,")
    echo("  then ask for approval before activating anything.")
    return 0


def run_delete(
    object_id: str,
    *,
    object_type: str,
    reason_text: str,
    approved: bool,
    dry_run: bool,
    as_json: bool,
) -> int:
    capability = "delete_entity"
    if not approved and not dry_run:
        fail(
            "deletion requires --approved, asserting the user explicitly "
            "approved deleting this object.\n"
            "Deleted objects lose their optimisation history permanently; "
            "paused objects keep it. Pausing is usually the right answer.\n"
            "Preview first with --dry-run."
        )
        return 2

    log: ActionLog | None = None
    attempt: dict[str, Any] = {
        "operation": "delete",
        "capability": capability,
        "risk_level": RiskLevel.DELETE,
        "resource_type": object_type,
        "resource_id": object_id,
        "approval_noted": approved,
    }
    try:
        _ws, _store, log, route_reason = _context(capability)
        client = ApiClient()
        result = delete_object(
            client=client,
            object_id=object_id,
            object_type=DeletableType(object_type),
            reason=reason_text,
            dry_run=dry_run,
        )
    except DryRun as exc:
        _log_attempt(log, "dry_run", exc, attempt)
        echo(str(exc), "yellow")
        return 0
    except MetaAdsAgentError as exc:
        _log_attempt(log, "failed", exc, attempt)
        fail(str(exc))
        return 1

    log.append(
        ActionRecord(
            operation="delete",
            capability=capability,
            risk_level=RiskLevel.DELETE,
            provider=Provider.API_FALLBACK,
            resource_type=result.object_type.value,
            resource_id=result.object_id,
            ad_account_id=result.ad_account_id,
            before={"status": result.previous_status},
            after={"deleted": True},
            detail=result.detail,
            approval_noted=True,
        )
    )

    if as_json:
        emit_json(
            {
                "capability": capability,
                "provider": "api_fallback",
                "reason": route_reason,
                "deleted": result.object_id,
                "type": result.object_type.value,
                "previous_status": result.previous_status,
                "detail": result.detail,
            }
        )
        return 0

    heading(f"Deleted {result.object_type.value} {result.object_id}")
    echo(f"  previous status  {result.previous_status or 'unknown'}")
    echo(f"  detail           {result.detail}")
    return 0
