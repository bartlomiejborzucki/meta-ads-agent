"""Concurrent writers: two sessions against one workspace must not lose entries.

Each file was already written atomically, which stops a crash from truncating
it but not two writers from each saving the version they read. These tests
run real concurrent writers (threads, each with its own lock handle, which is
how two processes look to the lock) and check nothing went missing.
"""

from __future__ import annotations

import errno
import json
import sys
import threading
from pathlib import Path

import pytest

from conftest import write_png
from meta_ads_agent.errors import ReconciliationError, StateError
from meta_ads_agent.locking import file_lock, lock_path_for
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import CreatedObject, ObjectType, Provider
from meta_ads_agent.state.actionlog import ActionLog, ActionRecord
from meta_ads_agent.state.assets import AssetStore, probe_asset
from meta_ads_agent.state.store import StateStore
from meta_ads_agent.workspace import Workspace


def _in_threads(count: int, work) -> None:  # type: ignore[no-untyped-def]
    errors: list[BaseException] = []
    barrier = threading.Barrier(count)

    def run(index: int) -> None:
        try:
            barrier.wait()
            work(index)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


class TestFileLock:
    def test_a_held_lock_makes_a_second_holder_wait_then_fail_clearly(self, tmp_path: Path) -> None:
        target = tmp_path / "manifest.json"
        with (
            file_lock(target),
            pytest.raises(StateError, match="another meta-ads-agent process"),
            file_lock(target, timeout=0.2),
        ):
            pass  # pragma: no cover - the inner lock never succeeds

    def test_the_lock_is_released_after_the_block(self, tmp_path: Path) -> None:
        target = tmp_path / "manifest.json"
        with file_lock(target):
            pass
        with file_lock(target, timeout=0.2):
            pass
        assert lock_path_for(target).name == ".manifest.json.lock"

    @pytest.mark.skipif(sys.platform == "win32", reason="flock is the POSIX path")
    def test_a_filesystem_without_flock_proceeds_unlocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # drvfs (a Windows drive under WSL) is where windows-codex installs go.
        import fcntl

        def refuse(fd: int, operation: int) -> None:
            raise OSError(errno.ENOLCK, "No locks available")

        monkeypatch.setattr(fcntl, "flock", refuse)
        with file_lock(tmp_path / "x.json", timeout=0.2):
            pass


class TestConcurrentWriters:
    def test_parallel_uploads_of_different_files_all_reach_the_manifest(
        self, workspace: Workspace, tmp_path: Path
    ) -> None:
        probes = [probe_asset(write_png(tmp_path / f"img{i}.png", 10 + i, 10)) for i in range(8)]

        def remember(index: int) -> None:
            AssetStore(workspace).remember(
                probes[index], "act_1234567890", image_hash=f"hash{index}"
            )

        _in_threads(len(probes), remember)
        manifest = AssetStore(workspace).load()
        assert all(manifest.lookup(p.fingerprint, "act_1234567890") is not None for p in probes)

    def test_one_file_is_claimed_by_one_uploader_at_a_time(
        self, workspace: Workspace, tmp_path: Path
    ) -> None:
        probe = probe_asset(write_png(tmp_path / "hero.png", 20, 20))
        store = AssetStore(workspace)
        uploads: list[int] = []

        def upload_once(index: int) -> None:
            with store.claim(probe, "act_1234567890"):
                if store.lookup(probe, "act_1234567890") is None:
                    uploads.append(index)
                    store.remember(probe, "act_1234567890", image_hash="h")

        _in_threads(6, upload_once)
        assert len(uploads) == 1

    def test_parallel_log_appends_are_whole_lines(self, workspace: Workspace) -> None:
        def append(index: int) -> None:
            log = ActionLog(workspace)
            for n in range(20):
                log.append(ActionRecord(operation=f"op{index}-{n}", detail="x" * 2000))

        _in_threads(6, append)
        lines = workspace.action_log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 120
        assert all(json.loads(line)["operation"] for line in lines)


def _obj(plan_ref: str, object_id: str, kind: ObjectType) -> CreatedObject:
    return CreatedObject(
        id=object_id,
        type=kind,
        name=plan_ref,
        provider=Provider.OFFICIAL_MCP,
        plan_ref=plan_ref,
        status_at_creation="PAUSED",
    )


class TestTwoSessionsOnOneCampaign:
    def test_neither_session_erases_the_other_sessions_objects(
        self, workspace: Workspace, plan: CampaignPlanDocument
    ) -> None:
        first, second = StateStore(workspace), StateStore(workspace)
        mine = first.load_or_create_state(plan)
        theirs = second.load_or_create_state(plan)

        first.record_object(mine, _obj("campaign", "120001", ObjectType.CAMPAIGN))
        second.record_object(theirs, _obj("ad_sets[0]", "120045", ObjectType.AD_SET))

        on_disk = StateStore(workspace).load_state(plan.slug)
        assert {o.id for o in on_disk.objects} == {"120001", "120045"}

    def test_a_conflict_keeps_both_ids_and_then_says_so(
        self, workspace: Workspace, plan: CampaignPlanDocument
    ) -> None:
        # Two sessions both created "the campaign". One is a duplicate on Meta,
        # and losing either id would hide it.
        first, second = StateStore(workspace), StateStore(workspace)
        mine = first.load_or_create_state(plan)
        theirs = second.load_or_create_state(plan)

        first.record_object(mine, _obj("campaign", "120001", ObjectType.CAMPAIGN))
        with pytest.raises(ReconciliationError, match=r"campaign: 120002 and 120001"):
            second.record_object(theirs, _obj("campaign", "120002", ObjectType.CAMPAIGN))

        on_disk = StateStore(workspace).load_state(plan.slug)
        assert {o.id for o in on_disk.objects} == {"120001", "120002"}


class TestInstallLock:
    def test_the_lock_file_is_not_mistaken_for_a_stray_file(self, tmp_path: Path) -> None:
        from meta_ads_agent.cli.install_cmd import _install_payload, installation_report
        from meta_ads_agent.install.state import LOCK_FILENAME

        target = tmp_path / "skills"
        _install_payload(target_kind="path", path=str(target))
        assert (target / LOCK_FILENAME).exists()
        assert installation_report(target_kind="path", path=str(target))["status"] == "complete"
