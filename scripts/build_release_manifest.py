#!/usr/bin/env python3
"""Generate release-manifest.json from the working tree.

The manifest is the release's own account of what it consists of, and it is
generated rather than maintained so that adding a file cannot be half done.
``--check`` compares the committed manifest with the tree and fails on any
difference, which is what stops a release shipping a payload nobody described.

Exit 0 when written or already current, 1 on drift.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from meta_ads_agent import __version__  # noqa: E402
from meta_ads_agent.install.manifest import (  # noqa: E402
    MigrationRef,
    build_manifest,
    load_manifest,
)
from meta_ads_agent.install.migrations import REGISTRY  # noqa: E402

MANIFEST = REPO / "release-manifest.json"

# Script-backed migrations this release expects, if any. Built-in migrations
# come from the registry and need no entry here - only the ones carried out by
# a script inside the payload do, because those are the ones whose bytes have
# to be pinned before anything will execute them.
SCRIPT_MIGRATIONS: tuple[MigrationRef, ...] = ()


def declared_migrations() -> tuple[MigrationRef, ...]:
    built_in = tuple(
        MigrationRef(
            id=migration.id,
            description=migration.description,
            introduced_in=migration.introduced_in,
        )
        for migration in REGISTRY
    )
    return built_in + SCRIPT_MIGRATIONS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    args = parser.parse_args()

    fresh = build_manifest(REPO, __version__, migrations=declared_migrations())

    if args.check:
        if not MANIFEST.is_file():
            print(f"error: {MANIFEST.name} is missing. Run: python3 {Path(__file__).name}")
            return 1
        committed = load_manifest(MANIFEST)
        problems: list[str] = []
        if committed.version != fresh.version:
            problems.append(f"version: manifest {committed.version}, package {fresh.version}")
        if committed.digest != fresh.digest:
            old = committed.by_path()
            new = fresh.by_path()
            for path in sorted(set(new) - set(old)):
                problems.append(f"not in the manifest: {path}")
            for path in sorted(set(old) - set(new)):
                problems.append(f"in the manifest but not in the tree: {path}")
            for path in sorted(set(old) & set(new)):
                if old[path].sha256 != new[path].sha256:
                    problems.append(f"changed since the manifest was built: {path}")
        declared = {m.id for m in committed.migrations}
        expected = {m.id for m in fresh.migrations}
        for missing in sorted(expected - declared):
            problems.append(f"migration not declared in the manifest: {missing}")
        for extra in sorted(declared - expected):
            problems.append(f"manifest declares an unknown migration: {extra}")

        if problems:
            print(f"{MANIFEST.name} is out of date ({len(problems)} difference(s)):")
            for problem in problems:
                print(f"  - {problem}")
            print(f"\nRegenerate it:  python3 scripts/{Path(__file__).name}")
            return 1
        print(
            f"{MANIFEST.name} matches the tree: {fresh.version}, "
            f"{len(fresh.entries)} file(s), digest {fresh.digest[:12]}"
        )
        return 0

    MANIFEST.write_text(fresh.to_json(), encoding="utf-8")
    print(
        f"wrote {MANIFEST.name}: {fresh.version}, {len(fresh.entries)} file(s) "
        f"across {len(fresh.skills)} skill(s), digest {fresh.digest[:12]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
