"""Terminal output helpers.

Two rules: everything user-visible passes through redaction, and colour is
optional. Output is read by agents as often as by humans, so structure matters
more than decoration and ``--json`` is available on every command that has a
result worth parsing.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from meta_ads_agent.redaction import redact, redact_mapping

_NO_COLOUR = bool(os.environ.get("NO_COLOR")) or not sys.stdout.isatty()

_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "cyan": "36",
}


def style(text: str, *names: str) -> str:
    if _NO_COLOUR or not names:
        return text
    codes = ";".join(_CODES[n] for n in names if n in _CODES)
    return f"\033[{codes}m{text}\033[0m" if codes else text


def echo(text: str = "", *names: str) -> None:
    """Print a redacted line."""
    print(style(redact(text), *names))


def warn(text: str) -> None:
    print(style(f"warning: {redact(text)}", "yellow"), file=sys.stderr)


def fail(text: str) -> None:
    print(style(f"error: {redact(text)}", "red"), file=sys.stderr)


def heading(text: str) -> None:
    echo("")
    echo(text, "bold")
    echo("-" * len(text), "dim")


def emit_json(payload: Any) -> None:
    """Print a redacted JSON document for machine consumption."""
    print(json.dumps(redact_mapping(payload), indent=2, ensure_ascii=False, default=str))


def status_line(label: str, status: str, detail: str = "") -> None:
    """One aligned status row, e.g. ``python      OK    3.13.7``."""
    colours = {
        "OK": ("green",),
        "READY": ("green",),
        "MISSING": ("yellow",),
        "OPTIONAL": ("dim",),
        "FAIL": ("red",),
        "INFO": ("dim",),
    }
    marker = style(f"{status:<8}", *colours.get(status, ()))
    echo(f"  {label:<26} {marker} {redact(detail)}")
