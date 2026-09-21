"""What is installed where, and how far the last update got.

The version number is written last, on purpose. Everything before it - the
copy, the orphan sweep, the hash check - happens while the state file still
says the old version and carries an ``in_progress`` record. An update killed
half way therefore leaves an installation that *knows* it is half way, rather
than one that claims to be current and is not. That failure, an install
reporting a version it does not actually have on disk, is the whole reason
this file exists.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meta_ads_agent.errors import StateError
from meta_ads_agent.workspace import atomic_write

SCHEMA_VERSION = 1

# A dotfile rather than a directory: a skills directory is scanned by the host
# for skill folders, and we should not add one that is not a skill.
STATE_FILENAME = ".meta-ads-agent-install.json"
BACKUP_DIRNAME = ".meta-ads-agent-backup"
STAGE_DIRNAME = ".meta-ads-agent-stage"

# Anything we create in the target, so the installer can tell its own
# bookkeeping apart from somebody else's skills and never touch the latter.
RESERVED_NAMES = frozenset({STATE_FILENAME, BACKUP_DIRNAME, STAGE_DIRNAME})


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class UpdateInProgress:
    """A marker written before the first byte moves and cleared after the last."""

    from_version: str
    to_version: str
    stage: str
    started_at: str = field(default_factory=_now)
    backup: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "stage": self.stage,
            "started_at": self.started_at,
            "backup": self.backup,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> UpdateInProgress:
        return cls(
            from_version=raw.get("from_version", "unknown"),
            to_version=raw.get("to_version", "unknown"),
            stage=raw.get("stage", "unknown"),
            started_at=raw.get("started_at", "unknown"),
            backup=raw.get("backup"),
        )


@dataclass(slots=True)
class InstallState:
    """The record of one installed payload, kept beside it."""

    root: Path
    version: str | None = None
    digest: str | None = None
    method: str = "unknown"
    installed_at: str | None = None
    updated_at: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    in_progress: UpdateInProgress | None = None
    schema_version: int = SCHEMA_VERSION

    # -- location ----------------------------------------------------------
    @property
    def path(self) -> Path:
        return self.root / STATE_FILENAME

    @property
    def backup_root(self) -> Path:
        return self.root / BACKUP_DIRNAME

    @property
    def stage_root(self) -> Path:
        return self.root / STAGE_DIRNAME

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def interrupted(self) -> bool:
        return self.in_progress is not None

    # -- io ----------------------------------------------------------------
    @classmethod
    def load(cls, root: Path) -> InstallState:
        """Read the record, or return an empty one for a fresh target."""
        state = cls(root=root)
        if not state.path.is_file():
            return state
        try:
            raw = json.loads(state.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(
                f"{state.path} is not valid JSON ({exc}). The installation "
                f"cannot be described. Re-run 'meta-ads-agent install --force' "
                f"to rebuild it; user data in .meta-ads/ is not affected."
            ) from exc
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise StateError(
                f"{state.path} uses install-state schema {raw.get('schema_version')!r}, "
                f"and this CLI understands {SCHEMA_VERSION}. Upgrade the CLI first."
            )
        state.version = raw.get("version")
        state.digest = raw.get("digest")
        state.method = raw.get("method", "unknown")
        state.installed_at = raw.get("installed_at")
        state.updated_at = raw.get("updated_at")
        state.files = dict(raw.get("files") or {})
        progress = raw.get("in_progress")
        state.in_progress = UpdateInProgress.from_dict(progress) if progress else None
        return state

    def save(self) -> None:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "version": self.version,
            "digest": self.digest,
            "method": self.method,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "in_progress": self.in_progress.as_dict() if self.in_progress else None,
            "files": dict(sorted(self.files.items())),
        }
        atomic_write(self.path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    # -- transitions -------------------------------------------------------
    def begin(self, *, to_version: str, stage: str, backup: Path | None = None) -> None:
        """Record that an update has started. Called before anything moves."""
        self.in_progress = UpdateInProgress(
            from_version=self.version or "none",
            to_version=to_version,
            stage=stage,
            backup=str(backup) if backup else None,
        )
        self.save()

    def advance(self, stage: str) -> None:
        if self.in_progress is None:  # pragma: no cover - defensive
            raise StateError("advance() called with no update in progress")
        self.in_progress.stage = stage
        self.save()

    def finish(self, *, version: str, digest: str, files: dict[str, str], method: str) -> None:
        """Declare the installation current. The last thing an update does."""
        self.version = version
        self.digest = digest
        self.files = dict(files)
        self.method = method
        self.updated_at = _now()
        if self.installed_at is None:
            self.installed_at = self.updated_at
        self.in_progress = None
        self.save()

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "version": self.version,
            "digest": self.digest,
            "method": self.method,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "file_count": len(self.files),
            "in_progress": self.in_progress.as_dict() if self.in_progress else None,
        }
