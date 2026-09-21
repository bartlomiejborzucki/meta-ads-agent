#!/usr/bin/env python3
"""Render the shared skill blocks from packaging/shared/ into every SKILL.md.

Each skill directory is installable on its own, so anything a skill needs has
to be physically inside it. A few passages genuinely belong in more than one
skill - the preflight checks above all - and copying prose by hand across nine
files is how nine files end up saying eight different things.

So the copies are generated. ``packaging/shared/<name>.md`` is the only place
the text is edited; this script writes it between the markers

    <!-- shared:<name> start ... -->
    <!-- shared:<name> end -->

in each SKILL.md that declares them. ``--check`` verifies the copies are
current without writing, which is what CI runs.

Exit 0 when everything is in sync (or was synced), 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHARED = REPO / "packaging" / "shared"
SKILLS = REPO / "skills"

# Which skills must carry which block. A skill that writes to an ad account
# needs the no-CLI write policy; every skill needs the preflight, because any
# one of them can be the first thing loaded in a session.
REQUIRED: dict[str, set[str] | None] = {
    "preflight": None,  # None = every skill
    "no-cli-writes": {"meta-ads-core", "meta-ads-campaign"},
}

_NOTE = "generated from packaging/shared/{name}.md by scripts/sync_skill_blocks.py - edit there"


def block_pattern(name: str) -> re.Pattern[str]:
    tag = re.escape(name)
    return re.compile(
        rf"<!-- shared:{tag} start.*?-->\n(?:.*?\n)?<!-- shared:{tag} end -->",
        re.DOTALL,
    )


def rendered(name: str, body: str) -> str:
    return (
        f"<!-- shared:{name} start - {_NOTE.format(name=name)} -->\n"
        f"{body.strip()}\n"
        f"<!-- shared:{name} end -->"
    )


def sources() -> dict[str, str]:
    if not SHARED.is_dir():
        raise SystemExit(f"error: {SHARED.relative_to(REPO)} does not exist")
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(SHARED.glob("*.md"))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report drift instead of rewriting the skills"
    )
    args = parser.parse_args()

    blocks = sources()
    unknown = set(REQUIRED) - set(blocks)
    if unknown:
        print(f"error: REQUIRED names a block with no source file: {sorted(unknown)}")
        return 1

    problems: list[str] = []
    changed: list[str] = []

    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        skill = skill_md.parent.name
        text = original = skill_md.read_text(encoding="utf-8")

        for name, body in blocks.items():
            wanted = REQUIRED.get(name)
            required_here = wanted is None or skill in wanted
            match = block_pattern(name).search(text)

            if match is None:
                if required_here:
                    problems.append(
                        f"{skill}: missing the shared:{name} markers. Add\n"
                        f"    <!-- shared:{name} start -->\n"
                        f"    <!-- shared:{name} end -->\n"
                        f"  where the block belongs, then re-run this script."
                    )
                continue

            if not required_here:
                problems.append(f"{skill}: carries shared:{name}, which it is not meant to have")
                continue

            text = text[: match.start()] + rendered(name, body) + text[match.end() :]

        if text != original:
            changed.append(skill)
            if not args.check:
                skill_md.write_text(text, encoding="utf-8")

    if args.check and changed:
        problems.append(
            "shared blocks are stale in: "
            + ", ".join(changed)
            + "\n  Run: python3 scripts/sync_skill_blocks.py"
        )

    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    if args.check:
        print(f"shared blocks in sync across {len(list(SKILLS.glob('*/SKILL.md')))} skill(s)")
    else:
        print(f"synced {len(blocks)} block(s); rewrote: {', '.join(changed) or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
