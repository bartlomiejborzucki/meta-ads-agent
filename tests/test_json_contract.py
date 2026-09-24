"""The keys of every command's --json output, held to a recorded contract.

Agents and scripts read these keys. docs/reference/compatibility.md promises
that within a major version keys are only ever added: removing or renaming
one is a breaking change. This test records the keys each command emits
today (tests/fixtures/json-contract.json) and fails if any disappears.

A new key is fine and needs no change here. To add it to the contract -
which makes it a promise - regenerate with META_ADS_UPDATE_JSON_CONTRACT=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import plan_dict
from meta_ads_agent.cli.main import main

CONTRACT = Path(__file__).parent / "fixtures" / "json-contract.json"


def keys(value: Any, prefix: str = "") -> set[str]:
    """Dotted key paths of objects, looking into the first item of lists."""
    out: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.add(path)
            out |= keys(item, path)
    elif isinstance(value, list) and value:
        out |= keys(value[0], f"{prefix}[]")
    return out


def daily_rows() -> list[dict[str, object]]:
    return [
        {
            "date_start": f"2026-09-{d:02d}",
            "date_stop": f"2026-09-{d:02d}",
            "spend": "100",
            "impressions": "10000",
            "inline_link_clicks": "200",
            "ad_id": "ad-a",
            "adset_id": "set-1",
            "actions": [{"action_type": "lead", "value": "6"}],
        }
        for d in range(1, 29)
    ]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in ("META_ADS_WORKSPACE", "META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    campaign = tmp_path / ".meta-ads" / "campaigns" / "acme-webinar"
    campaign.mkdir(parents=True)
    (campaign / "plan.yaml").write_text(yaml.safe_dump(plan_dict()))
    (tmp_path / "insights.json").write_text(json.dumps({"data": daily_rows()}))
    return tmp_path


COMMANDS: dict[str, list[str]] = {
    "validate-plan": [
        "validate-plan",
        ".meta-ads/campaigns/acme-webinar/plan.yaml",
        "--skip-assets",
    ],
    "state": ["state"],
    "capabilities": ["capabilities"],
    "render-plan": ["render-plan", ".meta-ads/campaigns/acme-webinar/plan.yaml"],
    "report compare": [
        "report",
        "compare",
        "insights.json",
        "--days",
        "7",
        "--result-event",
        "lead",
    ],
    "report fatigue": ["report", "fatigue", "insights.json"],
    "report pacing": ["report", "pacing", "insights.json", "--daily-budget", "100"],
    "report power": [
        "report",
        "power",
        "--baseline-rate",
        "0.03",
        "--units-per-day",
        "400",
        "--days",
        "14",
    ],
}


def emitted(argv: list[str], capsys: pytest.CaptureFixture[str]) -> set[str]:
    main([*argv, "--json"])
    return keys(json.loads(capsys.readouterr().out))


def test_no_recorded_key_has_gone(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    current = {name: sorted(emitted(argv, capsys)) for name, argv in COMMANDS.items()}
    if os.environ.get("META_ADS_UPDATE_JSON_CONTRACT") == "1":
        CONTRACT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    missing = {
        name: sorted(set(recorded) - set(current.get(name, [])))
        for name, recorded in contract.items()
        if set(recorded) - set(current.get(name, []))
    }
    assert missing == {}, f"--json keys removed or renamed (a breaking change): {missing}"


def test_every_contracted_command_is_still_exercised() -> None:
    assert set(json.loads(CONTRACT.read_text(encoding="utf-8"))) <= set(COMMANDS)
