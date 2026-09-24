"""Checks on creatives: identities, destinations, routing, and local assets."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from meta_ads_agent.capabilities import Registry
from meta_ads_agent.errors import CapabilityError
from meta_ads_agent.models._common import looks_like_video
from meta_ads_agent.models.plan import CampaignPlanDocument, CreativeMode, CreativePlan
from meta_ads_agent.naming import has_placeholders
from meta_ads_agent.state.assets import AssetKind, probe_asset
from meta_ads_agent.validation.account import AccountContext
from meta_ads_agent.validation.report import Severity, ValidationReport

# Creative modes that need the API fallback. Derived from the capability
# registry at validation time, but mapped here because the plan speaks in modes
# and the registry speaks in capabilities.
_MODE_CAPABILITY: dict[CreativeMode, str] = {
    CreativeMode.SINGLE_IMAGE: "create_single_image_creative",
    CreativeMode.SINGLE_VIDEO: "create_video_creative",
    CreativeMode.EXISTING_POST: "create_existing_post_creative",
    CreativeMode.MULTI_VARIANT: "create_multi_variant_creative",
    CreativeMode.CAROUSEL: "create_carousel_creative",
}


def check_creative(
    creative: CreativePlan, path: str, account: AccountContext | None, report: ValidationReport
) -> None:
    if not creative.page_id:
        report.add(
            Severity.ERROR,
            "creative.page_missing",
            "every ad needs a Facebook Page identity and none is set here or "
            "resolvable from brand config",
            f"{path}.page_id",
        )
    elif (
        account
        and account.available_page_ids
        and creative.page_id not in account.available_page_ids
    ):
        report.add(
            Severity.ERROR,
            "creative.page_unknown",
            f"Page {creative.page_id} is not among the Pages available to this account",
            f"{path}.page_id",
        )

    if (
        creative.instagram_account_id
        and account
        and account.available_instagram_account_ids
        and creative.instagram_account_id not in account.available_instagram_account_ids
    ):
        report.add(
            Severity.ERROR,
            "creative.instagram_unknown",
            f"Instagram account {creative.instagram_account_id} is not linked to this ad account",
            f"{path}.instagram_account_id",
        )

    if creative.destination_url:
        check_destination(creative.destination_url, f"{path}.destination_url", report)
    for card_index, card in enumerate(creative.cards):
        if card.link:
            check_destination(card.link, f"{path}.cards[{card_index}].link", report)

    if (
        account
        and account.valid_call_to_action_types
        and (cta_types := [v.cta_type for v in creative.variants if v.cta_type])
    ):
        invalid = sorted({c for c in cta_types if c not in account.valid_call_to_action_types})
        if invalid:
            report.add(
                Severity.ERROR,
                "creative.cta_invalid",
                f"call-to-action type(s) {invalid} are not valid for this "
                "objective according to the discovered field metadata",
                f"{path}.variants",
            )

    angles = [v.angle.strip().lower() for v in creative.variants]
    if len(angles) > 1 and len(set(angles)) == 1:
        report.add(
            Severity.WARNING,
            "creative.angles_not_distinct",
            f"all {len(angles)} variants share the angle {angles[0]!r}. Wording "
            "changes on one idea are one test, not several - label them honestly "
            "or give them genuinely different angles.",
            f"{path}.variants",
        )

    if creative.advantage.enhancements:
        enabled = sorted(k for k, v in creative.advantage.enhancements.items() if v)
        disabled = sorted(k for k, v in creative.advantage.enhancements.items() if not v)
        report.add(
            Severity.INFO,
            "creative.advantage_declared",
            "Meta automatic enhancements - enabled: "
            f"{enabled or 'none'}; disabled: {disabled or 'none'}. Anything not "
            "listed follows Meta's default and may alter the creative.",
            f"{path}.advantage",
        )
    else:
        report.add(
            Severity.INFO,
            "creative.advantage_default",
            "no automatic-enhancement preferences declared, so Meta's defaults "
            "apply and the delivered creative may differ from the preview. "
            "Declare them in brand config to make this explicit.",
            f"{path}.advantage",
        )


def check_destination(url: str, path: str, report: ValidationReport) -> None:
    parts = urlsplit(url)
    if parts.scheme == "http":
        report.add(
            Severity.WARNING,
            "destination.not_https",
            f"{url} is plain http. Expect browser warnings and worse conversion "
            "rates; Meta may also restrict it.",
            path,
        )
    if parts.hostname and parts.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        report.add(
            Severity.ERROR,
            "destination.not_public",
            f"{url} points at localhost, which no ad viewer can reach",
            path,
        )
    if parts.hostname and "." not in parts.hostname:
        report.add(
            Severity.ERROR,
            "destination.no_public_host",
            f"{url} has no public hostname",
            path,
        )
    if any(token in url for token in ("{{", "}}", "<", ">")) or has_placeholders(url):
        report.add(
            Severity.ERROR,
            "destination.unresolved_template",
            f"{url} still contains template placeholders. Run "
            "`meta-ads-agent render-plan --write` to expand brand templates.",
            path,
        )


def check_creative_routing(
    doc: CampaignPlanDocument, registry: Registry, report: ValidationReport
) -> None:
    """Resolve each creative mode to a provider, and say so.

    Recording the provider is what lets the agent explain, truthfully, that a
    step used the fallback because Meta's MCP does not expose the capability.
    """
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        for ad_index, ad in enumerate(ad_set.ads):
            path = f"campaign.ad_sets[{index}].ads[{ad_index}].creative"
            capability = _MODE_CAPABILITY[ad.creative.mode]
            try:
                route = registry.route(capability)
            except CapabilityError as exc:
                report.add(
                    Severity.ERROR,
                    "creative.mode_unsupported",
                    str(exc),
                    f"{path}.mode",
                )
                continue
            report.providers_used[capability] = route.provider.value
            if route.uses_fallback:
                report.add(
                    Severity.INFO,
                    "routing.fallback",
                    f"creative mode {ad.creative.mode.value} will use the Meta "
                    f"Business SDK fallback ({route.cli}) because Meta's "
                    "official Ads MCP does not currently expose it.",
                    path,
                )

    local_paths = [
        asset.local_path
        for ad_set in doc.campaign.ad_sets
        for ad in ad_set.ads
        for _, asset in ad.creative.asset_refs()
        if asset.local_path
    ]
    if local_paths:
        # Route only the kinds actually present, so the report does not claim a
        # video upload will happen for an image-only plan.
        needed = set()
        for local_path in local_paths:
            needed.add(
                "local_video_upload" if looks_like_video(local_path) else "local_image_upload"
            )
        for capability in sorted(needed):
            route = registry.route(capability)
            report.providers_used[capability] = route.provider.value
        report.add(
            Severity.INFO,
            "routing.local_upload",
            "the plan references local files, so upload runs through the Meta "
            "Business SDK fallback - Meta's official Ads MCP lists uploaded "
            "media but has no local-file ingestion tool. Uploads are "
            "deduplicated by content fingerprint.",
        )


def check_local_assets(
    doc: CampaignPlanDocument, asset_base: Path | str | None, report: ValidationReport
) -> None:
    base = Path(asset_base) if asset_base else Path.cwd()
    for index, ad_set in enumerate(doc.campaign.ad_sets):
        for ad_index, ad in enumerate(ad_set.ads):
            creative = ad.creative
            for where, asset in creative.asset_refs():
                path = f"campaign.ad_sets[{index}].ads[{ad_index}].creative.{where}"
                if not asset.local_path:
                    continue
                expected = AssetKind.VIDEO if creative.mode is CreativeMode.SINGLE_VIDEO else None
                resolved = Path(asset.local_path).expanduser()
                if not resolved.is_absolute():
                    resolved = base / resolved
                try:
                    probe = probe_asset(resolved, kind=expected)
                except Exception as exc:
                    report.add(Severity.ERROR, "asset.unusable", str(exc), path)
                    continue
                report.add(
                    Severity.INFO,
                    "asset.ok",
                    f"{probe.kind.value} {resolved.name}: {probe.size_bytes} bytes"
                    + (f", {probe.width}x{probe.height}" if probe.width else "")
                    + (f", {probe.duration_seconds:.1f}s" if probe.duration_seconds else "")
                    + f", {probe.fingerprint[:19]}...",
                    path,
                )
                for warning in probe.warnings:
                    report.add(Severity.WARNING, "asset.warning", warning, path)
