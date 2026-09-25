"""Installing and upgrading: the cases where an update quietly loses files.

The failure being designed against is specific. An updater that copies "the
files that are already there" advances the version number and leaves the new
ones behind, so the installation reports a release it is not running. Every
test here is a shape of that bug: a new file, a new directory, a new script,
a deleted file, a half-finished copy, a migration that ran twice.

Fixture releases are built in temporary directories rather than pulled from
git history, so each test states exactly which difference it is about. The
real payload is exercised too - a synthetic release that passes proves the
engine, not the package.

Nothing here contacts Meta, and no test needs credentials.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import posix_only
from meta_ads_agent import __version__
from meta_ads_agent.errors import StateError
from meta_ads_agent.install import packaged
from meta_ads_agent.install.engine import apply_install, plan_install, rollback
from meta_ads_agent.install.manifest import (
    MigrationRef,
    build_manifest,
    load_manifest,
    verify_tree,
)
from meta_ads_agent.install.migrations import (
    MigrationLedger,
    collect_migrations,
    run_migrations,
)
from meta_ads_agent.install.state import InstallState
from meta_ads_agent.install.targets import InstallTarget, resolve_target
from meta_ads_agent.workspace import Workspace

REPO = Path(__file__).resolve().parents[1]

SKILL_TEMPLATE = """---
name: {name}
description: >-
  Fixture skill for the upgrade tests. Use when a test needs a skill.
---

# {name}

