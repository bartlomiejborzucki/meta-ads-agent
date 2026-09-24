"""CLI behaviour: exit codes, JSON output, and the guardrails in the commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conftest import plan_dict, write_png
from meta_ads_agent.cli.main import main
from meta_ads_agent.workspace import Workspace


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's own credentials and workspace out of CLI tests."""
    for name in (
        "META_ACCESS_TOKEN",
        "META_APP_ID",
        "META_APP_SECRET",
        "META_AD_ACCOUNT_ID",
        "META_GRAPH_API_VERSION",
        "META_ADS_WORKSPACE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


class TestTopLevel:
    def test_no_command_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run([], capsys)
        assert code == 0
        assert "meta-ads-agent doctor" in out

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--version"])
        assert exit_info.value.code == 0

    def test_the_help_explains_that_the_cli_is_not_the_main_interface(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out, _ = run([], capsys)
        assert "primary execution layer" in out


class TestDoctor:
    def test_reports_readiness_without_credentials(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(["doctor"], capsys)
        assert code == 0
        assert "READY FOR MCP" in out
        # Absent fallback credentials must not read as a failure.
        assert "MISSING OPTIONAL FALLBACK CONFIG" in out

    def test_json_output_is_parseable(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(["doctor", "--json"], capsys)
        assert code == 0
        payload = json.loads(out)
        assert payload["api_fallback_ready"] is False
        assert any(c["label"] == "capability registry" for c in payload["checks"])

    def test_a_missing_mcp_connection_prints_the_exact_command(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out, _ = run(["doctor"], capsys)
        if "Meta Ads MCP configured    MISSING" in out:
            assert "claude mcp add --transport http" in out
            assert "mcp.facebook.com/ads" in out

    def test_a_token_is_never_echoed(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("META_ACCESS_TOKEN", "test-token-value-abcdefgh")
        _, out, _ = run(["doctor"], capsys)
        assert "test-token-value-abcdefgh" not in out
        assert "sha256:" in out

    def test_suggests_init_when_no_workspace_exists(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out, _ = run(["doctor"], capsys)
        assert "meta-ads-agent init" in out


class TestInit:
    def test_creates_a_workspace_from_templates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _out, _ = run(["init", "--brand", "Acme"], capsys)
        assert code == 0
        workspace = Workspace.at(tmp_path / ".meta-ads")
        assert workspace.brand_file.is_file()
        assert workspace.voice_file.is_file()
        assert (workspace.offers_dir / "example.yaml").is_file()
        assert (workspace.root / ".gitignore").is_file()

    def test_the_brand_name_is_pre_filled(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init", "--brand", "Acme Sp. z o.o."], capsys)
        brand = yaml.safe_load((tmp_path / ".meta-ads" / "brand.yaml").read_text())
        assert brand["name"] == "Acme Sp. z o.o."

    def test_re_running_keeps_existing_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        brand_file = tmp_path / ".meta-ads" / "brand.yaml"
        brand_file.write_text("name: Edited By Hand\n")
        code, out, _ = run(["init"], capsys)
        assert code == 0
        assert "kept" in out
        assert brand_file.read_text() == "name: Edited By Hand\n"

    def test_force_overwrites(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        run(["init"], capsys)
        brand_file = tmp_path / ".meta-ads" / "brand.yaml"
        brand_file.write_text("name: Edited By Hand\n")
        run(["init", "--force"], capsys)
        assert "Your Brand" in brand_file.read_text()

    def test_check_validates_the_workspace(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        code, out, _ = run(["init", "--check"], capsys)
        assert code == 0
        assert "workspace ok" in out

    def test_check_reports_a_broken_brand_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        (tmp_path / ".meta-ads" / "brand.yaml").write_text("name: Acme\nprofile: reckless\n")
        code, _, err = run(["init", "--check"], capsys)
        assert code == 1
        assert "failed validation" in err

    def test_check_without_a_workspace_fails_clearly(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(["init", "--check"], capsys)
        assert code == 1
        assert "meta-ads-agent init" in err

    def test_works_in_a_directory_with_spaces(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = tmp_path / "my projects" / "Acme — kampanie"
        project.mkdir(parents=True)
        monkeypatch.chdir(project)
        assert run(["init"], capsys)[0] == 0
        assert (project / ".meta-ads" / "brand.yaml").is_file()


class TestCapabilities:
    def test_lists_routing_by_area(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(["capabilities"], capsys)
        assert code == 0
        assert "Capability routing" in out
        assert "Fallback gaps" in out

    def test_states_the_caveat_about_live_introspection(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Claiming a capability exists on the strength of a local file is the
        # mistake this command must not make.
        _, out, _ = run(["capabilities"], capsys)
        assert "not live introspection" in out

    def test_gaps_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        _, out, _ = run(["capabilities", "--gaps"], capsys)
        assert "local_video_upload" in out
        assert "list_ad_accounts" not in out

    def test_one_capability_in_detail(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(["capabilities", "local_video_upload"], capsys)
        assert code == 0
        assert "api_fallback" in out
        assert "meta-ads-agent api upload-video" in out

    def test_an_unknown_capability_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _, err = run(["capabilities", "teleport_budget"], capsys)
        assert code == 1
        assert "Unknown capability" in err

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        _, out, _ = run(["capabilities", "--json"], capsys)
        payload = json.loads(out)
        assert payload["mcp_endpoint"] == "https://mcp.facebook.com/ads"
        assert any(c["is_gap"] for c in payload["capabilities"])

    def test_validate_passes_on_the_shipped_registry(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(["capabilities", "--validate"], capsys)
        assert code == 0
        assert "registry ok" in out


class TestValidatePlan:
    def _write_plan(self, root: Path, mutate=None) -> Path:  # type: ignore[no-untyped-def]
        raw = plan_dict()
        if mutate:
            mutate(raw)
        directory = root / ".meta-ads" / "campaigns" / "acme-webinar"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "plan.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False))
        return path

    def test_a_valid_plan_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self._write_plan(tmp_path)
        code, out, _ = run(["validate-plan", str(path), "--skip-assets"], capsys)
        assert code == 0
        assert "VALID" in out

    def test_an_invalid_plan_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["dsa"] = {"beneficiary": None, "payor": None}

        path = self._write_plan(tmp_path, mutate)
        code, out, _ = run(["validate-plan", str(path), "--skip-assets"], capsys)
        assert code == 1
        assert "BLOCKED" in out
        assert "dsa.missing_fields" in out

    def test_an_unparseable_plan_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "plan.yaml"
        path.write_text("campaign: [this is not a mapping]\n")
        code, _, err = run(["validate-plan", str(path)], capsys)
        assert code == 2
        assert "not a valid campaign plan" in err

    def test_a_missing_file_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(["validate-plan", str(tmp_path / "nope.yaml")], capsys)
        assert code == 2
        assert "not found" in err

    def test_strict_treats_warnings_as_failure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self._write_plan(tmp_path)
        code, _, err = run(["validate-plan", str(path), "--skip-assets", "--strict"], capsys)
        assert code == 1
        assert "treated as failure" in err

    def test_json_output_names_the_providers(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self._write_plan(tmp_path)
        _, out, _ = run(["validate-plan", str(path), "--skip-assets", "--json"], capsys)
        payload = json.loads(out)
        assert payload["ok"] is True
        assert payload["providers"]["create_single_image_creative"] == "official_mcp"

    def test_a_local_asset_is_resolved_relative_to_the_plan(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": "./creatives/a.png"}
            ]

        path = self._write_plan(tmp_path, mutate)
        (path.parent / "creatives").mkdir()
        write_png(path.parent / "creatives" / "a.png", 1200, 628)
        code, out, _ = run(["validate-plan", str(path)], capsys)
        assert code == 0
        assert "1200x628" in out

    def test_the_cached_account_template_is_treated_as_unread(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A template full of nulls must not be mistaken for real account data.
        run(["init"], capsys)
        path = self._write_plan(tmp_path)
        _, out, _ = run(["validate-plan", str(path), "--skip-assets"], capsys)
        assert "NOT LOADED" in out


class TestSeveralAccounts:
    """One workspace, several ad accounts: facts are looked up by the plan's account."""

    def _workspace(self, root: Path, *accounts: str) -> Path:
        ws = root / ".meta-ads"
        (ws / "accounts").mkdir(parents=True)
        for account in accounts:
            (ws / "accounts" / f"{account}.yaml").write_text(
                yaml.safe_dump({"id": account, "currency": "PLN", "account_status": 1})
            )
        return ws

    def _plan(self, ws: Path, slug: str, account: str) -> Path:
        directory = ws / "campaigns" / slug
        directory.mkdir(parents=True)
        path = directory / "plan.yaml"
        path.write_text(yaml.safe_dump(plan_dict(slug=slug, ad_account_id=account)))
        return path

    def test_a_plan_is_validated_against_its_own_accounts_facts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ws = self._workspace(tmp_path, "act_1234567890", "act_9999999999")
        path = self._plan(ws, "second", "act_9999999999")
        _, out, _ = run(["validate-plan", str(path), "--skip-assets", "--json"], capsys)
        payload = json.loads(out)
        assert payload["account_context"] is True
        assert "account.mismatch" not in {f["code"] for f in payload["findings"]}

    def test_a_single_account_yaml_for_another_account_is_not_used(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ws = tmp_path / ".meta-ads"
        ws.mkdir()
        (ws / "account.yaml").write_text(yaml.safe_dump({"id": "act_1234567890"}))
        path = self._plan(ws, "other", "act_9999999999")
        _, out, err = run(["validate-plan", str(path), "--skip-assets", "--json"], capsys)
        payload = json.loads(out)  # the hint went to stderr, so stdout is still JSON
        assert payload["account_context"] is False
        assert "accounts/act_9999999999.yaml" in err

    def test_the_single_account_yaml_still_works_for_its_account(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ws = tmp_path / ".meta-ads"
        ws.mkdir()
        (ws / "account.yaml").write_text(yaml.safe_dump({"id": "act_1234567890"}))
        path = self._plan(ws, "same", "act_1234567890")
        _, out, _ = run(["validate-plan", str(path), "--skip-assets", "--json"], capsys)
        assert json.loads(out)["account_context"] is True

    def test_state_lists_and_filters_by_account(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ws = self._workspace(tmp_path)
        self._plan(ws, "first", "act_1234567890")
        self._plan(ws, "second", "act_9999999999")
        _, out, _ = run(["state", "--json"], capsys)
        assert {c["account"] for c in json.loads(out)["campaigns"]} == {
            "act_1234567890",
            "act_9999999999",
        }
        _, out, _ = run(["state", "--json", "--account", "9999999999"], capsys)
        assert [c["slug"] for c in json.loads(out)["campaigns"]] == ["second"]


class TestState:
    def test_listing_an_empty_workspace(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        code, out, _ = run(["state"], capsys)
        assert code == 0
        assert "none yet" in out

    def test_no_workspace_fails_clearly(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _, err = run(["state"], capsys)
        assert code == 1
        assert "workspace" in err

    def test_state_detail_shows_objects_and_the_resume_point(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        from meta_ads_agent.models.plan import CampaignPlanDocument
        from meta_ads_agent.models.state import (
            CreatedObject,
            ObjectType,
            Provider,
            Stage,
        )
        from meta_ads_agent.state.store import StateStore

        workspace = Workspace.locate(tmp_path)
        store = StateStore(workspace)
        doc = CampaignPlanDocument.model_validate(plan_dict())
        store.save_plan(doc)
        state = store.load_or_create_state(doc)
        store.record_object(
            state,
            CreatedObject(
                id="120210000000001",
                type=ObjectType.CAMPAIGN,
                name="Acme campaign",
                provider=Provider.OFFICIAL_MCP,
                plan_ref="campaign",
                status_at_creation="PAUSED",
            ),
        )
        store.advance(state, Stage.CAMPAIGN_CREATED)

        code, out, _ = run(["state", "acme-webinar"], capsys)
        assert code == 0
        assert "120210000000001" in out
        assert "PAUSED" in out
        assert "next stage  ad_sets_created" in out
        assert "Meta is authoritative" in out

    def test_json_state_reports_the_resume_stage(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        from meta_ads_agent.models.plan import CampaignPlanDocument
        from meta_ads_agent.state.store import StateStore

        workspace = Workspace.locate(tmp_path)
        store = StateStore(workspace)
        doc = CampaignPlanDocument.model_validate(plan_dict())
        store.save_plan(doc)
        store.load_or_create_state(doc)
        _, out, _ = run(["state", "acme-webinar", "--json"], capsys)
        payload = json.loads(out)
        assert payload["stage"] == "planned"
        assert payload["resume_from"] == "validated"
        assert payload["plan_drift"] is False


class TestApiGuardrails:
    def test_api_without_a_subcommand_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(["api"], capsys)
        assert code == 0
        assert "upload-image" in out

    def test_a_real_upload_without_a_token_explains_it_is_optional(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        image = write_png(tmp_path / "a.png", 600, 600)
        code, _, err = run(["api", "upload-image", str(image)], capsys)
        assert code == 1
        assert "does not expose" in err

    def test_a_dry_run_works_before_any_credentials_exist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        image = write_png(tmp_path / "a.png", 600, 600)
        code, out, _ = run(["api", "upload-image", str(image), "--dry-run"], capsys)
        assert code == 0
        assert "DRY RUN" in out

    def test_delete_without_approval_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        code, _, err = run(
            ["api", "delete", "120", "--type", "ad", "--reason", "duplicate"], capsys
        )
        assert code == 2
        assert "--approved" in err
        assert "optimisation history" in err

    def test_delete_requires_a_reason_at_the_parser_level(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            main(["api", "delete", "120", "--type", "ad", "--approved"])

    def test_creative_modes_are_mutually_exclusive(self) -> None:
        with pytest.raises(SystemExit):
            main(["api", "create-creative", "--video", "--post", "--name", "x"])

    def test_a_video_creative_without_a_video_id_is_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        code, _, err = run(
            [
                "api",
                "create-creative",
                "--video",
                "--name",
                "x",
                "--page-id",
                "1",
                "--url",
                "https://x.example.com",
                "--primary-text",
                "hi",
                "--dry-run",
            ],
            capsys,
        )
        assert code == 2
        assert "--video-id" in err

    def test_missing_required_creative_options_are_listed_together(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(["init"], capsys)
        code, _, err = run(
            ["api", "create-creative", "--video", "--name", "x", "--dry-run"], capsys
        )
        assert code == 2
        assert "--page-id" in err
        assert "--url" in err
        assert "--primary-text" in err
