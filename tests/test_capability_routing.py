"""Capability routing and approval-risk classification.

Two behaviours matter most: the fallback must never take over work the MCP
owns, and a YAML typo must not be able to downgrade an approval requirement.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from meta_ads_agent.capabilities import (
    APPROVAL_REQUIRED,
    Provider,
    RiskLevel,
    load_registry,
    risk_rank,
)
from meta_ads_agent.errors import CapabilityError, ConfigError

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "capabilities.yaml"


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_registry(REGISTRY_PATH)


class TestShippedRegistry:
    def test_parses(self, registry) -> None:  # type: ignore[no-untyped-def]
        assert registry.version >= 1
        assert registry.capabilities
        assert registry.mcp_endpoint == "https://mcp.facebook.com/ads"

    def test_graph_version_matches_the_code_default(self, registry) -> None:  # type: ignore[no-untyped-def]
        from meta_ads_agent.api.version import DEFAULT_GRAPH_API_VERSION

        assert registry.graph_api_version == DEFAULT_GRAPH_API_VERSION

    def test_every_fallback_capability_names_a_command(self, registry) -> None:  # type: ignore[no-untyped-def]
        for cap in registry.gaps():
            assert cap.cli, f"{cap.name} routes to the fallback but names no command"

    def test_every_mcp_capability_names_tool_hints(self, registry) -> None:  # type: ignore[no-untyped-def]
        for cap in registry.capabilities.values():
            if cap.preferred_provider is Provider.OFFICIAL_MCP:
                assert cap.mcp_tools, f"{cap.name} claims MCP coverage but names no tool"

    def test_every_unsupported_capability_explains_itself(self, registry) -> None:  # type: ignore[no-untyped-def]
        for cap in registry.unsupported():
            assert cap.notes.strip(), f"{cap.name} is unsupported with no explanation"

    def test_registry_is_freshly_reviewed(self, registry) -> None:  # type: ignore[no-untyped-def]
        # Not a clock test: this asserts the shipped file carries review dates
        # at all, which is what makes staleness detectable.
        for cap in registry.capabilities.values():
            assert cap.last_reviewed is not None, f"{cap.name} has no last_reviewed"


class TestRouting:
    def test_mcp_capability_routes_to_mcp(self, registry) -> None:  # type: ignore[no-untyped-def]
        route = registry.route("create_campaign")
        assert route.provider is Provider.OFFICIAL_MCP
        assert not route.uses_fallback
        assert "ads_create_campaign" in route.mcp_tools

    def test_gap_capability_routes_to_fallback_and_explains_why(self, registry) -> None:  # type: ignore[no-untyped-def]
        route = registry.route("local_video_upload")
        assert route.provider is Provider.API_FALLBACK
        assert route.uses_fallback
        assert "does not currently expose" in route.reason
        assert route.cli == "meta-ads-agent api upload-video"

    def test_fallback_does_not_take_over_mcp_work_when_mcp_is_absent(self, registry) -> None:  # type: ignore[no-untyped-def]
        # Rerouting here would turn a setup problem into a credential request.
        with pytest.raises(CapabilityError, match="not connected"):
            registry.route("create_campaign", mcp_available=False)

    def test_fallback_still_works_without_the_mcp(self, registry) -> None:  # type: ignore[no-untyped-def]
        route = registry.route("local_image_upload", mcp_available=False)
        assert route.provider is Provider.API_FALLBACK

    def test_unsupported_capability_raises_with_its_note(self, registry) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(CapabilityError, match="not supported"):
            registry.route("create_carousel_creative")

    def test_unknown_capability_lists_the_known_ones(self, registry) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(CapabilityError, match="Unknown capability"):
            registry.route("make_me_money")

    def test_the_known_gaps_are_the_documented_ones(self, registry) -> None:  # type: ignore[no-untyped-def]
        # If this list grows, ADR-002 requires a stated reason. If it shrinks,
        # something good happened and the test should be updated deliberately.
        assert {c.name for c in registry.gaps()} == {
            "local_image_upload",
            "local_video_upload",
            "create_video_creative",
            "create_existing_post_creative",
            "create_multi_variant_creative",
            "delete_entity",
        }


class TestApprovalClassification:
    @pytest.mark.parametrize(
        ("capability", "expected"),
        [
            ("list_ad_accounts", False),
            ("read_campaign_structure", False),
            ("create_campaign", False),
            ("create_ad_set", False),
            ("update_entity_inactive", False),
            ("update_entity_active", True),
            ("change_budget", True),
            ("activate_entity", True),
            ("delete_entity", True),
            ("upload_customer_list", True),
            ("delete_custom_audience", True),
        ],
    )
    def test_approval_requirements(self, registry, capability: str, expected: bool) -> None:  # type: ignore[no-untyped-def]
        assert registry.route(capability).requires_approval is expected

    def test_risk_class_wins_over_a_yaml_typo(self, registry) -> None:  # type: ignore[no-untyped-def]
        """A registry entry cannot opt out of an approval its class demands."""
        cap = registry.get("activate_entity")
        object.__setattr__(cap, "requires_confirmation_declared", False)
        assert cap.risk_level in APPROVAL_REQUIRED
        assert cap.requires_approval is True

    def test_an_entry_may_opt_in_to_stricter_approval(self, registry) -> None:  # type: ignore[no-untyped-def]
        cap = registry.get("create_campaign")
        object.__setattr__(cap, "requires_confirmation_declared", True)
        assert cap.requires_approval is True
        object.__setattr__(cap, "requires_confirmation_declared", False)

    def test_spending_classes_all_require_approval(self) -> None:
        for level in (
            RiskLevel.UPDATE_ACTIVE,
            RiskLevel.BUDGET_INCREASE,
            RiskLevel.ACTIVATE,
            RiskLevel.DELETE,
            RiskLevel.BULK,
            RiskLevel.PII_UPLOAD,
        ):
            assert level in APPROVAL_REQUIRED

    def test_read_and_create_paused_do_not(self) -> None:
        assert RiskLevel.READ not in APPROVAL_REQUIRED
        assert RiskLevel.CREATE_PAUSED not in APPROVAL_REQUIRED

    def test_risk_ordering_is_by_consequence(self) -> None:
        assert risk_rank(RiskLevel.READ) < risk_rank(RiskLevel.CREATE_PAUSED)
        assert risk_rank(RiskLevel.CREATE_PAUSED) < risk_rank(RiskLevel.ACTIVATE)
        assert risk_rank(RiskLevel.ACTIVATE) < risk_rank(RiskLevel.DELETE)
        assert risk_rank(RiskLevel.DELETE) < risk_rank(RiskLevel.PII_UPLOAD)

    def test_pii_upload_is_the_highest_risk(self, registry) -> None:  # type: ignore[no-untyped-def]
        ranks = {cap.name: risk_rank(cap.risk_level) for cap in registry.capabilities.values()}
        assert ranks["upload_customer_list"] == max(ranks.values())


class TestStaleness:
    def test_entries_go_stale(self, registry) -> None:  # type: ignore[no-untyped-def]
        far_future = dt.date(2030, 1, 1)
        assert registry.stale(older_than_days=90, today=far_future)

    def test_nothing_is_stale_on_the_review_date(self, registry) -> None:  # type: ignore[no-untyped-def]
        assert registry.stale(older_than_days=90, today=registry.reviewed) == []


class TestMalformedRegistry:
    def test_bad_provider_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.yaml"
        path.write_text(
            "version: 1\ncapabilities:\n"
            "  - name: x\n    preferred_provider: telepathy\n    risk_level: read\n"
        )
        with pytest.raises(ConfigError, match="preferred_provider"):
            load_registry(path)

    def test_bad_risk_level_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.yaml"
        path.write_text(
            "version: 1\ncapabilities:\n"
            "  - name: x\n    preferred_provider: official_mcp\n    risk_level: vibes\n"
        )
        with pytest.raises(ConfigError, match="risk_level"):
            load_registry(path)

    def test_duplicate_capability_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.yaml"
        path.write_text(
            "version: 1\ncapabilities:\n"
            "  - name: x\n    preferred_provider: official_mcp\n    risk_level: read\n"
            "  - name: x\n    preferred_provider: api_fallback\n    risk_level: delete\n"
        )
        with pytest.raises(ConfigError, match="Duplicate"):
            load_registry(path)

    def test_missing_file_is_reported_clearly(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_registry(tmp_path / "absent.yaml")
