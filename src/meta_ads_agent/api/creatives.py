"""Creative shapes Meta's official MCP does not expose.

``ads_create_creative`` is documented as single-image link creatives. Three
shapes therefore need the SDK:

* **video** - needs ``video_data`` and a thumbnail
* **existing Facebook Page post** - ``ads_boost_ig_post`` covers Instagram only
* **multiple copy variants / placement-specific assets** - needs
  ``asset_feed_spec``

Use the MCP for single-image creatives. If a call here would duplicate what the
MCP already does, that is a bug, not a shortcut.

Everything built here is inert: a creative does not spend money until an ad
references it and that ad is activated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meta_ads_agent.api.client import ApiClient, wrap_sdk_error
from meta_ads_agent.errors import (
    ApiCallFailed,
    ApiFallbackUnavailable,
    DryRun,
    ValidationError,
)
from meta_ads_agent.models.plan import CopyVariant


@dataclass(frozen=True, slots=True)
class CreativeResult:
    creative_id: str
    mode: str
    detail: str


def create_video_creative(
    *,
    client: ApiClient | None,
    ad_account_id: str,
    name: str,
    page_id: str,
    video_id: str,
    destination_url: str,
    variant: CopyVariant,
    thumbnail_url: str | None = None,
    thumbnail_hash: str | None = None,
    instagram_account_id: str | None = None,
    dry_run: bool = False,
) -> CreativeResult:
    """Create a single-video link creative.

    Meta requires a thumbnail. If neither a URL nor a hash is supplied we ask
    Meta for one of the frames it generated during transcoding, rather than
    silently shipping a creative with no visible still.
    """
    if dry_run:
        raise DryRun(
            f"DRY RUN: would create a video creative {name!r} on {ad_account_id} "
            f"from video {video_id}, Page {page_id}, linking to "
            f"{destination_url}. Nothing would spend - a creative is inert until "
            "an ad using it is activated."
        )

    if client is None:
        raise ApiFallbackUnavailable("an API client is required to create a creative")

    resolved_thumbnail = thumbnail_url
    if not resolved_thumbnail and not thumbnail_hash:
        resolved_thumbnail = _pick_video_thumbnail(client, video_id)

    video_data: dict[str, Any] = {
        "video_id": video_id,
        "message": variant.primary_text,
        "call_to_action": {
            "type": variant.cta_type or "LEARN_MORE",
            "value": {"link": destination_url},
        },
    }
    if variant.headline:
        video_data["title"] = variant.headline
    if variant.description:
        video_data["link_description"] = variant.description
    if thumbnail_hash:
        video_data["image_hash"] = thumbnail_hash
    elif resolved_thumbnail:
        video_data["image_url"] = resolved_thumbnail

    object_story_spec: dict[str, Any] = {"page_id": page_id, "video_data": video_data}
    if instagram_account_id:
        object_story_spec["instagram_user_id"] = instagram_account_id

    creative_id = _create(
        client,
        ad_account_id,
        {"name": name, "object_story_spec": object_story_spec},
        operation="create_video_creative",
    )
    return CreativeResult(
        creative_id=creative_id,
        mode="single_video",
        detail=(
            f"created video creative {creative_id} from video {video_id}. Used "
            "the Business SDK fallback because Meta's official Ads MCP creates "
            "single-image link creatives only."
        ),
    )


def create_existing_post_creative(
    *,
    client: ApiClient | None,
    ad_account_id: str,
    name: str,
    post_id: str,
    instagram_account_id: str | None = None,
    dry_run: bool = False,
) -> CreativeResult:
    """Promote an existing published post, preserving its engagement.

    ``object_story_id`` references the real post, so its existing likes,
    comments, and shares carry into the ad. Rebuilding the same content as a
    new dark post would start from zero, which is usually the opposite of what
    someone asking to "promote this post" wants.
    """
    if dry_run:
        raise DryRun(
            f"DRY RUN: would create a creative {name!r} on {ad_account_id} "
            f"promoting existing post {post_id}. The post itself is not "
            "modified and its engagement is preserved."
        )

    params: dict[str, Any] = {"name": name, "object_story_id": post_id}
    if instagram_account_id:
        params["instagram_user_id"] = instagram_account_id

    creative_id = _create(client, ad_account_id, params, operation="create_existing_post_creative")
    return CreativeResult(
        creative_id=creative_id,
        mode="existing_post",
        detail=(
            f"created creative {creative_id} promoting post {post_id}, engagement "
            "preserved. Used the Business SDK fallback because Meta's official "
            "Ads MCP boosts Instagram posts only (ads_boost_ig_post)."
        ),
    )


def create_multi_variant_creative(
    *,
    client: ApiClient | None,
    ad_account_id: str,
    name: str,
    page_id: str,
    destination_url: str,
    variants: list[CopyVariant],
    image_hashes: list[str] | None = None,
    video_ids: list[str] | None = None,
    instagram_account_id: str | None = None,
    dry_run: bool = False,
) -> CreativeResult:
    """Create a creative with several copy variants via ``asset_feed_spec``.

    Meta picks among the variants per impression, which makes this a delivery
    optimisation rather than a clean test - the skill says so, because reading
    per-variant results out of it is not straightforward.
    """
    if not variants:
        raise ValidationError("a multi-variant creative needs at least one copy variant")
    if not image_hashes and not video_ids:
        raise ValidationError("a multi-variant creative needs at least one image or video")

    if dry_run:
        raise DryRun(
            f"DRY RUN: would create a multi-variant creative {name!r} on "
            f"{ad_account_id} with {len(variants)} copy variant(s), "
            f"{len(image_hashes or [])} image(s), {len(video_ids or [])} video(s)."
        )

    asset_feed_spec: dict[str, Any] = {
        "bodies": [{"text": v.primary_text} for v in variants],
        "link_urls": [{"website_url": destination_url}],
        "ad_formats": ["SINGLE_VIDEO"] if video_ids else ["SINGLE_IMAGE"],
    }
    titles = [{"text": v.headline} for v in variants if v.headline]
    if titles:
        asset_feed_spec["titles"] = titles
    descriptions = [{"text": v.description} for v in variants if v.description]
    if descriptions:
        asset_feed_spec["descriptions"] = descriptions
    ctas = sorted({v.cta_type for v in variants if v.cta_type})
    if ctas:
        asset_feed_spec["call_to_action_types"] = ctas
    if image_hashes:
        asset_feed_spec["images"] = [{"hash": h} for h in image_hashes]
    if video_ids:
        asset_feed_spec["videos"] = [{"video_id": v} for v in video_ids]

    object_story_spec: dict[str, Any] = {"page_id": page_id}
    if instagram_account_id:
        object_story_spec["instagram_user_id"] = instagram_account_id

    creative_id = _create(
        client,
        ad_account_id,
        {
            "name": name,
            "object_story_spec": object_story_spec,
            "asset_feed_spec": asset_feed_spec,
        },
        operation="create_multi_variant_creative",
    )
    return CreativeResult(
        creative_id=creative_id,
        mode="multi_variant",
        detail=(
            f"created multi-variant creative {creative_id} with "
            f"{len(variants)} copy variant(s). Used the Business SDK fallback "
            "because Meta's official Ads MCP does not expose asset_feed_spec."
        ),
    )


def _create(
    client: ApiClient | None, ad_account_id: str, params: dict[str, Any], *, operation: str
) -> str:
    if client is None:
        raise ApiFallbackUnavailable("an API client is required to create a creative")
    account = client.account(ad_account_id)
    try:
        created = account.create_ad_creative(params=params)
    except Exception as exc:
        raise wrap_sdk_error(exc, stage="creatives_created", operation=operation) from exc

    creative_id = created.get_id() if hasattr(created, "get_id") else None
    if not creative_id:
        raise ApiCallFailed(
            f"{operation} returned no creative id. Check ads_get_creatives before "
            "retrying - the creative may already exist.",
            stage="creatives_created",
            retry_safe=False,
        )
    return str(creative_id)


def _pick_video_thumbnail(client: ApiClient, video_id: str) -> str | None:
    """Ask Meta for a generated thumbnail for *video_id*.

    Returns None when none is available yet, in which case the caller may still
    proceed - Meta will usually choose one - but the creative may look
    different from expectation, which the preview step will reveal.
    """
    from facebook_business.adobjects.advideo import AdVideo

    try:
        thumbnails = AdVideo(video_id, api=client.connect()).get_thumbnails(
            fields=["uri", "is_preferred"]
        )
        candidates = list(thumbnails)
    except Exception:
        return None
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.get("is_preferred"):
            return str(candidate.get("uri")) or None
    return str(candidates[0].get("uri")) or None
