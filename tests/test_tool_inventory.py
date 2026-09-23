"""Comparing a live session's tool list with the capability map.

The map was read from Meta's published reference and never introspected.
`capabilities --compare` is how a person with a session closes that gap, so
it has to read the names out of whatever they paste, and report drift in
the direction that matters.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from meta_ads_agent.capabilities import load_registry
from meta_ads_agent.cli.main import main
from meta_ads_agent.tool_inventory import compare, load_inventory, tool_names

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def inventory():  # type: ignore[no-untyped-def]
    return load_inventory()


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_registry()


def session(inventory, *, drop=(), add=()) -> str:  # type: ignore[no-untyped-def]
    names = (set(inventory.documented) - set(drop)) | set(add)
    return "\n".join(f"mcp__meta-ads__{n}" for n in sorted(names))


class TestReadingPastedText:
    @pytest.mark.parametrize(
        "text",
        [
            "mcp__meta-ads__ads_get_ad_accounts",
            '["ads_get_ad_accounts"]',
            '[{"name": "ads_get_ad_accounts", "description": "..."}]',
            "- ads_get_ad_accounts: list ad accounts",
        ],
    )
    def test_names_are_found_whatever_surrounds_them(self, text: str) -> None:
        assert tool_names(text) == {"ads_get_ad_accounts"}

    def test_text_with_no_tool_names_is_refused(self, registry, inventory) -> None:  # type: ignore[no-untyped-def]
        from meta_ads_agent.errors import ValidationError

        with pytest.raises(ValidationError, match="no ads_\\* tool names"):
            compare("Meta has lots of tools", registry, inventory)


class TestDrift:
    def test_a_session_matching_the_reference_is_clean(self, registry, inventory) -> None:  # type: ignore[no-untyped-def]
        drift = compare(session(inventory), registry, inventory)
        assert drift.clean
        assert drift.unverified_absent == sorted(inventory.unverified)

    def test_a_routed_tool_going_missing_names_what_it_breaks(self, registry, inventory) -> None:  # type: ignore[no-untyped-def]
        drift = compare(session(inventory, drop={"ads_get_ad_accounts"}), registry, inventory)
        assert drift.missing == {"ads_get_ad_accounts": ["list_ad_accounts"]}
        assert not drift.clean

    def test_a_new_delete_tool_is_flagged_against_the_delete_gap(self, registry, inventory) -> None:  # type: ignore[no-untyped-def]
        drift = compare(session(inventory, add={"ads_delete_campaign"}), registry, inventory)
        assert drift.new == ["ads_delete_campaign"]
        assert drift.gap_candidates == {"delete_entity": ["ads_delete_campaign"]}

    def test_a_confirmed_community_name_is_reported_and_weighed(self, registry, inventory) -> None:  # type: ignore[no-untyped-def]
        drift = compare(session(inventory, add={"ads_creative_upload_image"}), registry, inventory)
        assert drift.unverified_confirmed == ["ads_creative_upload_image"]
        assert drift.gap_candidates == {"local_image_upload": ["ads_creative_upload_image"]}
        assert drift.new == []


class TestCommand:
    def test_exit_1_and_json_when_the_session_differs(  # type: ignore[no-untyped-def]
        self, tmp_path: Path, inventory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pasted = tmp_path / "tools.txt"
        pasted.write_text(session(inventory, drop={"ads_get_ad_accounts"}))
        assert main(["capabilities", "--compare", str(pasted), "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert "ads_get_ad_accounts" in payload["missing"]

    def test_exit_0_when_it_matches(  # type: ignore[no-untyped-def]
        self, tmp_path: Path, inventory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pasted = tmp_path / "tools.txt"
        pasted.write_text(session(inventory))
        assert main(["capabilities", "--compare", str(pasted)]) == 0
        assert "matches the map" in capsys.readouterr().out


class TestInventoryFile:
    def test_it_matches_the_research_document(self) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(REPO / "scripts" / "build_mcp_tool_inventory.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_every_tool_the_map_routes_to_is_documented(self, registry, inventory) -> None:  # type: ignore[no-untyped-def]
        routed = {t for cap in registry.capabilities.values() for t in cap.mcp_tools}
        assert routed - inventory.documented == set()

    def test_the_reference_is_about_ninety_tools(self, inventory) -> None:  # type: ignore[no-untyped-def]
        # The README says "around 90"; a parse that finds 40 has broken.
        assert 80 <= len(inventory.documented) <= 110
