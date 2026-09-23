"""Local image and video upload - the main reason this fallback exists.

Meta's official Ads MCP lists media already on an account (``ads_get_ad_images``,
``ads_get_ad_videos``) but has no tool that ingests a local file. One community
source reports an image-upload tool that accepts URLs only, which still leaves
local files unsolved, and local files are the common case for an agent working
in someone's project directory.

Both paths are deduplicated by content fingerprint through the asset manifest:
the same bytes are uploaded once per ad account, ever. A retried campaign build
re-uses the existing remote id instead of creating a second Meta object for one
file.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meta_ads_agent.api.client import ApiClient, wrap_sdk_error
from meta_ads_agent.errors import ApiCallFailed, ApiFallbackUnavailable, DryRun
from meta_ads_agent.models.state import AssetRecord
from meta_ads_agent.state.assets import AssetKind, AssetStore, probe_asset

# Meta transcodes video asynchronously. A freshly uploaded video cannot be used
# in a creative until processing finishes, so we poll rather than hand back an
# id that will be rejected a second later.
VIDEO_POLL_INTERVAL_SECONDS = 5.0
VIDEO_POLL_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True, slots=True)
class UploadResult:
    """Outcome of an upload, including whether it actually happened."""

    record: AssetRecord
    reused: bool
    detail: str

    @property
    def remote_id(self) -> str:
        return self.record.image_hash or self.record.video_id or ""


def upload_image(
    path: Path | str,
    ad_account_id: str,
    *,
    client: ApiClient | None,
    store: AssetStore,
    dry_run: bool = False,
) -> UploadResult:
    """Upload a local image and return its Meta image hash.

    ``client`` may be None only when ``dry_run`` is set: a dry run reports what
    would happen and must work before any credentials are configured.
    """
    probe = probe_asset(path, kind=AssetKind.IMAGE)

    with store.claim(probe, ad_account_id):
        existing = store.lookup(probe, ad_account_id)
        if existing is not None and existing.image_hash:
            return UploadResult(
                record=existing,
                reused=True,
                detail=(
                    f"already uploaded to {ad_account_id} as image_hash "
                    f"{existing.image_hash} on {existing.uploaded_at:%Y-%m-%d}; "
                    "skipped re-upload"
                ),
            )

        if dry_run:
            raise _dry_run(probe.path, "image", ad_account_id)
        if client is None:
            raise ApiFallbackUnavailable("an API client is required for a real upload")

        from facebook_business.adobjects.adimage import AdImage

        account = client.account(ad_account_id)
        try:
            image = AdImage(parent_id=account.get_id_assured(), api=client.connect())
            image[AdImage.Field.filename] = str(probe.path)
            image.remote_create()
            image_hash = image[AdImage.Field.hash]
        except Exception as exc:
            raise wrap_sdk_error(exc, stage="assets_uploaded", operation="upload_image") from exc

        if not image_hash:
            raise ApiCallFailed(
                "Meta accepted the image upload but returned no hash, so the result "
                "cannot be used in a creative. Check ads_get_ad_images before retrying "
                "- the image may already exist.",
                stage="assets_uploaded",
                retry_safe=False,
            )

        record = store.remember(probe, ad_account_id, image_hash=str(image_hash))
    return UploadResult(
        record=record,
        reused=False,
        detail=f"uploaded {probe.path.name} as image_hash {image_hash}",
    )


def upload_video(
    path: Path | str,
    ad_account_id: str,
    *,
    client: ApiClient | None,
    store: AssetStore,
    dry_run: bool = False,
    wait: bool = True,
    timeout_seconds: float = VIDEO_POLL_TIMEOUT_SECONDS,
    sleep: Any = time.sleep,
) -> UploadResult:
    """Upload a local video, wait for Meta to finish processing, return its id.

    The SDK performs the chunked upload. ``wait=False`` returns as soon as the
    id exists, which is only useful if the caller will poll separately - a
    creative built against an unprocessed video is rejected.
    """
    probe = probe_asset(path, kind=AssetKind.VIDEO)

    with store.claim(probe, ad_account_id):
        existing = store.lookup(probe, ad_account_id)
        if existing is not None and existing.video_id:
            return UploadResult(
                record=existing,
                reused=True,
                detail=(
                    f"already uploaded to {ad_account_id} as video_id "
                    f"{existing.video_id} on {existing.uploaded_at:%Y-%m-%d}; "
                    "skipped re-upload"
                ),
            )

        if dry_run:
            raise _dry_run(probe.path, "video", ad_account_id)
        if client is None:
            raise ApiFallbackUnavailable("an API client is required for a real upload")

        from facebook_business.adobjects.advideo import AdVideo

        account = client.account(ad_account_id)
        try:
            video = AdVideo(parent_id=account.get_id_assured(), api=client.connect())
            video[AdVideo.Field.filepath] = str(probe.path)
            video.remote_create()
            video_id = video.get_id()
        except Exception as exc:
            raise wrap_sdk_error(exc, stage="assets_uploaded", operation="upload_video") from exc

        if not video_id:
            raise ApiCallFailed(
                "Meta accepted the video upload but returned no id. Check "
                "ads_get_ad_videos before retrying - a partial upload may have "
                "created a video object already.",
                stage="assets_uploaded",
                retry_safe=False,
            )

        # Persist the id before waiting. If processing times out or the process is
        # killed, the upload must not be repeated - the bytes are already on Meta.
        record = store.remember(probe, ad_account_id, video_id=str(video_id))

    status = "not checked"
    if wait:
        status = wait_for_video_processing(
            str(video_id),
            client=client,
            timeout_seconds=timeout_seconds,
            sleep=sleep,
        )

    return UploadResult(
        record=record,
        reused=False,
        detail=f"uploaded {probe.path.name} as video_id {video_id} (processing: {status})",
    )


def wait_for_video_processing(
    video_id: str,
    *,
    client: ApiClient,
    timeout_seconds: float = VIDEO_POLL_TIMEOUT_SECONDS,
    interval_seconds: float = VIDEO_POLL_INTERVAL_SECONDS,
    sleep: Any = time.sleep,
    now: Any = time.monotonic,
) -> str:
    """Poll until Meta finishes transcoding *video_id*.

    Returns the terminal status. Raises on a reported error or on timeout -
    both mean the video is not usable in a creative yet, and silently
    continuing would produce a confusing rejection at ad-creation time.
    """
    from facebook_business.adobjects.advideo import AdVideo

    deadline = now() + timeout_seconds
    last = "unknown"
    while True:
        try:
            fetched = AdVideo(video_id, api=client.connect()).api_get(fields=["status"])
            status_field = (fetched or {}).get("status") or {}
            last = str(status_field.get("video_status") or status_field.get("status") or "unknown")
        except Exception as exc:
            raise wrap_sdk_error(
                exc, stage="assets_uploaded", operation="get_video_status"
            ) from exc

        normalised = last.lower()
        if normalised == "ready":
            return last
        if normalised in {"error", "failed"}:
            raise ApiCallFailed(
                f"Meta reported video {video_id} as {last}. It was uploaded but "
                "cannot be used. Re-encode the file and upload it again - the "
                "fingerprint will differ, so the manifest will not block it.",
                stage="assets_uploaded",
                retry_safe=False,
            )
        if now() >= deadline:
            raise ApiCallFailed(
                f"video {video_id} was still {last} after "
                f"{timeout_seconds:.0f}s. The upload succeeded and the id is "
                "saved in the asset manifest; check it again later rather than "
                "re-uploading.",
                stage="assets_uploaded",
                retry_safe=True,
            )
        sleep(interval_seconds)


def _dry_run(path: Path, kind: str, ad_account_id: str) -> DryRun:
    return DryRun(
        f"DRY RUN: would upload {kind} {path.name} ({path}) to {ad_account_id}. "
        "It is not in the asset manifest, so this would be a real upload. "
        "Re-run without --dry-run to perform it."
    )
