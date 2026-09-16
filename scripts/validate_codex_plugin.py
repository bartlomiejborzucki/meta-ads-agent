#!/usr/bin/env python3
"""Validate .codex-plugin/plugin.json against OpenAI's documented spec.

Codex publishes no validator we can run in CI, so this checks the structural
rules from its plugin.json specification: required fields, kebab-case name,
strict semver, absolute HTTPS policy URLs, the defaultPrompt limits, that
component paths begin with "./" and exist, and that declared assets are
actually present.

It also checks the two host manifests agree on name, version, and license -
they are separate files describing one plugin, and they drift silently.

Exit 0 on success, 1 with a list of problems.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODEX = REPO / ".codex-plugin" / "plugin.json"
CLAUDE = REPO / ".claude-plugin" / "plugin.json"

REQUIRED = ("name", "version", "description", "author", "interface")
PATH_FIELDS = ("skills", "mcpServers", "apps", "hooks")
URL_FIELDS = ("websiteURL", "privacyPolicyURL", "termsOfServiceURL")
ASSET_FIELDS = ("composerIcon", "logo", "logoDark")

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> int:
    problems: list[str] = []

    if not CODEX.is_file():
        print(f"error: {CODEX} not found")
        return 1

    try:
        manifest = json.loads(CODEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {CODEX} is not valid JSON: {exc}")
        return 1

    for field in REQUIRED:
        if field not in manifest:
            problems.append(f"missing required field: {field}")

    name = manifest.get("name", "")
    if not NAME_RE.match(name):
        problems.append(f"name must be kebab-case, got {name!r}")

    version = manifest.get("version", "")
    if not SEMVER_RE.match(version):
        problems.append(f"version must be strict semver, got {version!r}")

    author = manifest.get("author")
    if not isinstance(author, dict) or not author.get("name"):
        problems.append("author must be an object with a name")

    for field in PATH_FIELDS:
        value = manifest.get(field)
        if not isinstance(value, str):
            continue
        if not value.startswith("./"):
            problems.append(f"{field} path must begin with './', got {value!r}")
        elif not (REPO / value[2:]).exists():
            problems.append(f"{field} points at {value!r}, which does not exist")

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        problems.append("interface must be an object")
    else:
        if not interface.get("displayName"):
            problems.append("interface.displayName is required")

        prompts = interface.get("defaultPrompt", [])
        if not isinstance(prompts, list):
            problems.append("interface.defaultPrompt must be a list")
        else:
            if len(prompts) > 3:
                problems.append(
                    f"interface.defaultPrompt takes at most 3 strings, got {len(prompts)}"
                )
            for prompt in prompts:
                if not isinstance(prompt, str):
                    problems.append("interface.defaultPrompt entries must be strings")
                elif len(prompt) > 128:
                    problems.append(
                        f"interface.defaultPrompt entry is {len(prompt)} chars "
                        f"(max 128): {prompt[:40]!r}..."
                    )

        for field in URL_FIELDS:
            value = interface.get(field)
            if value is None:
                continue
            if not isinstance(value, str) or not value.startswith("https://"):
                problems.append(f"interface.{field} must be an absolute https URL")

        for field in ASSET_FIELDS:
            value = interface.get(field)
            if not isinstance(value, str):
                continue
            if not value.startswith("./"):
                problems.append(f"interface.{field} must begin with './'")
            elif not (REPO / value[2:]).is_file():
                problems.append(
                    f"interface.{field} points at {value!r}, which is not in the repository"
                )

        for shot in interface.get("screenshots", []) or []:
            if not isinstance(shot, str) or not shot.startswith("./assets/"):
                problems.append("interface.screenshots entries must live under ./assets/")
            elif not (REPO / shot[2:]).is_file():
                problems.append(f"screenshot {shot!r} is not in the repository")

        brand = interface.get("brandColor")
        if brand is not None and not re.match(r"^#[0-9A-Fa-f]{6}$", str(brand)):
            problems.append(f"interface.brandColor must be a hex colour, got {brand!r}")

    # The two manifests describe one plugin and drift silently.
    if CLAUDE.is_file():
        claude = json.loads(CLAUDE.read_text(encoding="utf-8"))
        for field in ("name", "version", "license"):
            if claude.get(field) != manifest.get(field):
                problems.append(
                    f"{field} differs between manifests: "
                    f"codex={manifest.get(field)!r} claude={claude.get(field)!r}"
                )

    if problems:
        print(f"{CODEX.relative_to(REPO)}: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"{CODEX.relative_to(REPO)}: ok "
        f"({manifest['name']} {manifest['version']}, skills -> {manifest.get('skills')})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
