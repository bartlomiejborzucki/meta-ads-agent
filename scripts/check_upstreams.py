#!/usr/bin/env python3
"""Compare tracked upstreams against the versions recorded in upstreams.yaml.

Watches what we *can* watch: the `facebook-business` release on PyPI, and the
HEAD commit or latest release of the GitHub repositories we track. Reports
drift; never changes anything and never merges anything. A plugin-format change
or an SDK major is a migration, not a dependency bump.

**It cannot watch Meta's official Ads MCP.** That server has no public
repository and publishes no schemas, and we will not put credentials in CI to
inspect it. Its refresh is a documented manual procedure -
docs/reference/capability-refresh.md. This script says so in its report, so the
absence is visible rather than assumed covered.

Writes a markdown report and sets the `drift` GitHub Actions output.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
UPSTREAMS = REPO / "upstreams.yaml"
TIMEOUT = 30


def fetch_json(url: str) -> Any | None:
    request = urllib.request.Request(  # noqa: S310 - fixed https hosts below
        url, headers={"Accept": "application/json", "User-Agent": "meta-ads-agent-upstream-check"}
    )
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        print(f"warning: could not fetch {url}: {exc}", file=sys.stderr)
        return None


def pypi_latest(package: str) -> str | None:
    payload = fetch_json(f"https://pypi.org/pypi/{package}/json")
    return (payload or {}).get("info", {}).get("version")


def github_head(repo: str) -> tuple[str | None, str | None]:
    payload = fetch_json(f"https://api.github.com/repos/{repo}/commits?per_page=1")
    if not payload or not isinstance(payload, list) or not payload:
        return None, None
    commit = payload[0]
    return commit.get("sha", "")[:7] or None, (
        commit.get("commit", {}).get("committer", {}).get("date")
    )


def github_latest_release(repo: str) -> str | None:
    payload = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    if payload and payload.get("tag_name"):
        return str(payload["tag_name"])
    tags = fetch_json(f"https://api.github.com/repos/{repo}/tags?per_page=1")
    if tags and isinstance(tags, list) and tags:
        return str(tags[0].get("name"))
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    document = yaml.safe_load(UPSTREAMS.read_text(encoding="utf-8"))
    entries = document.get("upstreams", [])

    drifted: list[str] = []
    unchanged: list[str] = []
    unchecked: list[str] = []

    for entry in entries:
        repo = entry.get("repo", "?")
        watch = entry.get("watch", "none")

        if watch == "none":
            unchecked.append(f"`{repo}` — not watched ({entry.get('integration_type')})")
            continue

        if entry.get("package"):
            latest = pypi_latest(entry["package"])
            reviewed = str(entry.get("reviewed_version", ""))
            if latest is None:
                unchecked.append(f"`{repo}` — PyPI lookup failed")
            elif latest != reviewed:
                drifted.append(
                    f"### `{repo}` ({entry['package']})\n\n"
                    f"- reviewed: **{reviewed}**\n"
                    f"- latest: **{latest}**\n"
                    f"- affected: {', '.join(entry.get('affected_areas') or ['-'])}\n\n"
                    f"{entry.get('notes', '').strip()}\n"
                )
            else:
                unchanged.append(f"`{repo}` — {latest}")
            continue

        if watch == "releases":
            latest = github_latest_release(repo)
            reviewed = str(entry.get("reviewed_version", ""))
            if latest is None:
                unchecked.append(f"`{repo}` — release lookup failed")
            elif reviewed and reviewed.lstrip("v") not in latest.lstrip("v"):
                drifted.append(
                    f"### `{repo}`\n\n"
                    f"- reviewed: **{reviewed}**\n"
                    f"- latest release: **{latest}**\n"
                    f"- affected: {', '.join(entry.get('affected_areas') or ['-'])}\n"
                )
            else:
                unchanged.append(f"`{repo}` — {latest}")
            continue

        # watch: head
        sha, date = github_head(repo)
        reviewed = str(entry.get("reviewed_sha", ""))
        if sha is None:
            unchecked.append(f"`{repo}` — commit lookup failed")
        elif reviewed in ("", "unpinned"):
            unchecked.append(f"`{repo}` — reviewed SHA is unpinned (HEAD is `{sha}`)")
        elif not sha.startswith(reviewed[:7]):
            drifted.append(
                f"### `{repo}`\n\n"
                f"- reviewed: **`{reviewed}`** ({entry.get('review_date')})\n"
                f"- current HEAD: **`{sha}`** ({date})\n"
                f"- compare: https://github.com/{repo}/compare/{reviewed}...{sha}\n"
                f"- affected: {', '.join(entry.get('affected_areas') or ['-'])}\n"
            )
        else:
            unchanged.append(f"`{repo}` — `{sha}`")

    today = dt.date.today().isoformat()
    lines = [
        f"## Upstream check — {today}",
        "",
        f"{len(drifted)} upstream(s) moved since their reviewed version.",
        "",
        "**Nothing is merged automatically.** Review each change, update",
        "`upstreams.yaml` with the new reviewed SHA or version, and adjust the",
        "affected areas if behaviour changed.",
        "",
    ]

    if drifted:
        lines += ["## Drifted", "", *drifted]
    if unchecked:
        lines += ["## Not checked", "", *(f"- {i}" for i in unchecked), ""]
    if unchanged:
        lines += ["## Unchanged", "", *(f"- {i}" for i in unchanged), ""]

    lines += [
        "## Not covered by this check",
        "",
        "**Meta's official Ads MCP.** It has no public repository and publishes",
        "no schemas, and we will not put credentials in CI to inspect it. Its",
        "capability map is refreshed manually by someone with an authenticated",
        "session — see `docs/reference/capability-refresh.md`. If an entry in",
        "`config/capabilities.yaml` is more than 90 days old,",
        "`meta-ads-agent doctor` will say so.",
        "",
    ]

    report = "\n".join(lines)
    print(report)

    if args.output:
        args.output.write_text(report, encoding="utf-8")

    if output_file := os.environ.get("GITHUB_OUTPUT"):
        with open(output_file, "a", encoding="utf-8") as stream:
            stream.write(f"drift={'true' if drifted else 'false'}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
