"""The brand workspace: private, local, outside the plugin.

Layout of ``.meta-ads/`` in the user's project:

    .meta-ads/
      brand.yaml              structured brand + account defaults
      voice.md                free-form brand voice (prose, read by the creative skill)
      account.yaml            cached account facts; Meta stays authoritative
      offers/<slug>.yaml      reusable offer briefs
      assets/manifest.json    local file fingerprint -> remote image hash / video id
      assets/                 the user's own creative files, if they keep them here
      campaigns/<slug>/
        plan.yaml             intent
        state.json            what exists on Meta
        creatives.json        creative detail as built
        qa.md                 preview QA notes
        report.md             latest report
      reports/                account-level reports
      actions.jsonl           append-only audit log
      state/                  scratch for resumable operations

Why not inside the plugin: plugin directories hold installed code, are wiped on
reinstall, and are shared between projects. Account ids, performance exports,
and creative assets belong to the user's project and are gitignored by default.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from meta_ads_agent.errors import WorkspaceError

WORKSPACE_DIRNAME = ".meta-ads"
WORKSPACE_ENV_VAR = "META_ADS_WORKSPACE"

# 1-63 characters: a single-character slug is legitimate.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def slugify(text: str) -> str:
    """Directory-safe slug.

    Paths containing spaces or non-ASCII are legal on every platform we support
    but make shell quoting and cross-platform behaviour needlessly fragile, so
    generated directory names are constrained even though the user's own project
    path is not.
    """
    lowered = (text or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:63]
    if not slug or not _SLUG_RE.match(slug):
        raise WorkspaceError(
            f"cannot derive a directory-safe name from {text!r}; "
            "pass an explicit slug of lowercase letters, digits, and hyphens"
        )
    return slug


def atomic_write(path: Path, content: str) -> None:
    """Write via a temporary file and :func:`os.replace`.

    State files are written after every create. A crash mid-write must not
    truncate the record of an object that already exists on Meta.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@dataclass(frozen=True, slots=True)
class Workspace:
    """Resolved paths for one brand workspace."""

    root: Path

    # -- resolution --------------------------------------------------------
    @classmethod
    def locate(cls, start: Path | str | None = None, *, required: bool = True) -> Workspace:
        """Find the workspace.

        Order: ``META_ADS_WORKSPACE``, then ``.meta-ads/`` in *start* or any
        parent. Walking up means a command run from a subdirectory of the
        project still finds it, the way git does.
        """
        override = os.environ.get(WORKSPACE_ENV_VAR)
        if override:
            root = Path(override).expanduser()
            if required and not root.is_dir():
                raise WorkspaceError(
                    f"{WORKSPACE_ENV_VAR} points at {root}, which is not a directory"
                )
            return cls(root=root)

        current = Path(start).resolve() if start else Path.cwd().resolve()
        for candidate in (current, *current.parents):
            root = candidate / WORKSPACE_DIRNAME
            if root.is_dir():
                return cls(root=root)

        if required:
            raise WorkspaceError(
                f"No {WORKSPACE_DIRNAME}/ workspace found in {current} or any parent. "
                "Run 'meta-ads-agent init' to create one."
            )
        return cls(root=current / WORKSPACE_DIRNAME)

    @classmethod
    def at(cls, root: Path | str) -> Workspace:
        """A workspace at an explicit path, without searching."""
        return cls(root=Path(root).expanduser())

    # -- paths -------------------------------------------------------------
    @property
    def exists(self) -> bool:
        return self.root.is_dir()

    @property
    def brand_file(self) -> Path:
        return self.root / "brand.yaml"

    @property
    def voice_file(self) -> Path:
        return self.root / "voice.md"

    @property
    def account_file(self) -> Path:
        return self.root / "account.yaml"

    @property
    def offers_dir(self) -> Path:
        return self.root / "offers"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def asset_manifest_file(self) -> Path:
        return self.assets_dir / "manifest.json"

    @property
    def campaigns_dir(self) -> Path:
        return self.root / "campaigns"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def action_log_file(self) -> Path:
        return self.root / "actions.jsonl"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    def campaign_dir(self, slug: str) -> Path:
        return self.campaigns_dir / slugify(slug)

    def plan_file(self, slug: str) -> Path:
        return self.campaign_dir(slug) / "plan.yaml"

    def state_file(self, slug: str) -> Path:
        return self.campaign_dir(slug) / "state.json"

    def creatives_file(self, slug: str) -> Path:
        return self.campaign_dir(slug) / "creatives.json"

    def qa_file(self, slug: str) -> Path:
        return self.campaign_dir(slug) / "qa.md"

    def report_file(self, slug: str) -> Path:
        return self.campaign_dir(slug) / "report.md"

    def list_campaigns(self) -> list[str]:
        if not self.campaigns_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in self.campaigns_dir.iterdir()
            if p.is_dir() and not p.name.startswith(("_", "."))
        )

    # -- creation ----------------------------------------------------------
    def create(self, *, exist_ok: bool = True) -> list[Path]:
        """Create the directory skeleton. Returns the paths created."""
        if self.root.exists() and not exist_ok:
            raise WorkspaceError(f"{self.root} already exists")
        created: list[Path] = []
        for directory in (
            self.root,
            self.offers_dir,
            self.assets_dir,
            self.campaigns_dir,
            self.reports_dir,
            self.state_dir,
        ):
            if not directory.exists():
                directory.mkdir(parents=True)
                created.append(directory)
        self._write_local_gitignore()
        return created

    def _write_local_gitignore(self) -> None:
        """Ignore the workspace from inside it.

        The repository's own ``.gitignore`` covers ``.meta-ads/``, but a user
        initialising a workspace in *their* project has no such entry. Writing
        one here means the workspace is private by default wherever it is
        created, without editing a file the user owns.
        """
        target = self.root / ".gitignore"
        if target.exists():
            return
        atomic_write(
            target,
            "# Created by 'meta-ads-agent init'.\n"
            "# This workspace holds ad account ids, performance data, campaign\n"
            "# state, and creative assets. It is private by default.\n"
            "#\n"
            "# To version part of it deliberately, delete this file and add\n"
            "# targeted rules to your project's .gitignore instead. Do not\n"
            "# commit reports, exports, or customer audience files.\n"
            "*\n",
        )

    # -- typed IO ----------------------------------------------------------
    def read_yaml(self, path: Path) -> dict[str, Any]:
        """Read YAML with ``safe_load``.

        Never ``yaml.load``: a workspace file could come from anywhere, and
        full-loader YAML can construct arbitrary Python objects.
        """
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise WorkspaceError(f"{path} not found") from exc
        except yaml.YAMLError as exc:
            raise WorkspaceError(f"{path} is not valid YAML: {exc}") from exc
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise WorkspaceError(f"{path} must contain a mapping at the top level")
        return raw

    def read_json(self, path: Path) -> dict[str, Any]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise WorkspaceError(f"{path} not found") from exc
        except json.JSONDecodeError as exc:
            raise WorkspaceError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise WorkspaceError(f"{path} must contain a JSON object")
        return raw

    def write_yaml(self, path: Path, data: dict[str, Any], *, header: str | None = None) -> None:
        body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=88)
        atomic_write(path, f"{header.rstrip()}\n{body}" if header else body)

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        atomic_write(
            path, json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n"
        )


def _json_default(value: object) -> str:
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")
