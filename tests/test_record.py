"""``record``, ``cache-account`` and ``plan-calls`` from the command line.

The state store - one writer at a time, sessions merged, ids tied to a plan
fingerprint - was called by tests and by nothing else: the agent wrote
state.json by hand. These are its callers.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import plan_dict, write_png
from meta_ads_agent.cli.main import main
from meta_ads_agent.cli.record_cmd import progress
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import CampaignState, CreatedObject, ObjectType, Provider, Stage
from meta_ads_agent.state.assets import AssetStore, probe_asset
from meta_ads_agent.state.store import StateStore, fingerprint_matches
from meta_ads_agent.workspace import Workspace

SLUG = "acme-webinar"


def two_ads(raw: dict[str, Any]) -> dict[str, Any]:
    """The fixture plan with a second ad, sharing one local image with the first."""
    ad_set = raw["campaign"]["ad_sets"][0]
    first = ad_set["ads"][0]
    first["creative"]["assets"] = [{"local_path": "square.png"}]
    second = json.loads(json.dumps(first))
    second["name"] = "angle-b"
    ad_set["ads"].append(second)
    return raw


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
    workspace = Workspace.at(tmp_path / ".meta-ads")
    workspace.create()
    plan = workspace.plan_file(SLUG)
    plan.parent.mkdir(parents=True)
    plan.write_text(yaml.safe_dump(two_ads(plan_dict())), encoding="utf-8")
    write_png(plan.parent / "square.png", 1080, 1080)
    return workspace


def record(*argv: str) -> int:
    return main(["record", *argv])


def state(project: Workspace) -> CampaignState:
    return StateStore(project).load_state(SLUG)


def build(project: Workspace, *, upto: str = "ad") -> None:
    """Record a build in order, stopping after *upto*."""
    steps = [
        (
            "campaign",
            ["object", SLUG, "--type", "campaign", "--id", "101", "--plan-ref", "campaign"],
        ),
        ("ad_set", ["object", SLUG, "--type", "ad_set", "--id", "201", "--plan-ref", "ad_sets[0]"]),
        (
            "asset",
            [
                "asset", SLUG, "--file", str(project.plan_file(SLUG).parent / "square.png"),
                "--image-hash", "hash0001",
                "--plan-ref", "ad_sets[0].ads[0].creative.assets[0]",
            ],
        ),
        (
            "creative",
            [
                "object", SLUG, "--type", "creative", "--id", "301",
                "--plan-ref", "ad_sets[0].ads[0].creative",
            ],
        ),
        (
            "creative2",
            [
                "object", SLUG, "--type", "creative", "--id", "302",
                "--plan-ref", "ad_sets[0].ads[1].creative",
            ],
        ),
        ("ad1", ["object", SLUG, "--type", "ad", "--id", "401", "--plan-ref", "ad_sets[0].ads[0]"]),
        ("ad", ["object", SLUG, "--type", "ad", "--id", "402", "--plan-ref", "ad_sets[0].ads[1]"]),
    ]  # fmt: skip
    for name, argv in steps:
        assert record(*argv) == 0, name
        if name == upto:
            return


class TestRecordObject:
    def test_the_first_id_creates_state_tied_to_the_plan(self, project: Workspace) -> None:
        code = record(
            *("object", SLUG, "--type", "campaign", "--id", "101", "--plan-ref", "campaign"),
            *("--status", "PAUSED", "--name", "Acme"),
        )
        assert code == 0
        saved = state(project)
        doc = StateStore(project).load_plan(SLUG)
        assert fingerprint_matches(saved.plan_fingerprint, doc)
        (obj,) = saved.objects
        assert (obj.id, obj.type, obj.provider) == (
            "101",
            ObjectType.CAMPAIGN,
            Provider.OFFICIAL_MCP,
        )
        assert (obj.plan_ref, obj.status_at_creation, obj.name) == ("campaign", "PAUSED", "Acme")

    def test_the_stage_follows_from_what_is_recorded(self, project: Workspace) -> None:
        expected = {
            "campaign": Stage.CAMPAIGN_CREATED,
            "ad_set": Stage.AD_SETS_CREATED,
            "asset": Stage.ASSETS_UPLOADED,
            "creative": Stage.ASSETS_UPLOADED,
            "creative2": Stage.CREATIVES_CREATED,
            "ad1": Stage.CREATIVES_CREATED,
            "ad": Stage.ADS_CREATED,
        }
        for upto, stage in expected.items():
            path = project.state_file(SLUG)
            path.unlink(missing_ok=True)
            build(project, upto=upto)
            assert state(project).stage is stage, upto

    def test_recording_the_same_id_again_changes_nothing(self, project: Workspace) -> None:
        build(project, upto="ad_set")
        build(project, upto="ad_set")
        assert len(state(project).objects) == 2

    def test_a_different_id_for_the_same_element_is_refused(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build(project, upto="campaign")
        code = record("object", SLUG, "--type", "campaign", "--id", "999", "--plan-ref", "campaign")
        assert code == 1
        assert "refusing to remap" in capsys.readouterr().err
        assert [o.id for o in state(project).objects] == ["101"]

    def test_an_object_reported_active_is_refused(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = record("object", SLUG, "--type", "campaign", "--id", "101",
                      "--plan-ref", "campaign", "--status", "ACTIVE")  # fmt: skip
        err = capsys.readouterr().err
        assert code == 2
        assert "recorded as ACTIVE at creation" in err
        assert "pydantic" not in err

    def test_a_draft_status_is_recorded_as_meta_reported_it(self, project: Workspace) -> None:
        record("object", SLUG, "--type", "campaign", "--id", "101",
               "--plan-ref", "campaign", "--status", "DRAFT")  # fmt: skip
        assert state(project).objects[0].status_at_creation == "DRAFT"

    def test_a_plan_changed_after_objects_exist_refuses_the_next_id(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build(project, upto="campaign")
        plan = project.plan_file(SLUG)
        raw = yaml.safe_load(plan.read_text(encoding="utf-8"))
        raw["campaign"]["name"] = "Something else"
        plan.write_text(yaml.safe_dump(raw), encoding="utf-8")
        code = record("object", SLUG, "--type", "ad_set", "--id", "201", "--plan-ref", "ad_sets[0]")
        assert code == 1
        assert "changed after 1 object(s)" in capsys.readouterr().err

    def test_json_says_where_the_build_is(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        record(
            "object", SLUG, "--type", "campaign", "--id", "101", "--plan-ref", "campaign", "--json"
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "campaign_created"
        assert payload["resume_from"] == "ad_sets_created"
        assert payload["recorded"] == {"type": "campaign", "id": "101"}

    def test_no_plan_for_the_slug_exits_2(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = record("object", "nope", "--type", "campaign", "--id", "1", "--plan-ref", "campaign")
        assert code == 2
        assert "Traceback" not in capsys.readouterr().err

    def test_record_alone_shows_its_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert record() == 2
        assert "object" in capsys.readouterr().out


class TestProgress:
    def test_an_existing_post_needs_no_creative_of_its_own(self) -> None:
        raw = plan_dict()
        creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
        for key in ("assets", "variants", "destination_url"):
            creative.pop(key)
        creative.update(mode="existing_post", post_id="1111111111_999")
        doc = CampaignPlanDocument.model_validate(raw)
        saved = CampaignState(slug=SLUG, ad_account_id=doc.ad_account_id)
        for object_type, object_id, ref in (
            ("campaign", "1", "campaign"),
            ("ad_set", "2", "ad_sets[0]"),
        ):
            saved.record(
                CreatedObject(
                    id=object_id,
                    type=ObjectType(object_type),
                    provider=Provider.OFFICIAL_MCP,
                    plan_ref=ref,
                )
            )
        assert progress(doc, saved) is Stage.CREATIVES_CREATED

    def test_nothing_recorded_is_no_stage(self) -> None:
        doc = CampaignPlanDocument.model_validate(plan_dict())
        assert progress(doc, CampaignState(slug=SLUG, ad_account_id=doc.ad_account_id)) is None


class TestOtherRecords:
    def test_stages_without_objects_and_no_going_back(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build(project)
        assert record("stage", SLUG, "previewed") == 0
        assert state(project).stage is Stage.PREVIEWED
        assert record("stage", SLUG, "validated") == 1
        assert "backwards" in capsys.readouterr().err

    def test_a_failure_is_not_retry_safe_unless_said(self, project: Workspace) -> None:
        build(project, upto="ad_set")
        assert record("failure", SLUG, "--stage", "creatives_created", "--message", "timeout",
                      "--plan-ref", "ad_sets[0].ads[0].creative") == 0  # fmt: skip
        assert record("failure", SLUG, "--stage", "creatives_created", "--message", "Invalid",
                      "--code", "100", "--subcode", "1885183", "--retry-safe") == 0  # fmt: skip
        first, second = state(project).failures
        assert (first.retry_safe, first.plan_ref) == (False, "ad_sets[0].ads[0].creative")
        assert (second.retry_safe, second.meta_code, second.meta_subcode) == (True, 100, 1885183)

    def test_activation(self, project: Workspace) -> None:
        build(project)
        assert record("activation", SLUG) == 0
        saved = state(project)
        assert saved.activated is True and saved.activated_at is not None
        assert saved.stage is Stage.ACTIVATED


class TestRecordAsset:
    def test_the_file_is_remembered_so_it_uploads_once(self, project: Workspace) -> None:
        build(project, upto="asset")
        image = project.plan_file(SLUG).parent / "square.png"
        remembered = AssetStore(project).lookup(probe_asset(image), "act_1234567890")
        assert remembered is not None
        assert (remembered.image_hash, remembered.provider) == ("hash0001", Provider.OFFICIAL_MCP)
        assert state(project).by_plan_ref("ad_sets[0].ads[0].creative.assets[0]").id == "hash0001"

    def test_plan_calls_then_uses_the_hash_instead_of_uploading(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build(project, upto="asset")
        capsys.readouterr()
        assert main(["plan-calls", str(project.plan_file(SLUG)), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        tools = [c["tool"] for c in payload["calls"] if c["status"] == "pending"]
        assert "ads_creative_upload_media" not in tools
        creatives = [c for c in payload["calls"] if c["tool"] == "ads_create_creative"]
        assert {c["args"]["image_hash"] for c in creatives} == {"hash0001"}

    def test_a_video_id_for_an_image_is_refused(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = project.plan_file(SLUG).parent / "square.png"
        assert record("asset", SLUG, "--file", str(image), "--video-id", "700") == 2
        assert "is image, but a video id" in capsys.readouterr().err

    @pytest.mark.parametrize("ids", [[], ["--image-hash", "a", "--video-id", "7"]])
    def test_exactly_one_id(self, project: Workspace, ids: list[str]) -> None:
        image = project.plan_file(SLUG).parent / "square.png"
        assert record("asset", SLUG, "--file", str(image), *ids) == 2


class TestPlanCalls:
    def test_a_fresh_plan_lists_every_call_and_how_to_record_it(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["plan-calls", str(project.plan_file(SLUG)), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_read"] == "2026-11-11"
        assert [c["tool"] for c in payload["calls"]] == [
            "ads_create_campaign",
            "ads_create_ad_set",
            "ads_creative_upload_media",
            "ads_create_creative",
            "ads_create_creative",
            "ads_create_ad",
            "ads_create_ad",
        ]
        upload = payload["calls"][2]
        assert upload["record"].startswith(f"meta-ads-agent record asset {SLUG} --file ")
        assert "--image-hash <ID>" in upload["record"]
        assert payload["calls"][0]["record"] == (
            f"meta-ads-agent record object {SLUG} --type campaign --plan-ref 'campaign' --id <ID>"
        )

    def test_a_resumed_build_skips_what_exists(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build(project, upto="ad_set")
        capsys.readouterr()
        main(["plan-calls", str(project.plan_file(SLUG)), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert [c["status"] for c in payload["calls"][:2]] == ["done", "done"]
        assert payload["pending"] == 5

    def test_a_plan_with_errors_produces_no_calls(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan = project.plan_file(SLUG)
        raw = yaml.safe_load(plan.read_text(encoding="utf-8"))
        raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["destination_url"] = (
            "http://localhost/x"
        )
        plan.write_text(yaml.safe_dump(raw), encoding="utf-8")
        assert main(["plan-calls", str(plan)]) == 1
        captured = capsys.readouterr()
        assert "does not validate" in captured.err
        assert "ads_create_campaign" not in captured.out

    def test_a_plan_changed_after_objects_exist_produces_no_calls(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build(project, upto="campaign")
        plan = project.plan_file(SLUG)
        raw = yaml.safe_load(plan.read_text(encoding="utf-8"))
        raw["campaign"]["name"] = "Something else"
        plan.write_text(yaml.safe_dump(raw), encoding="utf-8")
        assert main(["plan-calls", str(plan)]) == 1
        assert "changed after 1 object(s)" in capsys.readouterr().err

    def test_plan_calls_writes_nothing(self, project: Workspace) -> None:
        main(["plan-calls", str(project.plan_file(SLUG)), "--json"])
        assert not project.state_file(SLUG).exists()

    def test_the_human_output_names_the_date_and_the_needs(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan = project.plan_file(SLUG)
        raw = yaml.safe_load(plan.read_text(encoding="utf-8"))
        raw["campaign"]["ad_sets"][0].pop("optimization_goal")
        plan.write_text(yaml.safe_dump(raw), encoding="utf-8")
        assert main(["plan-calls", str(plan)]) == 0
        out = capsys.readouterr().out
        assert "2026-11-11" in out
        assert "NEEDS  optimization_goal" in out
        assert "Settle those before building" in out


class TestCacheAccount:
    ACCOUNT = {
        "account_id": "1234567890",
        "name": "Acme",
        "currency": "PLN",
        "currency_offset": 100,
        "timezone": "Europe/Warsaw",
        "account_status": 1,
        "min_daily_budget_cents": 500,
        "a_field_meta_added": True,
    }

    def write(self, tmp_path: Path, payload: Any) -> str:
        path = tmp_path / "account.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_the_facts_land_where_validate_plan_reads_them(
        self, project: Workspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = self.write(tmp_path, {"data": [self.ACCOUNT]})
        assert main(["cache-account", source, "--pages", "1111111111, 2", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["account"] == "act_1234567890"
        saved = yaml.safe_load(project.account_file.read_text(encoding="utf-8"))
        assert saved["id"] == "act_1234567890"
        assert (saved["timezone_name"], saved["min_daily_budget"]) == ("Europe/Warsaw", 500)
        assert saved["available_page_ids"] == ["1111111111", "2"]
        assert "a_field_meta_added" not in saved and "read_at" in saved

        assert main(["validate-plan", str(project.plan_file(SLUG)), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["account_context"] is True

    def test_a_second_account_gets_its_own_file(self, project: Workspace, tmp_path: Path) -> None:
        main(["cache-account", self.write(tmp_path, self.ACCOUNT)])
        other = {**self.ACCOUNT, "account_id": "999", "currency": "EUR"}
        assert main(["cache-account", self.write(tmp_path, other)]) == 0
        assert yaml.safe_load(project.account_file.read_text("utf-8"))["currency"] == "PLN"
        second = yaml.safe_load(project.account_file_for("act_999").read_text("utf-8"))
        assert second["currency"] == "EUR"

    def test_refreshing_the_same_account_rewrites_its_file(
        self, project: Workspace, tmp_path: Path
    ) -> None:
        main(["cache-account", self.write(tmp_path, self.ACCOUNT)])
        main(["cache-account", self.write(tmp_path, {**self.ACCOUNT, "account_status": 2})])
        assert yaml.safe_load(project.account_file.read_text("utf-8"))["account_status"] == 2
        assert not project.accounts_dir.exists() or not list(project.accounts_dir.iterdir())

    def test_several_accounts_need_one_named(
        self, project: Workspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        both = [self.ACCOUNT, {**self.ACCOUNT, "account_id": "999"}]
        source = self.write(tmp_path, both)
        assert main(["cache-account", source]) == 2
        assert "act_1234567890, act_999" in capsys.readouterr().err
        assert main(["cache-account", source, "--account", "999"]) == 0

    def test_stdin(self, project: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(self.ACCOUNT)))
        assert main(["cache-account", "-"]) == 0
        assert project.account_file.is_file()

    @pytest.mark.parametrize("content", ["not json", "[]", '"a string"', '[{"name": "no id"}]'])
    def test_input_that_is_not_an_account_exits_2(
        self, project: Workspace, tmp_path: Path, content: str
    ) -> None:
        path = tmp_path / "bad.json"
        path.write_text(content, encoding="utf-8")
        assert main(["cache-account", str(path)]) == 2

    def test_no_workspace_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
        assert main(["cache-account", self.write(tmp_path, self.ACCOUNT)]) == 2
