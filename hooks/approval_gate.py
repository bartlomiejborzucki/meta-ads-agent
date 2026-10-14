#!/usr/bin/env python3
"""PreToolUse hook: enforce meta-ads-agent's approval classes in Claude Code.

Claude Code runs this before every call to an ``ads_*`` tool on any MCP
server, with the call as JSON on stdin. It answers on stdout:

- ``ask`` for a tool whose class needs explicit approval (activation, budget
  or live changes, deletes, customer-list uploads), and for an ``ads_*``
  write tool it does not know;
- ``deny`` for a campaign, ad set or ad created with a status other than
  PAUSED;
- nothing at all otherwise, which leaves the call to the user's own
  permission settings. It never answers ``allow``.

Standard library only, and Python 3.8 or later (macOS ships 3.9), so it
works without the optional CLI and with the system python3. It never writes
the tool input anywhere. ``META_ADS_AGENT_HOOKS=0`` turns it off, and
``META_ADS_AGENT_HOOKS=strict`` turns every ``ask`` into ``deny``. Under
Codex, which loads plugin hooks once the user trusts them but cannot ask,
strict is automatic. The design
and its limits are in docs/architecture/adr/ADR-011-hooks-enforce-approvals.md.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

CLASSES_FILE = Path(__file__).resolve().parent / "tool-classes.json"

_TOOL_NAME = re.compile(r"^mcp__.+__(ads_[a-z0-9_]+)$")
_WRITE_WORDS = (
    "create", "update", "delete", "activate", "boost", "connect", "upload",
    "schedule", "set", "remove", "add", "pause", "duplicate", "copy", "publish",
)  # fmt: skip
_READ_WORDS = ("get", "read", "list", "search", "check", "insights", "library", "help")
_STATUS_KEYS = {"status", "configured_status", "effective_status"}
_BUDGET_WORDS = ("budget", "bid_amount", "spend_cap")

# Entities that deliver. A creative or an audience with status ACTIVE
# spends nothing; a campaign, ad set or ad can.
_DELIVERING_CREATES = {"ads_create_campaign", "ads_create_ad_set", "ads_create_ad"}

_WHY = {
    "update_active": "it changes something live: delivery, or what live ads read",
    "budget_increase": "it can change a budget, which moves money",
    "activate": "it starts delivery, which spends money",
    "bulk": "it changes many objects at once",
    "delete": "it deletes, which cannot be undone; pausing keeps the history",
    "pii_upload": "it uploads customer data",
    "unknown": "this tool is not in meta-ads-agent's capability map, and its name is not a read",
}

_DISABLED = {"0", "false", "no", "off"}


def _decision(kind: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": f"meta-ads-agent: {reason}",
        }
    }


def _words(tool: str) -> list[str]:
    return tool[len("ads_") :].split("_")


def _looks_like_a_read(tool: str) -> bool:
    words = _words(tool)
    if any(w in _WRITE_WORDS for w in words):
        return False
    return any(w in _READ_WORDS for w in words)


def _walk(value: Any, depth: int = 0) -> list[tuple[str, Any]]:
    """Every (key, value) pair in the input, including inside JSON strings.

    Meta's MCP is reported to take some objects (targeting, the creative on
    an ad) as JSON-encoded strings, so a status can hide inside one.
    """
    if depth > 8:
        return []
    found: list[tuple[str, Any]] = []
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append((str(key).lower(), item))
            found.extend(_walk(item, depth + 1))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk(item, depth + 1))
    return found


def _statuses(tool_input: Any) -> list[str]:
    found: list[str] = []
    for key, value in _walk(tool_input):
        if key not in _STATUS_KEYS:
            continue
        values = value if isinstance(value, list) else [value]
        found.extend(str(v).strip() for v in values if isinstance(v, str))
    return found


def _budget_fields(tool_input: Any) -> list[str]:
    return [
        f"{k}={v}"
        for k, v in _walk(tool_input)
        if any(w in k for w in _BUDGET_WORDS)
        and isinstance(v, (str, int, float))  # a tuple: runs on 3.8
    ]


def _update_reason(tool: str, tool_input: Any) -> str:
    parts = [f"{tool} can pause, edit live objects, or change budgets"]
    statuses = _statuses(tool_input)
    if any(s.upper() == "ACTIVE" for s in statuses):
        parts = [f"{tool} sets status ACTIVE, which starts delivery"]
    elif statuses:
        parts.append(f"this call sets status {', '.join(statuses)}")
    budgets = _budget_fields(tool_input)
    if budgets:
        parts.append(
            f"new value(s) {', '.join(budgets)} in the account's minor units; "
            "check the old value was shown in the account currency"
        )
    parts.append("approve only if you asked for this specific change")
    return "; ".join(parts) + "."


def decide(payload: dict[str, Any], classes: dict[str, Any] | None) -> dict[str, Any] | None:
    """The hook's answer for one call, or None to stay silent."""
    match = _TOOL_NAME.match(str(payload.get("tool_name", "")))
    if not match:
        return None
    tool = match.group(1)
    tool_input = payload.get("tool_input") or {}

    if tool in _DELIVERING_CREATES:
        live = [s for s in _statuses(tool_input) if s.upper() != "PAUSED"]
        if live:
            return _decision(
                "deny",
                f"{tool} with status {', '.join(live)}. Everything is created PAUSED; "
                "activation is a separate step after previews and the user's approval.",
            )

    if tool == "ads_update_entity":
        return _decision("ask", _update_reason(tool, tool_input))

    known = (classes or {}).get("tools", {})
    level = known.get(tool)
    if level is None:
        if _looks_like_a_read(tool):
            return None
        return _decision("ask", f"{tool}: {_WHY['unknown']}.")

    required = set((classes or {}).get("approval_required", ()))
    if level in required:
        why = _WHY.get(level, "it needs explicit approval")
        return _decision(
            "ask",
            f"{tool} is `{level}`: {why}. Approve only if you asked for this specific change.",
        )
    return None


