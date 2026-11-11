"""The upstream check's notion of a release that moved."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_upstreams.py"
_spec = importlib.util.spec_from_file_location("check_upstreams", _SCRIPT)
assert _spec and _spec.loader
check_upstreams = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_upstreams)


@pytest.mark.parametrize(
    ("reviewed", "latest", "compare", "moved"),
    [
        ("2.1.322", "v2.1.322", "exact", False),
        ("2.1.322", "v2.1.330", "exact", True),
        ("2.1.322", "v2.1.330", "minor", False),
        ("2.1.322", "v2.2.0", "minor", True),
        ("2.1.322", "v3.0.0", "minor", True),
        ("v26.0.4", "26.0.4", "exact", False),
    ],
)
def test_release_moved(reviewed: str, latest: str, compare: str, moved: bool) -> None:
    assert check_upstreams.release_moved(reviewed, latest, compare) is moved


def test_ci_installs_the_reviewed_claude_code() -> None:
    """CI validates the plugin with the Claude Code release upstreams.yaml says was reviewed."""
    import re

    import yaml

    root = _SCRIPT.parents[1]
    upstreams = yaml.safe_load((root / "upstreams.yaml").read_text(encoding="utf-8"))
    (entry,) = [u for u in upstreams["upstreams"] if u["repo"] == "anthropics/claude-code"]
    reviewed = str(entry["reviewed_version"])
    for workflow in ("ci.yml", "trigger-evals.yml"):
        text = (root / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        pins = re.findall(r"@anthropic-ai/claude-code@([\w.-]+)", text)
        assert pins, f"{workflow} no longer installs a pinned Claude Code"
        assert set(pins) == {reviewed}, (
            f"{workflow} pins {pins}, upstreams.yaml reviewed {reviewed}"
        )
