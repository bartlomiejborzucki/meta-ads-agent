"""Versioned, once-only migrations of the user's workspace.

Deliberately separate from the payload update. Replacing skill files is
replacing code we own; changing anything under ``.meta-ads/`` is editing the
user's work - their brand voice, their offer briefs, their campaign plans and
the state that says which objects exist on Meta. Those two operations deserve
different rules, and merging them is how an upgrade eats a plan.

The rules here:

* every migration has an id, and the ledger records it the moment it succeeds;
* every migration can also *detect* whether its effect is already present, so
  a lost ledger does not cause it to run twice;
* the workspace is backed up before the first migration that changes anything;
* a failure stops the run - later migrations are not attempted on a workspace
  that an earlier one left half-changed;
* nothing here reads a token, contacts Meta, or touches a campaign.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from meta_ads_agent.errors import StateError
from meta_ads_agent.install.manifest import MigrationRef, sha256_file
from meta_ads_agent.workspace import Workspace, atomic_write

SCHEMA_VERSION = 1
LEDGER_FILENAME = ".migrations.json"
BACKUP_DIRNAME = ".backups"

# Never copied into a backup: the backups themselves, and caches.
_BACKUP_EXCLUDE = frozenset({BACKUP_DIRNAME, "__pycache__"})


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class MigrationLedger:
    """Which migrations have run against this workspace."""

    workspace: Workspace
    applied: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.workspace.root / LEDGER_FILENAME

    @classmethod
    def load(cls, workspace: Workspace) -> MigrationLedger:
        ledger = cls(workspace=workspace)
        if not ledger.path.is_file():
            return ledger
        try:
            raw = json.loads(ledger.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(
                f"{ledger.path} is not valid JSON ({exc}). Delete it to have every "
                "migration re-check itself - each one detects whether its effect is "
                "already present, so nothing will be applied twice."
            ) from exc
        for record in raw.get("applied", []):
            ledger.applied[record["id"]] = record
        return ledger

    def has(self, migration_id: str) -> bool:
        return migration_id in self.applied

    def record(self, migration_id: str, *, version: str, outcome: str, detail: str = "") -> None:
        self.applied[migration_id] = {
            "id": migration_id,
            "at": _now(),
            "version": version,
            "outcome": outcome,
            "detail": detail,
        }
        self.save()

    def save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "applied": [self.applied[key] for key in sorted(self.applied)],
        }
        atomic_write(self.path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Migration protocol and registry
# ---------------------------------------------------------------------------
class Migration(Protocol):
    # Read-only properties rather than attributes: a dataclass with a plain
    # field and one with a computed property both have to satisfy this, and
    # a settable attribute in a Protocol excludes the second.
    @property
    def id(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def introduced_in(self) -> str: ...

    @property
    def changes_user_data(self) -> bool: ...

    def is_satisfied(self, workspace: Workspace) -> bool:
        """True when the effect is already present, ledger or no ledger."""

    def apply(self, workspace: Workspace) -> str:
        """Make the change. Returns one line describing what happened."""


@dataclass(frozen=True, slots=True)
class WorkspaceGitignore:
    """Give an older workspace the ``.gitignore`` that makes it private.

    ``init`` has written one since the first release, but a workspace created
    by hand - or copied out of an example - may not have it, and the
    consequence is an ad account id and a performance export in somebody's
    git history. ``doctor`` warns about this already; the migration is what
    fixes it without asking the user to re-run ``init`` over their own files.
    """

    id: str = "0001-workspace-gitignore"
    description: str = "add the private-by-default .gitignore inside .meta-ads/"
    introduced_in: str = "0.2.0"
    changes_user_data: bool = False

    def is_satisfied(self, workspace: Workspace) -> bool:
        return (workspace.root / ".gitignore").is_file()

    def apply(self, workspace: Workspace) -> str:
        workspace._write_local_gitignore()
        return f"wrote {workspace.root / '.gitignore'}"


REGISTRY: tuple[Migration, ...] = (WorkspaceGitignore(),)


# ---------------------------------------------------------------------------
# Script-backed migrations
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ScriptMigration:
    """A migration carried out by a script shipped inside the payload.

    A release that adds a script to the repository has done nothing useful by
    itself - someone has to run it. Naming it in the manifest is what turns it
    into a step the updater knows about, and pinning its SHA-256 there is what
    makes running it defensible: the bytes executed are the bytes the release
    declared, not whatever is on disk by the time we get there.

    It still does not run unless the user allows it. Downloading code and
    executing it because a JSON file said to is not a trust model.
    """

    ref: MigrationRef
    payload_root: Path
    changes_user_data: bool = True

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def description(self) -> str:
        return self.ref.description

    @property
    def introduced_in(self) -> str:
        return self.ref.introduced_in

    @property
    def script_path(self) -> Path:
        return self.payload_root / (self.ref.script or "")

    def is_satisfied(self, workspace: Workspace) -> bool:
        """Ask the script itself, so a lost ledger cannot cause a second run."""
        result = self._run(workspace, "--check")
        # 0 = already applied, 1 = work to do. Anything else is a broken
        # script, and a broken check must not read as "already done".
        if result.returncode not in (0, 1):
            raise StateError(
                f"migration {self.id}: --check exited {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()[:400]}"
            )
        return result.returncode == 0

    def apply(self, workspace: Workspace) -> str:
        result = self._run(workspace, "--apply")
        if result.returncode != 0:
            raise StateError(
                f"migration {self.id} failed ({result.returncode}): "
                f"{(result.stderr or result.stdout).strip()[:400]}"
            )
        return (result.stdout or "").strip().splitlines()[-1] if result.stdout.strip() else "done"

    def verify_hash(self) -> None:
        if not self.script_path.is_file():
            raise StateError(
                f"migration {self.id} names {self.ref.script}, which is not in the "
                "installed payload. The installation is incomplete - run "
                "'meta-ads-agent install --force' before migrating."
            )
        actual = sha256_file(self.script_path)
        if actual != self.ref.script_sha256:
            raise StateError(
                f"migration {self.id}: {self.ref.script} does not match the hash in "
                "the release manifest. Refusing to execute it."
            )

    def _run(self, workspace: Workspace, flag: str) -> subprocess.CompletedProcess[str]:
        self.verify_hash()
        return subprocess.run(  # noqa: S603 - argv is fixed; the path is hash-pinned
            [sys.executable, str(self.script_path), flag, "--workspace", str(workspace.root)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            # No inherited Meta credentials: a data migration has no business
            # reading a token, and cannot leak one it never had.
            env=_scrubbed_env(),
        )


def _scrubbed_env() -> dict[str, str]:
    import os

    blocked = {
        "META_ACCESS_TOKEN",
        "META_APP_SECRET",
        "META_APP_ID",
        "META_AD_ACCOUNT_ID",
    }
    return {k: v for k, v in os.environ.items() if k not in blocked}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class MigrationOutcome:
    id: str
    status: str  # applied | already-satisfied | skipped-needs-consent | pending
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status, "detail": self.detail}


@dataclass(slots=True)
class MigrationRun:
    outcomes: list[MigrationOutcome] = field(default_factory=list)
    backup: Path | None = None
    failed: str | None = None

    @property
    def pending(self) -> list[str]:
        return [o.id for o in self.outcomes if o.status in ("pending", "skipped-needs-consent")]

    @property
    def applied(self) -> list[str]:
        return [o.id for o in self.outcomes if o.status == "applied"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "pending": self.pending,
            "backup": str(self.backup) if self.backup else None,
            "failed": self.failed,
            "outcomes": [o.as_dict() for o in self.outcomes],
        }


def collect_migrations(
    *, payload_root: Path | None = None, refs: tuple[MigrationRef, ...] = ()
) -> list[Migration]:
    """Built-ins first, then script-backed ones, in declared order."""
    migrations: list[Migration] = list(REGISTRY)
    for ref in refs:
        if ref.script and payload_root is not None:
            migrations.append(ScriptMigration(ref=ref, payload_root=payload_root))
    return migrations


def backup_workspace(workspace: Workspace, label: str) -> Path:
    """Copy the workspace aside before anything writes to it."""
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    base = workspace.root / BACKUP_DIRNAME / f"{stamp}-pre-{label}"
    # Two migrations in the same second would otherwise copy into one
    # directory, and the second copy would fail on the first one's files.
    destination = base
    suffix = 1
    while destination.exists():
        destination = Path(f"{base}.{suffix}")
        suffix += 1
    destination.mkdir(parents=True, exist_ok=True)
    for child in sorted(workspace.root.iterdir()):
        if child.name in _BACKUP_EXCLUDE:
            continue
        if child.is_dir():
            shutil.copytree(child, destination / child.name, symlinks=True)
        else:
            shutil.copy2(child, destination / child.name)
    return destination


def run_migrations(
    workspace: Workspace,
    migrations: list[Migration],
    *,
    version: str,
    allow_scripts: bool = False,
    dry_run: bool = False,
) -> MigrationRun:
    """Apply what is outstanding, once each, stopping at the first failure."""
    if not workspace.exists:
        raise StateError(
            f"no workspace at {workspace.root}. Nothing to migrate - "
            "'meta-ads-agent init' creates one at the current release's schema."
        )

    ledger = MigrationLedger.load(workspace)
    run = MigrationRun()
    backup: Path | None = None

    for migration in migrations:
        if ledger.has(migration.id):
            run.outcomes.append(
                MigrationOutcome(migration.id, "already-satisfied", "recorded in the ledger")
            )
            continue

        if isinstance(migration, ScriptMigration) and not allow_scripts:
            run.outcomes.append(
                MigrationOutcome(
                    migration.id,
                    "skipped-needs-consent",
                    f"runs {migration.ref.script} from the payload; re-run with "
                    "--allow-migration-scripts to let it execute",
                )
            )
            continue

        try:
            if migration.is_satisfied(workspace):
                if not dry_run:
                    ledger.record(
                        migration.id,
                        version=version,
                        outcome="already-satisfied",
                        detail="effect was already present",
                    )
                run.outcomes.append(
                    MigrationOutcome(migration.id, "already-satisfied", "effect already present")
                )
                continue

            if dry_run:
                run.outcomes.append(
                    MigrationOutcome(migration.id, "pending", migration.description)
                )
                continue

            if backup is None and getattr(migration, "changes_user_data", True):
                backup = backup_workspace(workspace, migration.id)
                run.backup = backup

            detail = migration.apply(workspace)
            ledger.record(migration.id, version=version, outcome="applied", detail=detail)
            run.outcomes.append(MigrationOutcome(migration.id, "applied", detail))
        except Exception as exc:
            run.failed = f"{migration.id}: {exc}"
            run.outcomes.append(MigrationOutcome(migration.id, "pending", str(exc)))
            break

    return run
