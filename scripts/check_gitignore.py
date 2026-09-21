#!/usr/bin/env python3
"""Assert .gitignore excludes the things that must never be committed.

Tested rather than assumed, because a .gitignore rule is easy to delete during
an unrelated edit and the consequence is a leaked credential or a published ad
account id.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Paths that must be ignored. Each is a real leak if committed.
MUST_IGNORE = (
    ".env",
    ".env.local",
    ".env.production",
    "private.pem",
    "server.key",
    "credentials.json",
    "secrets.yaml",
    "secrets.yml",
    ".meta-ads/brand.yaml",
    ".meta-ads/account.yaml",
    ".meta-ads/actions.jsonl",
    ".meta-ads/campaigns/acme/state.json",
    ".meta-ads/assets/manifest.json",
    ".meta-ads/reports/2026-09.md",
    "__pycache__/x.pyc",
    ".venv/bin/python",
)

# Paths that must NOT be ignored: the example env file, the skill-bundled
# templates a user copies from, and the examples CI validates.
MUST_NOT_IGNORE = (
    ".env.example",
    "release-manifest.json",
    "skills/meta-ads-core/assets/brand.yaml",
    "skills/meta-ads-campaign/assets/campaign-plan.yaml",
    "examples/brand.yaml",
    "examples/campaign-plan.yaml",
    "examples/state.json",
    "config/capabilities.yaml",
    "skills/meta-ads-core/SKILL.md",
    "upstreams.yaml",
)


def ignored(path: str) -> bool:
    result = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    # 0 = ignored, 1 = not ignored, other = error
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"git check-ignore failed for {path}: {result.stderr.decode(errors='replace')}"
        )
    return result.returncode == 0


def main() -> int:
    problems: list[str] = []

    for path in MUST_IGNORE:
        if not ignored(path):
            problems.append(f"{path} is NOT ignored and must be")

    for path in MUST_NOT_IGNORE:
        if ignored(path):
            problems.append(f"{path} IS ignored and must not be")

    if problems:
        print(f"{len(problems)} .gitignore problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f".gitignore ok: {len(MUST_IGNORE)} path(s) correctly ignored, "
        f"{len(MUST_NOT_IGNORE)} correctly tracked"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
