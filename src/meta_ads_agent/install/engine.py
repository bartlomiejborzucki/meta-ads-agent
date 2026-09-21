"""Plan and apply an install or an upgrade.

The shape of the operation is a diff between two lists, not a walk over the
files that happen to be there. A release that adds a directory, adds a
script, renames a reference or drops a file produces exactly the same four
buckets - added, updated, unchanged, removed - and none of them is a special
case. Copying "the files that already existed" is the bug this replaces.

Ordering is chosen so that an interruption is always recoverable:

    backup -> stage -> verify staged -> swap -> verify installed -> record

The version is recorded in the final step. Until then the installation
describes itself as mid-update and says which stage it stopped at.
"""

from __future__ import annotations

import datetime as _dt
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meta_ads_agent.errors import StateError
from meta_ads_agent.install.manifest import (
    ReleaseManifest,
    VerificationReport,
    sha256_file,
    verify_tree,
)
from meta_ads_agent.install.state import RESERVED_NAMES, STATE_FILENAME, InstallState
from meta_ads_agent.install.targets import InstallTarget

# Enough history to undo a bad upgrade and the one before it, without turning
# the skills directory into an archive.
BACKUP_RETENTION = 3


@dataclass(slots=True)
class InstallPlan:
    """What an install would do, before it does any of it."""

    target: InstallTarget
    manifest: ReleaseManifest
    state: InstallState
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    removed_skills: list[str] = field(default_factory=list)
    resuming: bool = False
    # Snapshotted, because ``state`` is the live object the apply step
    # mutates. Reading it back afterwards would report every fresh install as
    # a repair - the plan describes the decision, not the outcome.
    from_version: str | None = None

    @property
    def fresh(self) -> bool:
        return self.from_version is None

    @property
    def changes(self) -> int:
        return len(self.added) + len(self.updated) + len(self.removed) + len(self.removed_skills)

    @property
    def action(self) -> str:
        if self.resuming:
            return "resume"
        if self.fresh:
            return "install"
        if self.changes == 0:
            return "up-to-date"
        if self.from_version == self.manifest.version:
            return "repair"
        return "upgrade"

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "from_version": self.from_version,
            "to_version": self.manifest.version,
            "target": self.target.as_dict(),
            "added": sorted(self.added),
            "updated": sorted(self.updated),
            "removed": sorted(self.removed),
            "removed_skills": sorted(self.removed_skills),
            "unchanged": len(self.unchanged),
            "resuming": self.resuming,
        }


@dataclass(slots=True)
class InstallResult:
    plan: InstallPlan
    verification: VerificationReport
    backup: Path | None

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.plan.as_dict(),
            "verification": self.verification.as_dict(),
            "backup": str(self.backup) if self.backup else None,
        }


def plan_install(
    manifest: ReleaseManifest,
    source_root: Path,
    target: InstallTarget,
    *,
    force: bool = False,
) -> InstallPlan:
    """Diff the release against what is on disk.

    The comparison is by content hash rather than by timestamp or size. A
    hand-edited skill and a half-copied one both differ from the release, and
    both are things the user wants to be told about.
    """
    state = InstallState.load(target.root)
    plan = InstallPlan(
        target=target,
        manifest=manifest,
        state=state,
        resuming=state.interrupted,
        from_version=state.version,
    )

    expected = manifest.by_path()
    for path, entry in expected.items():
        installed = target.root / path
        if not installed.is_file():
            plan.added.append(path)
        elif force or sha256_file(installed) != entry.sha256:
            plan.updated.append(path)
        else:
            plan.unchanged.append(path)

    # Leftovers, in two flavours: a file the new release dropped, and a whole
    # skill it dropped. Both are found by looking at what is installed, not by
    # remembering what we put there - a previous install may have been done by
    # a different version of this code, or by hand.
    known_skills = set(manifest.skills)
    for child in _iter_installed_children(target.root):
        if child.name in known_skills:
            continue
        if _looks_like_our_skill(child):
            plan.removed_skills.append(child.name)

    for skill in known_skills:
        skill_dir = target.root / skill
        if not skill_dir.is_dir():
            continue
        for found in skill_dir.rglob("*"):
            if found.is_file():
                relative = found.relative_to(target.root).as_posix()
                if relative not in expected:
                    plan.removed.append(relative)

    return plan


