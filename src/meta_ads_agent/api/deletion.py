"""Deletion - the capability of last resort.

Meta's official MCP has no delete tool for campaigns, ad sets, or ads, so this
is a genuine gap. It is also a gap that should usually stay unfilled in
practice: **deleted objects lose their optimisation history permanently, while
paused objects keep it.** Pausing is nearly always the better answer, and the
skill is required to say why pausing is insufficient before coming here.

This module therefore does three things beyond calling the API: it insists on
an explicit reason, it refuses to guess what to delete, and it supports
``--dry-run``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from meta_ads_agent.api.client import ApiClient, normalise_account_id, wrap_sdk_error
from meta_ads_agent.errors import ApiFallbackUnavailable, DryRun, ValidationError


class DeletableType(StrEnum):
    CAMPAIGN = "campaign"
    AD_SET = "ad_set"
    AD = "ad"


@dataclass(frozen=True, slots=True)
class DeleteResult:
    object_id: str
    object_type: DeletableType
    previous_status: str | None
    detail: str
    ad_account_id: str | None = None


def delete_object(
    *,
    client: ApiClient | None,
    object_id: str,
    object_type: DeletableType,
    reason: str,
    dry_run: bool = False,
) -> DeleteResult:
    """Delete one campaign, ad set, or ad.

    Reads the object first so the result records what was destroyed. If the
    object is ACTIVE this refuses outright: deleting something that is
    currently spending removes both the spend and the evidence of it, and
    pausing first costs one extra call.
    """
    if not reason.strip():
        raise ValidationError(
            "deletion requires a stated reason why pausing is insufficient. "
            "Deleted objects lose their optimisation history permanently; "
            "paused objects keep it."
        )

    if client is None:
        # A dry run still needs to read the object, so that the preview reports
        # the real name and status rather than a guess.
        raise ApiFallbackUnavailable(
            "reading the object before deletion requires credentials, even for "
            "--dry-run: a preview that cannot name what it would delete is not "
            "a useful preview."
        )

    obj = _object_for(client, object_id, object_type)

    previous_status: str | None = None
    previous_name: str | None = None
    account_id: str | None = None
    try:
        fetched = obj.api_get(fields=["name", "status", "effective_status", "account_id"])
        previous_status = str((fetched or {}).get("status") or "") or None
        previous_name = str((fetched or {}).get("name") or "") or None
        # Read so the action log can say which account lost the object.
        account_id = str((fetched or {}).get("account_id") or "") or None
    except Exception as exc:
        raise wrap_sdk_error(
            exc, stage="delete", operation=f"read_{object_type.value}_before_delete"
        ) from exc

    if previous_status and previous_status.upper() == "ACTIVE":
        raise ValidationError(
            f"{object_type.value} {object_id} ({previous_name or 'unnamed'}) is "
            "ACTIVE. Pause it first and confirm delivery has stopped. Deleting a "
            "live object destroys the object and its history at once."
        )

    if dry_run:
        raise DryRun(
            f"DRY RUN: would delete {object_type.value} {object_id} "
            f"({previous_name or 'unnamed'}, status {previous_status or 'unknown'}).\n"
            f"Reason given: {reason.strip()}\n"
            "This is irreversible and loses the object's optimisation history. "
            "Re-run without --dry-run only if pausing genuinely will not do."
        )

    try:
        obj.api_delete()
    except Exception as exc:
        raise wrap_sdk_error(exc, stage="delete", operation=f"delete_{object_type.value}") from exc

    return DeleteResult(
        object_id=object_id,
        object_type=object_type,
        previous_status=previous_status,
        ad_account_id=normalise_account_id(account_id) if account_id else None,
        detail=(
            f"deleted {object_type.value} {object_id} "
            f"({previous_name or 'unnamed'}), previously {previous_status or 'unknown'}. "
            f"Reason: {reason.strip()}. Used the Business SDK fallback because "
            "Meta's official Ads MCP has no delete tool."
        ),
    )


def _object_for(client: ApiClient, object_id: str, object_type: DeletableType) -> Any:
    api = client.connect()
    if object_type is DeletableType.CAMPAIGN:
        from facebook_business.adobjects.campaign import Campaign

        return Campaign(object_id, api=api)
    if object_type is DeletableType.AD_SET:
        from facebook_business.adobjects.adset import AdSet

        return AdSet(object_id, api=api)
    from facebook_business.adobjects.ad import Ad

    return Ad(object_id, api=api)
