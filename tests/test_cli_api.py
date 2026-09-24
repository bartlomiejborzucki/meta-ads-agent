"""The `meta-ads-agent api` commands end to end, against the faked SDK.

These are the highest-risk commands in the project - they upload assets, create
creatives, and delete objects - so they get exercised through the real argument
parsing and output path, not only at the function level.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import Recorder, write_png
from meta_ads_agent.cli.main import main
from meta_ads_agent.state.actionlog import ActionLog
from meta_ads_agent.state.assets import AssetStore, probe_asset
from meta_ads_agent.workspace import Workspace


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project directory with an initialised workspace, as its own cwd."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_1234567890")
    Workspace.at(tmp_path / ".meta-ads").create()
    return tmp_path


class TestUploadImage:
    def test_uploads_and_reports_the_hash(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = write_png(project / "hero.png", 1200, 628)
        code, out, _ = run(["api", "upload-image", str(image)], capsys)
        assert code == 0
        assert "fake_image_hash_1" in out
        # The reason is printed, so the architecture is visible in the transcript.
        assert "does not currently expose" in out
        assert sdk.image_uploads == [str(image)]

    def test_json_output_names_the_capability_and_the_reason(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = write_png(project / "hero.png", 600, 600)
        _, out, _ = run(["api", "upload-image", str(image), "--json"], capsys)
        payload = json.loads(out)
        assert payload["capability"] == "local_image_upload"
        assert payload["provider"] == "api_fallback"
        assert payload["image_hash"] == "fake_image_hash_1"
        assert payload["reused"] is False
        assert payload["fingerprint"].startswith("sha256:")

    def test_a_second_run_reuses_and_does_not_re_upload(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = write_png(project / "hero.png", 600, 600)
        run(["api", "upload-image", str(image)], capsys)
        code, out, _ = run(["api", "upload-image", str(image)], capsys)
        assert code == 0
        assert "not re-uploaded" in out
        assert len(sdk.image_uploads) == 1

    def test_the_upload_is_recorded_in_the_action_log(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = write_png(project / "hero.png", 600, 600)
        run(["api", "upload-image", str(image)], capsys)
        records = ActionLog(Workspace.locate(project)).read()
        assert records[-1].operation == "upload_image"
        assert records[-1].provider.value == "api_fallback"
        assert records[-1].resource_id == "fake_image_hash_1"

    def test_the_asset_manifest_is_written(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = write_png(project / "hero.png", 600, 600)
        run(["api", "upload-image", str(image)], capsys)
        store = AssetStore(Workspace.locate(project))
        assert store.lookup(probe_asset(image), "act_1234567890") is not None

    def test_a_missing_file_fails_cleanly(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(["api", "upload-image", str(project / "nope.png")], capsys)
        assert code == 1
        assert "not found" in err
        assert sdk.image_uploads == []

    def test_a_non_image_is_refused_before_any_upload(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = project / "notes.png"
        text.write_text("this is not an image")
        code, _, err = run(["api", "upload-image", str(text)], capsys)
        assert code == 1
        assert "cannot confirm" in err
        assert sdk.image_uploads == []

    def test_an_sdk_failure_surfaces_metas_error(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from conftest import FakeSdkError

        sdk.raise_on_image = FakeSdkError(
            "boom", {"error": {"code": 100, "message": "Invalid image file"}}
        )
        image = write_png(project / "hero.png", 600, 600)
        code, _, err = run(["api", "upload-image", str(image)], capsys)
        assert code == 1
        assert "Invalid image file" in err

    def test_no_account_is_refused_before_any_upload(
        self,
        sdk: Recorder,
        project: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("META_AD_ACCOUNT_ID")
        image = write_png(project / "hero.png", 600, 600)
        code, _, err = run(["api", "upload-image", str(image)], capsys)
        assert code == 1
        assert "--account" in err
        assert sdk.image_uploads == []

    def test_both_spellings_of_an_account_share_one_upload(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        image = write_png(project / "hero.png", 600, 600)
        run(["api", "upload-image", str(image), "--account", "1234567890"], capsys)
        code, out, _ = run(
            ["api", "upload-image", str(image), "--account", "act_1234567890"], capsys
        )
        assert code == 0
        assert "not re-uploaded" in out
        assert len(sdk.image_uploads) == 1


class TestUploadVideo:
    def test_uploads_waits_and_reports(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        video = project / "clip.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 512)
        code, out, _ = run(["api", "upload-video", str(video), "--timeout", "1"], capsys)
        assert code == 0
        assert "700000000000001" in out
        assert "processing: ready" in out

    def test_no_wait_skips_the_status_poll(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        video = project / "clip.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 512)
        run(["api", "upload-video", str(video), "--no-wait"], capsys)
        assert sdk.status_reads == []

    def test_dry_run_needs_no_credentials(
        self,
        project: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
        video = project / "clip.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 512)
        code, out, _ = run(["api", "upload-video", str(video), "--dry-run"], capsys)
        assert code == 0
        assert "DRY RUN" in out


class TestCreateCreative:
    def test_an_invalid_cta_is_a_usage_error_not_a_traceback(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(
            [
                "api",
                "create-creative",
                "--video",
                "--name",
                "angle-a video",
                "--page-id",
                "1111111111",
                "--video-id",
                "700000000000001",
                "--url",
                "https://acme.example.com/webinar",
                "--primary-text",
                "Friday afternoons, returned.",
                "--cta",
                "sign_up",
            ],
            capsys,
        )
        assert code == 2
        assert "sign_up" in err
        assert sdk.creatives == []

    def test_a_video_creative(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(
            [
                "api",
                "create-creative",
                "--video",
                "--name",
                "angle-a video",
                "--page-id",
                "1111111111",
                "--video-id",
                "700000000000001",
                "--url",
                "https://acme.example.com/webinar",
                "--primary-text",
                "Friday afternoons, returned.",
                "--headline",
                "Stop rebuilding the report",
                "--cta",
                "SIGN_UP",
            ],
            capsys,
        )
        assert code == 0
        assert "800000000000001" in out
        # A creative is inert; the output should say so rather than implying spend.
        assert "does not spend" in out
        assert sdk.creatives[0]["object_story_spec"]["video_data"]["video_id"] == (
            "700000000000001"
        )

    def test_an_existing_post_creative_preserves_engagement(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(
            [
                "api",
                "create-creative",
                "--post",
                "--name",
                "boost the launch post",
                "--post-id",
                "1111111111_2222222222",
            ],
            capsys,
        )
        assert code == 0
        assert sdk.creatives[0]["object_story_id"] == "1111111111_2222222222"
        assert "engagement preserved" in out

    def test_a_multi_variant_creative(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _out, _ = run(
            [
                "api",
                "create-creative",
                "--variants",
                "--name",
                "two angles",
                "--page-id",
                "1111111111",
                "--url",
                "https://acme.example.com",
                "--primary-text",
                "Body copy",
                "--headline",
                "A headline",
                "--image-hash",
                "h1",
                "--image-hash",
                "h2",
            ],
            capsys,
        )
        assert code == 0
        spec = sdk.creatives[0]["asset_feed_spec"]
        assert spec["images"] == [{"hash": "h1"}, {"hash": "h2"}]

    def test_the_creative_is_recorded_in_the_action_log(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(
            ["api", "create-creative", "--post", "--name", "n", "--post-id", "1_2"],
            capsys,
        )
        records = ActionLog(Workspace.locate(project)).read()
        assert records[-1].operation == "create_creative:existing_post"
        assert records[-1].resource_type == "creative"


class TestDelete:
    def test_deletion_requires_approval(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(
            ["api", "delete", "120", "--type", "ad", "--reason", "duplicate"], capsys
        )
        assert code == 2
        assert "--approved" in err
        assert "optimisation history" in err
        assert sdk.deletes == []

    def test_an_approved_deletion_of_a_paused_object_succeeds(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(
            [
                "api",
                "delete",
                "120210000000009",
                "--type",
                "ad",
                "--reason",
                "created by mistake, never delivered",
                "--approved",
            ],
            capsys,
        )
        assert code == 0
        assert sdk.deletes == ["ad:120210000000009"]
        assert "previous status  PAUSED" in out

    def test_an_active_object_is_refused_even_with_approval(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sdk.object_fields = {"name": "live ad", "status": "ACTIVE"}
        code, _, err = run(
            [
                "api",
                "delete",
                "120",
                "--type",
                "ad",
                "--reason",
                "cleanup",
                "--approved",
            ],
            capsys,
        )
        assert code == 1
        assert "Pause it first" in err
        assert sdk.deletes == []

    def test_a_dry_run_names_what_it_would_delete(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(
            [
                "api",
                "delete",
                "120",
                "--type",
                "campaign",
                "--reason",
                "duplicate",
                "--dry-run",
            ],
            capsys,
        )
        assert code == 0
        assert "DRY RUN" in out
        assert "irreversible" in out
        assert sdk.deletes == []

    def test_the_deletion_is_recorded_with_approval_noted(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(
            [
                "api",
                "delete",
                "120",
                "--type",
                "ad",
                "--reason",
                "duplicate",
                "--approved",
            ],
            capsys,
        )
        records = ActionLog(Workspace.locate(project)).read()
        assert records[-1].operation == "delete"
        assert records[-1].risk_level.value == "delete"
        assert records[-1].approval_noted is True
        assert records[-1].before == {"status": "PAUSED"}

    def test_the_deletion_names_the_account_it_came_from(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sdk.object_fields["account_id"] = "1234567890"
        run(["api", "delete", "120", "--type", "ad", "--reason", "dup", "--approved"], capsys)
        assert ActionLog(Workspace.locate(project)).read()[-1].ad_account_id == "act_1234567890"


class TestNewCreativeModes:
    """0.6: carousels, Instagram posts, placements, and several variants."""

    BASE = ["--page-id", "1111111111", "--url", "https://acme.example.com/webinar"]

    def test_a_carousel_from_a_cards_file(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cards = project / "cards.json"
        cards.write_text(
            json.dumps(
                [
                    {"image_hash": "abc123", "headline": "One"},
                    {"image_hash": "def456", "headline": "Two"},
                ]
            )
        )
        argv = ["api", "create-creative", "--carousel", "--name", "c", *self.BASE]
        code, _, err = run([*argv, "--primary-text", "Two reasons.", "--cards", str(cards)], capsys)
        assert code == 0, err
        spec = sdk.creatives[-1]["object_story_spec"]["link_data"]
        assert [a["image_hash"] for a in spec["child_attachments"]] == ["abc123", "def456"]
        assert spec["multi_share_optimized"] is False

    def test_a_one_card_carousel_is_refused_before_any_call(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cards = project / "cards.json"
        cards.write_text(json.dumps([{"image_hash": "abc123"}]))
        argv = ["api", "create-creative", "--carousel", "--name", "c", *self.BASE]
        code, _, err = run([*argv, "--primary-text", "x", "--cards", str(cards)], capsys)
        assert code == 1
        assert "2 to 10 cards" in err
        assert sdk.creatives == []

    def test_an_instagram_post(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["api", "create-creative", "--post", "--name", "ig"]
        code, _, err = run(
            [*argv, "--instagram-media-id", "17900000000000001", "--instagram-account-id", "2222"],
            capsys,
        )
        assert code == 0, err
        assert sdk.creatives[-1]["source_instagram_media_id"] == "17900000000000001"

    def test_an_instagram_post_needs_its_account(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["api", "create-creative", "--post", "--name", "ig"]
        code, _, err = run([*argv, "--instagram-media-id", "17900000000000001"], capsys)
        assert code == 1
        assert "Instagram account" in err
        assert sdk.creatives == []

    def test_several_variants_and_a_placement(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        variants = project / "variants.json"
        variants.write_text(
            json.dumps(
                [
                    {"angle": "time", "primary_text": "Friday back."},
                    {"angle": "risk", "primary_text": "No more errors."},
                ]
            )
        )
        argv = ["api", "create-creative", "--variants", "--name", "v", *self.BASE]
        code, _, err = run(
            [
                *argv,
                "--variants-file",
                str(variants),
                "--image-hash",
                "square",
                "--image-hash",
                "vertical",
                "--placement",
                "vertical=instagram_stories",
            ],
            capsys,
        )
        assert code == 0, err
        spec = sdk.creatives[-1]["asset_feed_spec"]
        assert [b["text"] for b in spec["bodies"]] == ["Friday back.", "No more errors."]
        assert len(spec["asset_customization_rules"]) == 2

    def test_pinning_every_asset_is_refused(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["api", "create-creative", "--variants", "--name", "v", *self.BASE]
        code, _, err = run(
            [
                *argv,
                "--primary-text",
                "x",
                "--image-hash",
                "only",
                "--placement",
                "only=instagram_reels",
            ],
            capsys,
        )
        assert code == 1
        assert "at least one asset unpinned" in err


class TestFailuresAndDryRunsAreLogged:
    """The log's job is to answer "what happened" - most of all after an error."""

    def test_a_failed_upload_is_recorded_as_failed(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from conftest import FakeSdkError

        sdk.raise_on_image = FakeSdkError(
            "boom", {"error": {"code": 100, "message": "Invalid image file"}}
        )
        image = write_png(project / "hero.png", 600, 600)
        assert run(["api", "upload-image", str(image)], capsys)[0] == 1
        (record,) = ActionLog(Workspace.locate(project)).read()
        assert record.result == "failed"
        assert record.operation == "upload_image"
        assert record.ad_account_id == "act_1234567890"
        assert "Invalid image file" in (record.detail or "")

    def test_a_dry_run_is_recorded_as_a_dry_run(
        self, project: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("META_AD_ACCOUNT_ID")
        image = write_png(project / "hero.png", 600, 600)
        assert run(["api", "upload-image", str(image), "--dry-run"], capsys)[0] == 0
        (record,) = ActionLog(Workspace.locate(project)).read()
        assert record.result == "dry_run"
        # The dry-run placeholder is not an account and is not logged as one.
        assert record.ad_account_id is None

    def test_a_refused_deletion_is_recorded(
        self, sdk: Recorder, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sdk.object_fields["status"] = "ACTIVE"
        run(["api", "delete", "120", "--type", "ad", "--reason", "dup", "--approved"], capsys)
        (record,) = ActionLog(Workspace.locate(project)).read()
        assert record.result == "failed"
        assert record.resource_id == "120"
        assert "ACTIVE" in (record.detail or "")
        assert sdk.deletes == []


class TestCapabilityGuard:
    def test_a_command_cannot_run_for_an_mcp_owned_capability(
        self,
        sdk: Recorder,
        project: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The CLI must not become a second path to MCP-owned work."""
        from meta_ads_agent.capabilities import Provider
        from meta_ads_agent.cli import api_cmd

        real_route = api_cmd.load_registry().route

        def pretend_mcp_owns_it(name: str, **kwargs: object):  # type: ignore[no-untyped-def]
            route = real_route(name, **kwargs)  # type: ignore[arg-type]
            return route.__class__(
                capability=route.capability,
                provider=Provider.OFFICIAL_MCP,
                risk_level=route.risk_level,
                requires_approval=route.requires_approval,
                reason="pretend the MCP covers this now",
            )

        monkeypatch.setattr(
            api_cmd.load_registry().__class__, "route", staticmethod(pretend_mcp_owns_it)
        )
        image = write_png(project / "hero.png", 600, 600)
        code, _, err = run(["api", "upload-image", str(image)], capsys)
        assert code == 1
        assert "Use the official MCP" in err
        assert sdk.image_uploads == []