def _iter_installed_children(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.name not in RESERVED_NAMES)


def _looks_like_our_skill(path: Path) -> bool:
    """Only ever delete a directory that is one of ours.

    A skills directory belongs to the user and holds other people's skills.
    The name prefix plus a SKILL.md naming itself is a narrow enough test that
    an unrelated directory cannot be caught by it.
    """
    if not path.is_dir() or not path.name.startswith("meta-ads-"):
        return False
    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        return False
    try:
        head = skill_md.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:  # pragma: no cover - unreadable file, leave it alone
        return False
    return f"name: {path.name}" in head


def apply_install(
    plan: InstallPlan,
    source_root: Path,
    *,
    method: str = "sync",
    backup: bool = True,
) -> InstallResult:
    """Carry out the plan. Safe to re-run, and safe to interrupt."""
    target = plan.target
    manifest = plan.manifest
    state = plan.state
    target.root.mkdir(parents=True, exist_ok=True)

    # A resumed update keeps the backup the interrupted run took. Taking a new
    # one now would archive the half-installed tree and lose the good one -
    # the single most damaging thing a retry could do.
    existing_backup = _resume_backup(state)
    backup_dir = existing_backup
    if backup_dir is None and backup and _anything_installed(target.root, manifest):
        backup_dir = _backup_path(state)

    # Snapshotted before the in-progress marker is written. A backup that
    # contains the marker restores an installation that still believes it is
    # mid-update, which makes rollback useless exactly when it is needed.
    pre_update_state = state.path.read_bytes() if state.path.is_file() else None

    state.begin(to_version=manifest.version, stage="backup", backup=backup_dir)
    if backup_dir is not None and not backup_dir.exists():
        _take_backup(target.root, backup_dir, pre_update_state, set(manifest.skills))
        _prune_backups(state)

    state.advance("stage")
    stage_root = state.stage_root
    if stage_root.exists():
        shutil.rmtree(stage_root)
    _stage_payload(manifest, source_root, stage_root)

    staged = verify_tree(manifest, stage_root)
    if not staged.complete:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise StateError(
            "the staged payload does not match the release manifest "
            f"(missing {len(staged.missing)}, modified {len(staged.modified)}). "
            "Nothing was changed in the installation."
        )

    state.advance("swap")
    _swap_in(stage_root, target.root, manifest, plan)
    shutil.rmtree(stage_root, ignore_errors=True)

    state.advance("verify")
    verification = verify_tree(manifest, target.root)
    if not verification.complete:
        raise StateError(
            "the installation does not match the release manifest after copying: "
            f"{len(verification.missing)} missing, {len(verification.modified)} modified, "
            f"{len(verification.orphaned)} left over. The recorded version has not been "
            "advanced. Re-run the upgrade, or roll back with --rollback."
        )

    state.finish(
        version=manifest.version,
        digest=manifest.digest,
        files={entry.path: entry.sha256 for entry in manifest.sorted_entries()},
        method=method,
    )
    return InstallResult(plan=plan, verification=verification, backup=backup_dir)


def _anything_installed(root: Path, manifest: ReleaseManifest) -> bool:
    return any((root / skill).is_dir() for skill in manifest.skills)


def _backup_path(state: InstallState) -> Path:
    """A directory that does not exist yet.

    Second-resolution timestamps collide when two upgrades run back to back -
    in a test suite constantly, on a real machine rarely, and a collision
    means copying into a directory that already holds a different backup.
    """
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    base = state.backup_root / f"{stamp}-{state.version or 'unversioned'}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}.{suffix}")
        suffix += 1
    return candidate


