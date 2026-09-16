#!/usr/bin/env python3
"""Replace the `OWNER` placeholder with a real GitHub owner.

The repository ships with `OWNER/meta-ads-agent` in URLs because the owner is
not knowable in advance, and a wrong owner in an install command is worse than
an obvious placeholder.

    python3 scripts/set_repo_owner.py my-github-username
    python3 scripts/set_repo_owner.py my-org --repo meta-ads-toolkit
    python3 scripts/set_repo_owner.py my-org --check

`--check` reports where placeholders remain without changing anything, which is
what you want in CI once the project has an owner.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLACEHOLDER_OWNER = "OWNER"
DEFAULT_REPO_NAME = "meta-ads-agent"

# Only files that carry URLs. Skipping the rest keeps the diff readable.
SUFFIXES = {".md", ".json", ".toml", ".yml", ".yaml"}


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [
        REPO / line
        for line in output.splitlines()
        if Path(line).suffix in SUFFIXES and (REPO / line).is_file()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner", help="GitHub user or organisation")
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO_NAME,
        help=f"repository name, if you renamed the project (default: {DEFAULT_REPO_NAME})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report remaining placeholders without changing anything",
    )
    args = parser.parse_args()

    pattern = re.compile(rf"\b{PLACEHOLDER_OWNER}/{re.escape(DEFAULT_REPO_NAME)}\b")
    replacement = f"{args.owner}/{args.repo}"

    if args.check:
        offenders: list[str] = []
        for path in tracked_files():
            text = path.read_text(encoding="utf-8")
            count = len(pattern.findall(text))
            if count:
                offenders.append(f"{path.relative_to(REPO)} ({count})")
        if offenders:
            print(f"{len(offenders)} file(s) still contain the placeholder:")
            for entry in offenders:
                print(f"  - {entry}")
            return 1
        print("no placeholders remain")
        return 0

    changed = 0
    for path in tracked_files():
        text = path.read_text(encoding="utf-8")
        updated = pattern.sub(replacement, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(f"updated {path.relative_to(REPO)}")

    if not changed:
        print("nothing to change")
        return 0

    print(f"\n{changed} file(s) now point at {replacement}")
    print("Review the diff, then commit:")
    print("  git diff")
    print(f'  git commit -am "Point URLs at {replacement}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
