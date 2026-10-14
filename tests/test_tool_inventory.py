"""Comparing a live session's tool list with the capability map.

The map was read from Meta's published reference and never introspected.
`capabilities --compare` is how a person with a session closes that gap, so
it has to read the names out of whatever they paste, and report drift in
the direction that matters.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from meta_ads_agent.capabilities import RiskLevel, load_registry
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


class TestUnreadableInput:
    def test_a_directory_is_an_input_error_not_a_crash(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["capabilities", "--compare", str(tmp_path)]) == 2
        assert "could not read" in capsys.readouterr().err


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


SKILLS = REPO / "skills"
_TOOL = re.compile(r"\bads_[a-z0-9_]+[a-z0-9]\b")
_CLASS = re.compile(r"`(" + "|".join(level.value for level in RiskLevel) + r")`")


def _skill_texts() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in sorted(SKILLS.rglob("*.md"))}


def _table_rows(text: str) -> list[list[str]]:
    """Markdown table rows as cell lists, separator rows dropped."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def _is_tool_list(cell: str) -> bool:
    """A cell holding only tool names, e.g. "`ads_a`, `ads_b`"."""
    rest = _TOOL.sub("", cell)
    return bool(_TOOL.search(cell)) and set(rest) <= set("`,/ ")


class TestSkillsNameEveryTool:
    """The skills are where an agent learns a tool exists and what it risks.

    A tool only the inventory knows is one the agent has to guess the name
    of; a class written next to a tool that disagrees with the capability
    map is an approval rule the agent will follow instead of the real one.
    """

    def test_every_inventoried_tool_is_named_in_a_skill(self, inventory) -> None:  # type: ignore[no-untyped-def]
        named: set[str] = set()
        for text in _skill_texts().values():
            named |= set(_TOOL.findall(text))
        missing = (set(inventory.documented) | set(inventory.unverified)) - named
        assert missing == set(), (
            f"{len(missing)} tool(s) no skill names - add them to a skill or to "
            f"skills/meta-ads-core/references/mcp-tool-map.md: {sorted(missing)}"
        )

    def test_a_class_written_beside_a_tool_matches_the_map(self, registry) -> None:  # type: ignore[no-untyped-def]
        risk = {t: str(cap.risk_level) for cap in registry.capabilities.values() for t in cap.mcp_tools}
        wrong: list[str] = []
        checked = 0
        for path, text in _skill_texts().items():
            header: list[str] | None = None
            for cells in _table_rows(text):
                classes = [_CLASS.findall(cell) for cell in cells]
                if header is None or not any(_TOOL.search(c) for c in cells):
                    # A header row: remember any column that names one class.
                    header = [c[0] if len(c) == 1 else "" for c in classes]
                    continue
                row_classes = {k for c in classes for k in c}
                for i, cell in enumerate(cells):
                    expected = (
                        next(iter(row_classes))
                        if len(row_classes) == 1
                        else (header[i] if i < len(header) else "")
                    )
                    if not expected:
                        continue
                    if not _is_tool_list(cell):
                        # Prose that mentions a tool ("check X first") is
                        # not a statement about that tool's class.
                        continue
                    for tool in _TOOL.findall(cell):
                        if tool not in risk:
                            continue
                        checked += 1
                        if risk[tool] != expected:
                            wrong.append(
                                f"{path.relative_to(REPO)}: {tool} written as {expected}, "
                                f"the map says {risk[tool]}"
                            )
        assert wrong == []
        # The pixel and catalog tables alone hold more than this; a parse
        # that checks nothing would pass vacuously.
        assert checked >= 25