def _resume_backup(state: InstallState) -> Path | None:
    if state.in_progress and state.in_progress.backup:
        candidate = Path(state.in_progress.backup)
        if candidate.exists():
            return candidate
    return None


def _take_backup(
    root: Path, destination: Path, pre_update_state: bytes | None, known: set[str]
) -> None:
    """Archive every directory the restore will have to put back.

    Membership is by name as well as by shape. A skill whose SKILL.md is
    damaged still fails the shape test, and skipping it would produce a
    backup that looks complete and restores an installation with a hole in
    it - which is the failure a backup exists to prevent.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for child in _iter_installed_children(root):
        if not child.is_dir():
            continue
        if child.name not in known and not _looks_like_our_skill(child):
            continue
        shutil.copytree(child, destination / child.name, symlinks=True, dirs_exist_ok=True)
    if pre_update_state is not None:
        (destination / STATE_FILENAME).write_bytes(pre_update_state)


def _prune_backups(state: InstallState) -> None:
    if not state.backup_root.is_dir():
        return
    backups = sorted((p for p in state.backup_root.iterdir() if p.is_dir()), reverse=True)
    for stale in backups[BACKUP_RETENTION:]:
        shutil.rmtree(stale, ignore_errors=True)


def _stage_payload(manifest: ReleaseManifest, source_root: Path, stage_root: Path) -> None:
    """Build the complete new tree beside the old one, then check it.

    Staging is what makes "the new release added a file" and "the new release
    added a whole directory of scripts" the same operation: the stage is built
    from the manifest, so it contains whatever the manifest lists.
    """
    for entry in manifest.sorted_entries():
        source = source_root / entry.path
        if not source.is_file():
            raise StateError(
                f"{entry.path} is listed in the release manifest but missing from "
                f"the source at {source_root}. The package is incomplete; refusing "
                "to install a partial payload."
            )
        destination = stage_root / entry.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if entry.executable:
            destination.chmod(destination.stat().st_mode | 0o111)


def _swap_in(
    stage_root: Path, target_root: Path, manifest: ReleaseManifest, plan: InstallPlan
) -> None:
    for skill in manifest.skills:
        staged = stage_root / skill
        live = target_root / skill
        if live.exists():
            shutil.rmtree(live)
        shutil.move(str(staged), str(live))

    for orphan_skill in plan.removed_skills:
        stale = target_root / orphan_skill
        if stale.is_dir() and _looks_like_our_skill(stale):
            shutil.rmtree(stale)


def rollback(target: InstallTarget) -> Path:
    """Restore the most recent backup and forget the interrupted update."""
    state = InstallState.load(target.root)
    candidate = _resume_backup(state)
    if candidate is None:
        backups = (
            sorted((p for p in state.backup_root.iterdir() if p.is_dir()), reverse=True)
            if state.backup_root.is_dir()
            else []
        )
        if not backups:
            raise StateError(
                f"no backup to roll back to under {state.backup_root}. "
                "Re-run the install to rebuild the payload from the package."
            )
        candidate = backups[0]

    # Clear out exactly what the backup is about to put back, plus anything
    # still recognisable as ours. Anything else in the directory belongs to
    # somebody else and is left where it is.
    restoring = {saved.name for saved in candidate.iterdir() if saved.is_dir()}
    recorded = {path.split("/", 1)[0] for path in state.files}
    for child in _iter_installed_children(target.root):
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name in restoring or child.name in recorded or _looks_like_our_skill(child):
            shutil.rmtree(child)
    for saved in sorted(candidate.iterdir()):
        if saved.is_dir():
            shutil.copytree(saved, target.root / saved.name, symlinks=True)
    saved_state = candidate / STATE_FILENAME
    if saved_state.is_file():
        shutil.copy2(saved_state, state.path)
    else:  # pragma: no cover - a backup from before state files existed
        state.in_progress = None
        state.save()

    shutil.rmtree(state.stage_root, ignore_errors=True)
    return candidate
