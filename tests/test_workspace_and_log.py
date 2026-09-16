"""Workspace resolution, atomic writes, and the action log."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meta_ads_agent.capabilities import Provider, RiskLevel
from meta_ads_agent.errors import WorkspaceError
from meta_ads_agent.state.actionlog import ActionLog, ActionRecord
from meta_ads_agent.workspace import (
    WORKSPACE_ENV_VAR,
    Workspace,
    atomic_write,
    slugify,
)


class TestSlugify:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Acme Webinar Q4", "acme-webinar-q4"),
            ("Acme  —  Q4 2026!", "acme-q4-2026"),
            ("ACME/Q4", "acme-q4"),
            ("  trailing  ", "trailing"),
            ("Kampania — Święta", "kampania-wi-ta"),
        ],
    )
    def test_produces_directory_safe_names(self, raw: str, expected: str) -> None:
        assert slugify(raw) == expected

    def test_length_is_bounded(self) -> None:
        assert len(slugify("x" * 200)) <= 63

    @pytest.mark.parametrize("raw", ["", "   ", "!!!", "—"])
    def test_unusable_input_is_refused_rather_than_guessed(self, raw: str) -> None:
        with pytest.raises(WorkspaceError, match="directory-safe"):
            slugify(raw)


class TestLocation:
    def test_found_from_a_subdirectory_like_git_does(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        nested = project / "src" / "deep"
        nested.mkdir(parents=True)
        Workspace.at(project / ".meta-ads").create()
        assert Workspace.locate(nested).root == project / ".meta-ads"

    def test_the_environment_variable_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shared = tmp_path / "shared" / ".meta-ads"
        Workspace.at(shared).create()
        project = tmp_path / "project"
        project.mkdir()
        Workspace.at(project / ".meta-ads").create()
        monkeypatch.setenv(WORKSPACE_ENV_VAR, str(shared))
        assert Workspace.locate(project).root == shared

    def test_a_bad_environment_variable_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(WORKSPACE_ENV_VAR, str(tmp_path / "nope"))
        with pytest.raises(WorkspaceError, match="not a directory"):
            Workspace.locate(tmp_path)

    def test_absence_can_be_tolerated(self, tmp_path: Path) -> None:
        workspace = Workspace.locate(tmp_path, required=False)
        assert workspace.exists is False

    def test_absence_is_reported_with_the_fix(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceError, match="meta-ads-agent init"):
            Workspace.locate(tmp_path)


class TestPrivacy:
    def test_a_new_workspace_ignores_itself(self, tmp_path: Path) -> None:
        # The repo's .gitignore cannot help a user's own project.
        workspace = Workspace.at(tmp_path / ".meta-ads")
        workspace.create()
        gitignore = workspace.root / ".gitignore"
        assert gitignore.is_file()
        assert gitignore.read_text().strip().endswith("*")

    def test_an_existing_gitignore_is_not_overwritten(self, tmp_path: Path) -> None:
        workspace = Workspace.at(tmp_path / ".meta-ads")
        workspace.root.mkdir(parents=True)
        (workspace.root / ".gitignore").write_text("!reports/\n")
        workspace.create()
        assert (workspace.root / ".gitignore").read_text() == "!reports/\n"

    def test_create_is_safe_to_re_run(self, tmp_path: Path) -> None:
        workspace = Workspace.at(tmp_path / ".meta-ads")
        assert len(workspace.create()) == 6
        assert workspace.create() == []


class TestAtomicWrite:
    def test_content_is_written(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "file.json"
        atomic_write(target, '{"a": 1}\n')
        assert target.read_text() == '{"a": 1}\n'

    def test_no_temporary_files_are_left_behind(self, tmp_path: Path) -> None:
        atomic_write(tmp_path / "f.txt", "x")
        assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]

    def test_an_existing_file_is_replaced_not_appended(self, tmp_path: Path) -> None:
        target = tmp_path / "f.txt"
        atomic_write(target, "first")
        atomic_write(target, "second")
        assert target.read_text() == "second"

    def test_a_failed_write_leaves_the_original_intact(self, tmp_path: Path) -> None:
        target = tmp_path / "f.txt"
        atomic_write(target, "original")
        with pytest.raises(TypeError):
            atomic_write(target, None)  # type: ignore[arg-type]
        assert target.read_text() == "original"
        assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]


class TestYamlSafety:
    def test_only_safe_yaml_is_loaded(self, workspace: Workspace) -> None:
        # A workspace file can come from anywhere. Full-loader YAML can
        # construct arbitrary Python objects.
        workspace.brand_file.write_text("name: !!python/object/apply:os.system ['echo pwned']\n")
        with pytest.raises(WorkspaceError, match="not valid YAML"):
            workspace.read_yaml(workspace.brand_file)

    def test_a_non_mapping_document_is_rejected(self, workspace: Workspace) -> None:
        workspace.brand_file.write_text("- just\n- a\n- list\n")
        with pytest.raises(WorkspaceError, match="mapping"):
            workspace.read_yaml(workspace.brand_file)

    def test_an_empty_file_reads_as_empty(self, workspace: Workspace) -> None:
        workspace.brand_file.write_text("")
        assert workspace.read_yaml(workspace.brand_file) == {}


class TestActionLog:
    def test_records_are_appended_one_per_line(self, workspace: Workspace) -> None:
        log = ActionLog(workspace)
        log.append(ActionRecord(operation="create_campaign", resource_id="120"))
        log.append(ActionRecord(operation="create_ad_set", resource_id="121"))
        lines = log.path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["operation"] == "create_campaign"

    def test_a_budget_change_records_before_and_after(self, workspace: Workspace) -> None:
        log = ActionLog(workspace)
        log.append(
            ActionRecord(
                operation="change_budget",
                risk_level=RiskLevel.BUDGET_INCREASE,
                resource_type="campaign",
                resource_id="120",
                before={"daily_budget": "50.00 PLN"},
                after={"daily_budget": "70.00 PLN"},
                approval_noted=True,
            )
        )
        record = log.read()[-1]
        assert record.before["daily_budget"] == "50.00 PLN"
        assert record.after["daily_budget"] == "70.00 PLN"
        assert record.approval_noted is True

    def test_the_provider_is_recorded(self, workspace: Workspace) -> None:
        log = ActionLog(workspace)
        log.append(ActionRecord(operation="upload_video", provider=Provider.API_FALLBACK))
        assert log.read()[-1].provider is Provider.API_FALLBACK

    def test_secrets_are_scrubbed_on_the_way_in(self, workspace: Workspace) -> None:
        log = ActionLog(workspace)
        log.append(
            ActionRecord(
                operation="upload_image",
                detail="used access_token=EAAnotarealtoken000000",
            )
        )
        assert "EAAnotarealtoken000000" not in log.path.read_text()
        assert "REDACTED" in log.path.read_text()

    def test_a_malformed_line_does_not_break_the_log(self, workspace: Workspace) -> None:
        # The log's job is to be readable when something already went wrong.
        log = ActionLog(workspace)
        log.append(ActionRecord(operation="create_campaign"))
        with log.path.open("a", encoding="utf-8") as stream:
            stream.write("{ this is not json\n")
        log.append(ActionRecord(operation="create_ad"))
        operations = [r.operation for r in log.read()]
        assert operations == ["create_campaign", "create_ad"]

    def test_an_absent_log_reads_as_empty(self, workspace: Workspace) -> None:
        assert ActionLog(workspace).read() == []

    def test_reading_can_be_limited_to_the_most_recent(self, workspace: Workspace) -> None:
        log = ActionLog(workspace)
        for index in range(10):
            log.append(ActionRecord(operation=f"op{index}"))
        assert [r.operation for r in log.read(limit=3)] == ["op7", "op8", "op9"]

    def test_the_host_is_recorded_when_declared(
        self, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("META_ADS_AGENT_HOST", "claude-code")
        assert ActionLog(workspace).append(ActionRecord(operation="x")).agent_host == (
            "claude-code"
        )

    def test_the_result_field_is_constrained(self) -> None:
        with pytest.raises(Exception, match="result"):
            ActionRecord(operation="x", result="mostly fine")

    def test_the_log_has_no_credential_fields(self) -> None:
        forbidden = ("token", "secret", "password", "credential")
        for name in ActionRecord.model_fields:
            assert not any(f in name.lower() for f in forbidden), name

    def test_works_under_a_path_with_spaces(self, spaced_workspace: Workspace) -> None:
        log = ActionLog(spaced_workspace)
        log.append(ActionRecord(operation="create_campaign"))
        assert len(log.read()) == 1
        assert " " in str(log.path)


class TestCampaignPaths:
    def test_campaign_paths_are_derived_from_the_slug(self, workspace: Workspace) -> None:
        assert workspace.plan_file("Acme Q4").name == "plan.yaml"
        assert workspace.plan_file("Acme Q4").parent.name == "acme-q4"
        assert workspace.state_file("acme-q4").name == "state.json"

    def test_listing_ignores_hidden_and_template_directories(self, workspace: Workspace) -> None:
        for name in ("real-campaign", "_template", ".hidden"):
            (workspace.campaigns_dir / name).mkdir(parents=True)
        assert workspace.list_campaigns() == ["real-campaign"]

    def test_listing_an_absent_directory_is_empty(self, tmp_path: Path) -> None:
        assert Workspace.at(tmp_path / ".meta-ads").list_campaigns() == []
