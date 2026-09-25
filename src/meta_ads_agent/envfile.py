"""The optional ``./.env`` file for the API fallback's settings.

The README and ``.env.example`` tell a user to copy the example to ``.env``
and fill in a token. This is what makes that work: at start-up the CLI reads
``.env`` from the current directory and sets the ``META_*`` variables it
defines that the environment does not already have.

Deliberately small:

* only ``META_*`` keys, so a project's unrelated ``.env`` cannot change
  anything else about the process;
* ``KEY=value`` lines, optional ``export``, optional matching quotes, ``#``
  comments - no variable expansion and no command substitution, so reading
  the file can never run anything;
* a variable already in the environment wins, **even when it is empty**. CI
  sets ``META_ACCESS_TOKEN=""`` on purpose so a stray live call fails; a
  ``.env`` must not be able to fill that back in.

Values are never printed. ``doctor`` says which file was read, and shows a
token only as its fingerprint, like any other.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"^\s*(?:export\s+)?(META_[A-Z0-9_]+)\s*=\s*(.*?)\s*$")

# Set by apply() so doctor can say where the values came from.
loaded_from: Path | None = None
loaded_keys: tuple[str, ...] = ()


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _LINE.match(line)
        if not match:
            continue
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def apply(directory: Path | None = None) -> tuple[str, ...]:
    """Fill ``META_*`` variables missing from the environment from ``./.env``."""
    global loaded_from, loaded_keys
    path = (directory or Path.cwd()) / ".env"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    applied = []
    for key, value in parse(text).items():
        if key in os.environ or not value:
            continue
        os.environ[key] = value
        applied.append(key)
    loaded_from, loaded_keys = path, tuple(sorted(applied))
    return loaded_keys