def _load_classes() -> dict[str, Any] | None:
    try:
        data = json.loads(CLASSES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _strict(answer: dict[str, Any]) -> dict[str, Any]:
    """``ask`` as ``deny``, for a host that cannot ask.

    Codex parses ``ask`` but does not support it: it reports a failed hook
    and runs the call. On such a host the only answer that holds is ``deny``.
    """
    out = answer["hookSpecificOutput"]
    if out["permissionDecision"] != "ask":
        return answer
    reason = out["permissionDecisionReason"][len("meta-ads-agent: ") :]
    return _decision(
        "deny",
        f"strict mode refuses what it would otherwise ask about. {reason} "
        "To make this change, the user runs it with META_ADS_AGENT_HOOKS unset, "
        "or makes it in Ads Manager.",
    )


def _host_cannot_ask(payload: Any) -> bool:
    """Codex runs this hook from the plugin too, and cannot ask.

    Its PreToolUse input carries ``turn_id`` and no ``permission_mode``;
    Claude Code's carries ``permission_mode``. Mistaking one for the other
    errs towards deny, which is the safe direction.
    """
    return isinstance(payload, dict) and "turn_id" in payload and "permission_mode" not in payload


def main() -> int:
    mode = os.environ.get("META_ADS_AGENT_HOOKS", "").strip().lower()
    if mode in _DISABLED:
        return 0
    payload: Any = None
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("the hook input is not a JSON object")
        answer = decide(payload, _load_classes())
    except Exception as exc:  # any failure must still ask
        answer = _decision("ask", f"the approval hook could not check this call ({exc}).")
    if answer is not None and (mode == "strict" or _host_cannot_ask(payload)):
        answer = _strict(answer)
    if answer is not None:
        sys.stdout.write(json.dumps(answer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
