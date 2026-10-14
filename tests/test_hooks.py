"""The Claude Code approval hook (ADR-011).

Every test runs the hook the way Claude Code does - a separate `python -I`
process, the call as JSON on stdin, the answer on stdout - because the
interesting failures are in that boundary: an import the stdlib lacks, a
crash that prints nothing, output Claude Code cannot parse.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "approval_gate.py"
SERVER = "mcp__meta-ads__"
# The hook runs on whatever python3 the user has - macOS ships 3.9 - so CI
# also runs this file with META_ADS_HOOK_PYTHON pointing at Python 3.8.
PYTHON = os.environ.get("META_ADS_HOOK_PYTHON") or sys.executable


def run_hook(
    tool: str, tool_input: Any = None, *, raw: str | None = None, env: dict[str, str] | None = None
) -> dict[str, Any] | None:
    payload = (
        raw
        if raw is not None
        else json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool if tool.startswith("mcp__") else SERVER + tool,
                "tool_input": tool_input or {},
            }
        )
    )
    result = subprocess.run(  # noqa: S603
        [PYTHON, "-I", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout) if result.stdout else None


def decision(answer: dict[str, Any] | None) -> str | None:
    if answer is None:
        return None
    out = answer["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecisionReason"].startswith("meta-ads-agent: ")
    return str(out["permissionDecision"])


def reason(answer: dict[str, Any] | None) -> str:
    assert answer is not None
    return str(answer["hookSpecificOutput"]["permissionDecisionReason"])


class TestReadsAndPausedWork:
    @pytest.mark.parametrize(
        "tool",
        ["ads_get_ad_accounts", "ads_get_ad_entities", "ads_get_ad_images", "ads_library_search"],
    )
    def test_reads_are_left_to_the_users_settings(self, tool: str) -> None:
        assert run_hook(tool) is None

    def test_a_paused_campaign_is_left_alone(self) -> None:
        assert run_hook("ads_create_campaign", {"name": "x", "status": "PAUSED"}) is None

    def test_a_create_without_a_status_is_left_alone(self) -> None:
        # Meta's MCP documents its creates as PAUSED.
        assert run_hook("ads_create_ad_set", {"name": "x"}) is None

    def test_a_creative_is_not_delivery(self) -> None:
        assert run_hook("ads_create_creative", {"status": "ACTIVE"}) is None

    def test_it_never_answers_allow(self) -> None:
        for tool in ("ads_get_ad_accounts", "ads_create_campaign", "ads_activate_entity"):
            assert decision(run_hook(tool)) != "allow"


class TestDeny:
    @pytest.mark.parametrize("tool", ["ads_create_campaign", "ads_create_ad_set", "ads_create_ad"])
    def test_creating_a_live_object_is_refused(self, tool: str) -> None:
        answer = run_hook(tool, {"name": "x", "status": "ACTIVE"})
        assert decision(answer) == "deny"
        assert "created PAUSED" in reason(answer)

    @pytest.mark.parametrize("status", [["ACTIVE"], " active ", "ARCHIVED"])
    def test_other_spellings_of_not_paused_are_refused(self, status: Any) -> None:
        assert decision(run_hook("ads_create_campaign", {"status": status})) == "deny"

    def test_a_status_inside_a_json_string_is_found(self) -> None:
        answer = run_hook(
            "ads_create_ad", {"creative": json.dumps({"configured_status": "active"})}
        )
        assert decision(answer) == "deny"


class TestAsk:
    @pytest.mark.parametrize(
        ("tool", "word"),
        [
            ("ads_activate_entity", "`activate`"),
            ("ads_delete_custom_audience", "`delete`"),
            ("ads_update_custom_audience_users", "`pii_upload`"),
            ("ads_catalog_update_product_set", "`update_active`"),
            ("ads_experiment_abtest_create_test", "`update_active`"),
            ("ads_pixel_event_delete", "`delete`"),
            ("ads_boost_ig_post", "`activate`"),
        ],
    )
    def test_approval_classes_ask(self, tool: str, word: str) -> None:
        answer = run_hook(tool)
        assert decision(answer) == "ask"
        assert word in reason(answer)

    def test_an_entity_update_always_asks(self) -> None:
        answer = run_hook("ads_update_entity", {"entity_id": "1", "name": "renamed"})
        assert decision(answer) == "ask"
        assert "specific change" in reason(answer)

    def test_an_activation_through_update_says_so(self) -> None:
        answer = run_hook("ads_update_entity", {"entity_id": "1", "status": "ACTIVE"})
        assert "starts delivery" in reason(answer)

    def test_a_budget_change_shows_the_new_value(self) -> None:
        answer = run_hook("ads_update_entity", {"entity_id": "1", "daily_budget": 9000})
        assert "daily_budget=9000" in reason(answer)
        assert "minor units" in reason(answer)

    def test_an_unknown_write_tool_asks(self) -> None:
        answer = run_hook("ads_duplicate_campaign", {"id": "1"})
        assert decision(answer) == "ask"
        assert "not in meta-ads-agent's capability map" in reason(answer)

    def test_an_unknown_read_tool_is_left_alone(self) -> None:
        assert run_hook("ads_get_something_new") is None

    def test_any_server_name_is_covered(self) -> None:
        answer = run_hook("mcp__plugin_x_meta__ads_activate_entity")
        assert decision(answer) == "ask"


class TestFailure:
    def test_input_it_cannot_read_still_asks(self) -> None:
        answer = run_hook("", raw="{not json")
        assert decision(answer) == "ask"
        assert "could not check" in reason(answer)

    def test_a_tool_that_is_not_meta_is_ignored(self) -> None:
        assert run_hook("mcp__github__create_issue") is None

    def test_it_can_be_turned_off(self) -> None:
        off = run_hook("ads_activate_entity", env={"META_ADS_AGENT_HOOKS": "0"})
        assert off is None

    def test_a_missing_class_table_fails_towards_asking(self, tmp_path: Path) -> None:
        copy = tmp_path / "approval_gate.py"
        copy.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run(  # noqa: S603
            [PYTHON, "-I", str(copy)],
            input=json.dumps({"tool_name": SERVER + "ads_create_campaign", "tool_input": {}}),
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


class TestPackaging:
    def test_the_class_table_matches_capabilities(self) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(REPO / "scripts" / "build_hook_tool_classes.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_hooks_json_runs_this_script_on_meta_tools(self) -> None:
        config = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        (entry,) = config["hooks"]["PreToolUse"]
        assert entry["matcher"] == "mcp__.*__ads_.*"
        (hook,) = entry["hooks"]
        assert "${CLAUDE_PLUGIN_ROOT}/hooks/approval_gate.py" in hook["command"]
        assert " -I " in hook["command"]

    def test_the_hook_imports_only_the_standard_library(self) -> None:
        text = HOOK.read_text(encoding="utf-8")
        imported = {
            line.split()[1].split(".")[0]
            for line in text.splitlines()
            if line.startswith(("import ", "from "))
        }
        assert imported <= {"__future__", "json", "os", "re", "sys", "pathlib", "typing"}
