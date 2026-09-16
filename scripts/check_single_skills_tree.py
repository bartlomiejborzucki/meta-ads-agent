#!/usr/bin/env python3
"""Fail if skill content lives anywhere other than skills/.

ADR-003: there is exactly one canonical skills directory, and both host
manifests are thin wrappers over it. The failure mode this guards against is
skills-codex/ and skills-claude/ diverging silently, with reviewers unable to
tell which is current.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANONICAL = REPO / "skills"
IGNORED_PARTS = {".git", ".venv", "node_modules", "dist", "build", ".pytest_cache"}


def main() -> int:
    found = [
        path
        for path in REPO.rglob("SKILL.md")
        if not IGNORED_PARTS & set(path.relative_to(REPO).parts)
    ]

    if not found:
        print("error: no SKILL.md found at all")
        return 1

    strays = [p for p in found if CANONICAL not in p.parents]
    if strays:
        print(f"error: {len(strays)} SKILL.md file(s) outside skills/:")
        for path in strays:
            print(f"  - {path.relative_to(REPO)}")
        print("\nSkill content belongs only in skills/. Host-specific files go in")
        print("integrations/<host>/ or the host manifest. See")
        print("docs/architecture/adr/ADR-003-dual-agent-packaging.md")
        return 1

    # Every skill needs frontmatter with a name and a description, or the host
    # will not load it and the agent will not know when to use it.
    problems: list[str] = []
    for path in sorted(found):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            problems.append(f"{path.relative_to(REPO)}: no YAML frontmatter")
            continue
        end = text.find("\n---", 4)
        if end == -1:
            problems.append(f"{path.relative_to(REPO)}: unterminated frontmatter")
            continue
        frontmatter = text[4:end]
        for key in ("name:", "description:"):
            if key not in frontmatter:
                problems.append(f"{path.relative_to(REPO)}: frontmatter missing {key}")
        expected = path.parent.name
        if f"name: {expected}" not in frontmatter:
            problems.append(
                f"{path.relative_to(REPO)}: frontmatter name should match the "
                f"directory name ({expected})"
            )

    if problems:
        print(f"{len(problems)} frontmatter problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"one canonical skills tree, {len(found)} skill(s):")
    for path in sorted(found):
        print(f"  {path.parent.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
