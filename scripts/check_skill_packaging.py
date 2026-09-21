#!/usr/bin/env python3
"""Install the skills the way an agent host would, then check they still work.

A skill directory is the unit of distribution. It can arrive three ways:

1. the whole plugin, manifest and all;
2. the whole ``skills/`` tree, dropped into a skills directory;
3. a single ``skills/meta-ads-<name>/`` directory, copied on its own.

Only the first keeps the repository around it, and for a long time the skills
quietly assumed otherwise - pointing at ``docs/``, ``templates/`` and
``config/`` paths that exist in a checkout and nowhere else. That failure is
invisible from the repository, which is why this check copies the skills out
first and only then resolves their references.

What it asserts, for every shape:

* every path-shaped reference in a skill resolves inside that same skill;
* every ``meta-ads-agent`` command mentioned is a real CLI subcommand, so a
  skill can never send a user after something that does not exist;
* every skill carries the shared preflight block, so the MCP check and the
  separate CLI check happen before anything else;
* the skills that write to an ad account carry the no-CLI write policy.

Nothing here touches the network or a Meta account.

Exit 0 on success, 1 with a list of problems.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
sys.path.insert(0, str(REPO / "src"))

# Reference shapes we resolve. A markdown link is unambiguous; a backticked
# token is a judgement call, so the filters below are deliberately narrow -
# better to miss an odd reference than to fail on prose.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
BACKTICKED = re.compile(r"`([^`\n]+)`")
PATH_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".jsonl", ".py", ".toml")

# Paths that are not repository paths at all: the user's workspace, their own
# creative files, their home directory, and anything with a placeholder in it.
NOT_A_REPO_PATH = (".meta-ads/", "./creatives/", "~/", "offers/", "campaigns/")

CLI_MENTION = re.compile(r"meta-ads-agent\s+(?!--)([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?")

# Skills that create or mutate objects on an ad account, and therefore must
# say what happens when the validator is not installed.
WRITING_SKILLS = {"meta-ads-core", "meta-ads-campaign"}

PREFLIGHT_MARKERS = ("<!-- shared:preflight start", "meta-ads-agent --version")
NO_CLI_MARKERS = ("<!-- shared:no-cli-writes start", "uvx --from", "stop before the first write")


def references(path: Path) -> Iterator[tuple[str, str]]:
    """Yield ``(kind, target)`` for each path-shaped reference in a markdown file."""
    text = path.read_text(encoding="utf-8")

    for target in MD_LINK.findall(text):
        target = target.split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        yield "link", target

    for token in BACKTICKED.findall(text):
        token = token.strip()
        if " " in token or "/" not in token or not token.endswith(PATH_SUFFIXES):
            continue
        if token.startswith(NOT_A_REPO_PATH) or "<" in token or "{" in token:
            continue
        yield "path", token


def check_tree(root: Path, shape: str) -> list[str]:
    """Resolve every reference in an installed tree. ``root`` holds skill dirs."""
    problems: list[str] = []
    for skill_dir in sorted(p for p in root.iterdir() if (p / "SKILL.md").is_file()):
        boundary = skill_dir.resolve()
        for markdown in sorted(skill_dir.rglob("*.md")):
            for kind, target in references(markdown):
                resolved = (markdown.parent / target).resolve()
                where = f"{shape}: {skill_dir.name}/{markdown.relative_to(skill_dir)}"
                if not resolved.is_relative_to(boundary):
                    problems.append(
                        f"{where} [{kind}] -> {target}\n"
                        f"      leaves the skill directory. Cross-skill and repository "
                        f"references must be absolute URLs."
                    )
                elif not resolved.exists():
                    problems.append(
                        f"{where} [{kind}] -> {target}\n      does not exist after install"
                    )
    return problems


def check_cli_mentions() -> list[str]:
    """Every command a skill names must exist, or we send users after a ghost."""
    from meta_ads_agent.cli.main import build_parser

    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    )
    known: set[str] = set()
    for name, sub in subparsers.choices.items():
        known.add(name)
        for nested in getattr(sub, "_actions", []):
            for child in getattr(nested, "choices", None) or {}:
                known.add(f"{name} {child}")

    problems: list[str] = []
    for markdown in sorted(SKILLS.rglob("*.md")):
        for first, second in CLI_MENTION.findall(markdown.read_text(encoding="utf-8")):
            command = f"{first} {second}".strip() if first == "api" and second else first
            if command not in known:
                problems.append(
                    f"{markdown.relative_to(REPO)}: mentions 'meta-ads-agent {command}', "
                    f"which is not a subcommand. Known: {', '.join(sorted(known))}"
                )
    return problems


def check_required_blocks() -> list[str]:
    problems: list[str] = []
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        # Normalised, because these blocks are hard-wrapped prose and a marker
        # should not start failing because a sentence rewrapped.
        text = " ".join(skill_md.read_text(encoding="utf-8").split())
        skill = skill_md.parent.name
        for marker in PREFLIGHT_MARKERS:
            if marker not in text:
                problems.append(f"{skill}: preflight block is missing or incomplete ({marker!r})")
        if skill in WRITING_SKILLS:
            for marker in NO_CLI_MARKERS:
                if marker not in text:
                    problems.append(
                        f"{skill}: writes to an account but does not carry the "
                        f"no-CLI write policy ({marker!r})"
                    )
    return problems


def main() -> int:
    problems: list[str] = []

    with tempfile.TemporaryDirectory(prefix="skill-install-") as tmp:
        tmpdir = Path(tmp)

        # Shape 1 and 2: the whole skills tree, as a plugin or a skills dir.
        whole = tmpdir / "whole" / "skills"
        shutil.copytree(SKILLS, whole)
        problems += check_tree(whole, "full tree")

        # Shape 3: one directory at a time, the way someone copies a single
        # skill out of the repository.
        each = tmpdir / "each"
        each.mkdir(parents=True)
        for skill_dir in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
            shutil.copytree(skill_dir, each / skill_dir.name)
        for skill_dir in sorted(each.iterdir()):
            solo = tmpdir / "solo" / skill_dir.name
            solo.parent.mkdir(exist_ok=True)
            shutil.copytree(skill_dir, solo / skill_dir.name)
            problems += check_tree(solo, "standalone")
            shutil.rmtree(solo)

    problems += check_cli_mentions()
    problems += check_required_blocks()

    if problems:
        print(f"{len(problems)} packaging problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    count = len(list(SKILLS.glob("*/SKILL.md")))
    print(
        f"skill packaging ok: {count} skill(s) resolve every reference as a full "
        f"tree and standalone; CLI mentions and shared blocks check out"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