{body}
"""

# A migration script of the kind a future release might add: it does one
# small thing to the workspace, can say whether it has already been done, and
# never touches an ad account.
MIGRATION_SCRIPT = '''#!/usr/bin/env python3
"""Fixture migration: stamp the workspace with a schema marker."""
import argparse, json, pathlib, sys

MARKER = "schema-2.json"

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
parser.add_argument("--apply", action="store_true")
parser.add_argument("--workspace", required=True)
args = parser.parse_args()

target = pathlib.Path(args.workspace) / MARKER
if args.check:
    sys.exit(0 if target.is_file() else 1)

target.write_text(json.dumps({"schema": 2}), encoding="utf-8")
print(f"stamped {target}")
'''


# ---------------------------------------------------------------------------
# Fixture releases
# ---------------------------------------------------------------------------
def make_release(
    base: Path,
    version: str,
    files: dict[str, str],
    *,
    migrations: tuple[MigrationRef, ...] = (),
    executable: tuple[str, ...] = (),
):
    """Write a payload and describe it. Returns (payload_root, manifest)."""
    payload = base / "skills"
    if payload.exists():
        import shutil

        shutil.rmtree(payload)
    for relative, content in files.items():
        path = payload / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for relative in executable:
        path = payload / relative
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return payload, build_manifest(base, version, migrations=migrations)


def v1_files() -> dict[str, str]:
    return {
        "meta-ads-core/SKILL.md": SKILL_TEMPLATE.format(name="meta-ads-core", body="core v1"),
        "meta-ads-core/references/routing.md": "# routing\n\nv1\n",
        "meta-ads-core/references/retired.md": "# retired\n\nremoved in v2\n",
        "meta-ads-report/SKILL.md": SKILL_TEMPLATE.format(name="meta-ads-report", body="report v1"),
    }


def v2_files() -> dict[str, str]:
    return {
        # changed
        "meta-ads-core/SKILL.md": SKILL_TEMPLATE.format(name="meta-ads-core", body="core v2"),
        # unchanged
        "meta-ads-core/references/routing.md": "# routing\n\nv1\n",
        # retired.md is gone
        # new file in a new directory
        "meta-ads-core/assets/plan-template.yaml": "schema_version: 1\n",
        # new script, in a directory that did not exist in v1
        "meta-ads-core/scripts/migrate_schema.py": MIGRATION_SCRIPT,
        "meta-ads-report/SKILL.md": SKILL_TEMPLATE.format(name="meta-ads-report", body="report v2"),
        # a whole new skill
        "meta-ads-audit/SKILL.md": SKILL_TEMPLATE.format(name="meta-ads-audit", body="audit v2"),
    }


@pytest.fixture
def target(tmp_path: Path) -> InstallTarget:
    return resolve_target("path", path=tmp_path / "skills")


def install(manifest, source: Path, target: InstallTarget, **kwargs):
    plan = plan_install(manifest, source, target, force=kwargs.pop("force", False))
    return apply_install(plan, source, **kwargs)


# ---------------------------------------------------------------------------
# Clean install
# ---------------------------------------------------------------------------
class TestCleanInstall:
    def test_the_real_payload_installs_and_verifies(self, target: InstallTarget) -> None:
        manifest = packaged.release_manifest()
        result = install(manifest, packaged.payload_source(), target)
        assert result.verification.complete
        assert len(result.plan.added) == len(manifest.entries)
        state = InstallState.load(target.root)
        assert state.version == manifest.version
        assert state.in_progress is None

    def test_every_skill_arrives_whole(self, target: InstallTarget) -> None:
        manifest = packaged.release_manifest()
        install(manifest, packaged.payload_source(), target)
        for entry in manifest.entries:
            installed = target.root / entry.path
            assert installed.is_file(), f"{entry.path} did not install"
            assert installed.stat().st_size == entry.size

    def test_a_fresh_install_reports_itself_as_an_install(self, target: InstallTarget) -> None:
        manifest = packaged.release_manifest()
        result = install(manifest, packaged.payload_source(), target)
        assert result.plan.action == "install"
        assert result.plan.from_version is None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------
class TestUpgrade:
    @pytest.fixture
    def upgraded(self, tmp_path: Path, target: InstallTarget):
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())
        result = install(m2, new, target)
        return result, m2

    def test_new_files_are_installed(self, upgraded, target: InstallTarget) -> None:
        result, _ = upgraded
        assert "meta-ads-core/assets/plan-template.yaml" in result.plan.added
        assert (target.root / "meta-ads-core" / "assets" / "plan-template.yaml").is_file()

    def test_a_new_directory_is_created(self, upgraded, target: InstallTarget) -> None:
        assert (target.root / "meta-ads-core" / "scripts").is_dir()

    def test_a_whole_new_skill_arrives(self, upgraded, target: InstallTarget) -> None:
        assert (target.root / "meta-ads-audit" / "SKILL.md").is_file()

    def test_changed_files_are_replaced(self, upgraded, target: InstallTarget) -> None:
        text = (target.root / "meta-ads-core" / "SKILL.md").read_text(encoding="utf-8")
        assert "core v2" in text and "core v1" not in text

    def test_a_removed_file_does_not_survive(self, upgraded, target: InstallTarget) -> None:
        result, _ = upgraded
        assert "meta-ads-core/references/retired.md" in result.plan.removed
        assert not (target.root / "meta-ads-core" / "references" / "retired.md").exists()

    def test_unchanged_files_are_left_alone(self, upgraded) -> None:
        result, _ = upgraded
        assert "meta-ads-core/references/routing.md" in result.plan.unchanged

    def test_the_manifest_change_is_recorded(self, upgraded, target: InstallTarget) -> None:
        _, m2 = upgraded
        state = InstallState.load(target.root)
        assert state.version == "0.2.0"
        assert state.digest == m2.digest
        assert len(state.files) == len(m2.entries)

    def test_the_result_verifies_against_the_new_manifest(self, upgraded, target) -> None:
        _, m2 = upgraded
        assert verify_tree(m2, target.root).complete

    def test_rerunning_the_upgrade_is_a_no_op(self, upgraded, tmp_path, target) -> None:
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())
        plan = plan_install(m2, new, target)
        assert plan.action == "up-to-date"
        assert plan.changes == 0


class TestNewScriptBetweenVersions:
    """Shipping a script is not the same as the script having run."""

    @pytest.fixture
    def with_script(self, tmp_path: Path, target: InstallTarget):
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        ref = MigrationRef(
            id="0002-fixture-schema",
            description="stamp the workspace with a schema marker",
            introduced_in="0.2.0",
            script="meta-ads-core/scripts/migrate_schema.py",
        )
        new, m2 = make_release(
            tmp_path / "v2",
            "0.2.0",
            v2_files(),
            migrations=(ref,),
            executable=("meta-ads-core/scripts/migrate_schema.py",),
        )
        install(m2, new, target)
        return m2

    def test_the_script_is_present_after_the_upgrade(self, with_script, target) -> None:
        script = target.root / "meta-ads-core" / "scripts" / "migrate_schema.py"
        assert script.is_file()
        assert "stamped" in script.read_text(encoding="utf-8")

    @posix_only
    def test_the_script_keeps_its_executable_bit(self, with_script, target) -> None:
        script = target.root / "meta-ads-core" / "scripts" / "migrate_schema.py"
        assert script.stat().st_mode & stat.S_IXUSR

    def test_the_installed_script_actually_runs(self, with_script, target, tmp_path) -> None:
        workspace = Workspace.at(tmp_path / "proj" / ".meta-ads")
        workspace.create()
        script = target.root / "meta-ads-core" / "scripts" / "migrate_schema.py"
        result = subprocess.run(  # noqa: S603 - the script under test, by absolute path
            [sys.executable, str(script), "--apply", "--workspace", str(workspace.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert (workspace.root / "schema-2.json").is_file()

    def test_the_manifest_pins_the_scripts_hash(self, with_script) -> None:
        ref = next(m for m in with_script.migrations if m.script)
        assert ref.script_sha256 and len(ref.script_sha256) == 64

    def test_the_migration_is_reported_rather_than_run_without_consent(
        self, with_script, target, tmp_path
    ) -> None:
        workspace = Workspace.at(tmp_path / "proj" / ".meta-ads")
        workspace.create()
        migrations = collect_migrations(payload_root=target.root, refs=with_script.migrations)
        run = run_migrations(workspace, migrations, version="0.2.0", allow_scripts=False)
        outcome = next(o for o in run.outcomes if o.id == "0002-fixture-schema")
        assert outcome.status == "skipped-needs-consent"
        assert "--allow-migration-scripts" in outcome.detail
        assert not (workspace.root / "schema-2.json").exists()

    def test_with_consent_it_runs_once_and_only_once(self, with_script, target, tmp_path) -> None:
        workspace = Workspace.at(tmp_path / "proj" / ".meta-ads")
        workspace.create()
        migrations = collect_migrations(payload_root=target.root, refs=with_script.migrations)

        first = run_migrations(workspace, migrations, version="0.2.0", allow_scripts=True)
        assert "0002-fixture-schema" in first.applied
        marker = workspace.root / "schema-2.json"
        assert marker.is_file()
        stamped_at = marker.stat().st_mtime_ns

        second = run_migrations(workspace, migrations, version="0.2.0", allow_scripts=True)
        assert second.applied == []
        assert marker.stat().st_mtime_ns == stamped_at

    def test_a_tampered_script_is_refused(self, with_script, target, tmp_path) -> None:
        script = target.root / "meta-ads-core" / "scripts" / "migrate_schema.py"
        script.write_text("print('something else')\n", encoding="utf-8")
        workspace = Workspace.at(tmp_path / "proj" / ".meta-ads")
        workspace.create()
        migrations = collect_migrations(payload_root=target.root, refs=with_script.migrations)
        run = run_migrations(workspace, migrations, version="0.2.0", allow_scripts=True)
        assert run.failed and "does not match the hash" in run.failed


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
class TestMigrations:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Workspace:
        ws = Workspace.at(tmp_path / "proj" / ".meta-ads")
        ws.create()
        return ws

    def test_a_builtin_migration_runs_once(self, workspace: Workspace) -> None:
        (workspace.root / ".gitignore").unlink()
        migrations = collect_migrations()
        first = run_migrations(workspace, migrations, version=__version__)
        assert "0001-workspace-gitignore" in first.applied
        assert (workspace.root / ".gitignore").is_file()

        second = run_migrations(workspace, migrations, version=__version__)
        assert second.applied == []

    def test_a_lost_ledger_does_not_cause_a_second_run(self, workspace: Workspace) -> None:
        """Detection, not just bookkeeping. A ledger can be deleted."""
        migrations = collect_migrations()
        run_migrations(workspace, migrations, version=__version__)
        ledger_file = workspace.root / ".migrations.json"
        content = (workspace.root / ".gitignore").read_text(encoding="utf-8")
        ledger_file.unlink()

        again = run_migrations(workspace, migrations, version=__version__)
        statuses = {o.id: o.status for o in again.outcomes}
        assert statuses["0001-workspace-gitignore"] == "already-satisfied"
        assert (workspace.root / ".gitignore").read_text(encoding="utf-8") == content

    def test_the_ledger_records_what_ran(self, workspace: Workspace) -> None:
        (workspace.root / ".gitignore").unlink()
        run_migrations(workspace, collect_migrations(), version=__version__)
        ledger = MigrationLedger.load(workspace)
        assert ledger.has("0001-workspace-gitignore")
        assert ledger.applied["0001-workspace-gitignore"]["version"] == __version__

    def test_a_dry_run_changes_nothing(self, workspace: Workspace) -> None:
        (workspace.root / ".gitignore").unlink()
        run = run_migrations(workspace, collect_migrations(), version="x", dry_run=True)
        assert run.pending == ["0001-workspace-gitignore"]
        assert not (workspace.root / ".gitignore").exists()
        assert not (workspace.root / ".migrations.json").exists()

    def test_a_failing_migration_stops_the_run(self, workspace: Workspace, tmp_path) -> None:
        class Boom:
            id = "9999-boom"
            description = "always fails"
            introduced_in = "0.2.0"
            changes_user_data = True

            def is_satisfied(self, workspace: Workspace) -> bool:
                return False

            def apply(self, workspace: Workspace) -> str:
                raise RuntimeError("nope")

        class Later:
            id = "9999-later"
            description = "should not be reached"
            introduced_in = "0.2.0"
            changes_user_data = True

            def is_satisfied(self, workspace: Workspace) -> bool:  # pragma: no cover
                raise AssertionError("must not be consulted after a failure")

            def apply(self, workspace: Workspace) -> str:  # pragma: no cover
                raise AssertionError("must not run after a failure")

        run = run_migrations(workspace, [Boom(), Later()], version="0.2.0")
        assert run.failed and "9999-boom" in run.failed
        assert "9999-later" not in {o.id for o in run.outcomes}


class TestUserDataIsNotTouched:
    """An upgrade replaces our files. It has no business near theirs."""

    def _workspace_with_content(self, tmp_path: Path) -> tuple[Workspace, dict[str, str]]:
        ws = Workspace.at(tmp_path / "proj" / ".meta-ads")
        ws.create()
        content = {
            "brand.yaml": "name: Acme\nprofile: standard\n",
            "voice.md": "Plain, concrete, no exclamation marks.\n",
            "offers/webinar.yaml": "name: webinar\naudience: analysts\n",
            "campaigns/acme/plan.yaml": "slug: acme\n",
            "campaigns/acme/state.json": '{"stage": "ads_created"}\n',
            "campaigns/acme/qa.md": "# QA\nlooks fine\n",
            "assets/manifest.json": '{"fingerprints": {}}\n',
            "actions.jsonl": '{"operation": "read"}\n',
        }
        for relative, text in content.items():
            path = ws.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return ws, content

    def test_an_upgrade_leaves_every_workspace_file_byte_identical(
        self, tmp_path: Path, target: InstallTarget
    ) -> None:
        workspace, content = self._workspace_with_content(tmp_path)
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())
        install(m2, new, target)

        for relative, text in content.items():
            assert (workspace.root / relative).read_text(encoding="utf-8") == text

    def test_a_migration_backs_the_workspace_up_before_changing_it(self, tmp_path: Path) -> None:
        workspace, content = self._workspace_with_content(tmp_path)

        class TouchesData:
            id = "9999-touches-data"
            description = "rewrites brand.yaml"
            introduced_in = "0.2.0"
            changes_user_data = True

            def is_satisfied(self, workspace: Workspace) -> bool:
                return "migrated" in (workspace.root / "brand.yaml").read_text(encoding="utf-8")

            def apply(self, workspace: Workspace) -> str:
                path = workspace.root / "brand.yaml"
                path.write_text(path.read_text(encoding="utf-8") + "migrated: true\n", "utf-8")
                return "rewrote brand.yaml"

        run = run_migrations(workspace, [TouchesData()], version="0.2.0")
        assert run.backup is not None
        restored = (run.backup / "brand.yaml").read_text(encoding="utf-8")
        assert restored == content["brand.yaml"]
        assert "migrated" in (workspace.root / "brand.yaml").read_text(encoding="utf-8")

    def test_the_installer_never_writes_outside_its_own_target(
        self, tmp_path: Path, target: InstallTarget
    ) -> None:
        workspace, _ = self._workspace_with_content(tmp_path)
        sibling = tmp_path / "skills" / "somebody-elses-skill"
        sibling.mkdir(parents=True)
        (sibling / "SKILL.md").write_text("---\nname: somebody-elses-skill\n---\n", "utf-8")

        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())
        install(m2, new, target)

        assert (sibling / "SKILL.md").is_file(), "an unrelated skill was removed"
        assert workspace.exists


# ---------------------------------------------------------------------------
# Interruption
# ---------------------------------------------------------------------------
class TestInterruption:
    def test_a_copy_that_dies_leaves_the_old_version_recorded(
        self, tmp_path: Path, target: InstallTarget, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())

        import meta_ads_agent.install.engine as engine

        def die(*args, **kwargs):
            raise KeyboardInterrupt("power cut")

        monkeypatch.setattr(engine, "_swap_in", die)
        plan = plan_install(m2, new, target)
        with pytest.raises(KeyboardInterrupt):
            apply_install(plan, new)

        state = InstallState.load(target.root)
        assert state.version == "0.1.0", "an unfinished update must not claim the new version"
        assert state.interrupted
        assert state.in_progress and state.in_progress.stage == "swap"

    def test_the_interruption_is_visible_to_the_next_run(
        self, tmp_path: Path, target: InstallTarget, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())

        import meta_ads_agent.install.engine as engine

        monkeypatch.setattr(engine, "_swap_in", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(OSError):
            apply_install(plan_install(m2, new, target), new)

        monkeypatch.undo()
        plan = plan_install(m2, new, target)
        assert plan.resuming
        assert plan.action == "resume"

    def test_resuming_completes_the_upgrade(
        self, tmp_path: Path, target: InstallTarget, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())

        import meta_ads_agent.install.engine as engine

        monkeypatch.setattr(engine, "_swap_in", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(OSError):
            apply_install(plan_install(m2, new, target), new)
        monkeypatch.undo()

        result = apply_install(plan_install(m2, new, target), new)
        assert result.verification.complete
        state = InstallState.load(target.root)
        assert state.version == "0.2.0"
        assert not state.interrupted

    def test_a_resume_does_not_overwrite_the_good_backup(
        self, tmp_path: Path, target: InstallTarget, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The backup taken before the failure is the only way back."""
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())

        import meta_ads_agent.install.engine as engine

        monkeypatch.setattr(engine, "_swap_in", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(OSError):
            apply_install(plan_install(m2, new, target), new)
        monkeypatch.undo()

        state = InstallState.load(target.root)
        backup = Path(state.in_progress.backup)
        assert "core v1" in (backup / "meta-ads-core" / "SKILL.md").read_text(encoding="utf-8")

        apply_install(plan_install(m2, new, target), new)
        assert "core v1" in (backup / "meta-ads-core" / "SKILL.md").read_text(encoding="utf-8")

    def test_rollback_restores_the_previous_version(
        self, tmp_path: Path, target: InstallTarget, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())

        import meta_ads_agent.install.engine as engine

        monkeypatch.setattr(engine, "_swap_in", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(OSError):
            apply_install(plan_install(m2, new, target), new)
        monkeypatch.undo()

        rollback(target)
        state = InstallState.load(target.root)
        assert state.version == "0.1.0"
        assert not state.interrupted
        assert verify_tree(m1, target.root).complete
        assert not (target.root / "meta-ads-audit").exists()

    def test_a_migration_killed_half_way_is_resumable(self, tmp_path: Path) -> None:
        workspace = Workspace.at(tmp_path / "proj" / ".meta-ads")
        workspace.create()
        (workspace.root / "brand.yaml").write_text("name: Acme\n", encoding="utf-8")

        state = {"fail": True}

        class Flaky:
            id = "9999-flaky"
            description = "fails once, then works"
            introduced_in = "0.2.0"
            changes_user_data = True

            def is_satisfied(self, workspace: Workspace) -> bool:
                return (workspace.root / "done.txt").is_file()

            def apply(self, workspace: Workspace) -> str:
                if state["fail"]:
                    raise RuntimeError("disk full")
                (workspace.root / "done.txt").write_text("ok\n", encoding="utf-8")
                return "done"

        first = run_migrations(workspace, [Flaky()], version="0.2.0")
        assert first.failed
        assert not MigrationLedger.load(workspace).has("9999-flaky")
        assert first.backup and (first.backup / "brand.yaml").is_file()

        state["fail"] = False
        second = run_migrations(workspace, [Flaky()], version="0.2.0")
        assert second.applied == ["9999-flaky"]
        assert MigrationLedger.load(workspace).has("9999-flaky")


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------
class TestIntegrity:
    def test_the_committed_manifest_matches_the_tree(self) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(REPO / "scripts" / "build_release_manifest.py"), "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_manifest_version_is_the_package_version(self) -> None:
        manifest = load_manifest(REPO / "release-manifest.json")
        assert manifest.version == __version__

    def test_a_missing_file_is_detected(self, tmp_path: Path, target: InstallTarget) -> None:
        manifest = packaged.release_manifest()
        install(manifest, packaged.payload_source(), target)
        (target.root / "meta-ads-core" / "SKILL.md").unlink()
        report = verify_tree(manifest, target.root)
        assert not report.complete
        assert "meta-ads-core/SKILL.md" in report.missing

    def test_a_modified_file_is_detected(self, target: InstallTarget) -> None:
        manifest = packaged.release_manifest()
        install(manifest, packaged.payload_source(), target)
        (target.root / "meta-ads-core" / "SKILL.md").write_text("tampered\n", encoding="utf-8")
        assert "meta-ads-core/SKILL.md" in verify_tree(manifest, target.root).modified

    def test_a_leftover_from_an_older_version_is_detected(self, target: InstallTarget) -> None:
        manifest = packaged.release_manifest()
        install(manifest, packaged.payload_source(), target)
        stale = target.root / "meta-ads-core" / "references" / "gone-in-this-release.md"
        stale.write_text("# old\n", encoding="utf-8")
        assert (
            "meta-ads-core/references/gone-in-this-release.md"
            in verify_tree(manifest, target.root).orphaned
        )

    def test_an_incomplete_source_is_refused_before_anything_moves(
        self, tmp_path: Path, target: InstallTarget
    ) -> None:
        old, m1 = make_release(tmp_path / "v1", "0.1.0", v1_files())
        install(m1, old, target)
        new, m2 = make_release(tmp_path / "v2", "0.2.0", v2_files())
        (new / "meta-ads-core" / "scripts" / "migrate_schema.py").unlink()

        with pytest.raises(StateError, match="missing from"):
            apply_install(plan_install(m2, new, target), new)

        state = InstallState.load(target.root)
        assert state.version == "0.1.0"
        assert "core v1" in (target.root / "meta-ads-core" / "SKILL.md").read_text("utf-8")

    def test_a_hand_edited_manifest_is_rejected(self, tmp_path: Path) -> None:
        manifest = packaged.release_manifest()
        raw = json.loads(manifest.to_json())
        raw["files"][0]["sha256"] = "0" * 64
        path = tmp_path / "release-manifest.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(Exception, match="digest"):
            load_manifest(path)
