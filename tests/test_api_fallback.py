"""The Marketing API fallback, with the SDK boundary mocked.

No test here reaches the network. A fake ``facebook_business`` package is
installed into ``sys.modules`` so the fallback's own logic - dedup, ordering,
retry-safety, dry-run - is what gets exercised.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from conftest import FAKE_TOKEN
from meta_ads_agent.api.client import (
    TRANSIENT_CODES,
    ApiClient,
    Credentials,
    wrap_sdk_error,
)
from meta_ads_agent.api.version import (
    DEFAULT_GRAPH_API_VERSION,
    ENV_VAR,
    graph_api_version,
    is_probably_unsupported,
    version_tuple,
)
from meta_ads_agent.errors import (
    ApiCallFailed,
    ApiFallbackUnavailable,
    DryRun,
    ValidationError,
)
from meta_ads_agent.state.assets import AssetStore, probe_asset
from meta_ads_agent.workspace import Workspace


# ---------------------------------------------------------------------------
# A minimal fake SDK
# ---------------------------------------------------------------------------
class FakeSdkError(Exception):
    """Stands in for FacebookRequestError, which exposes ``body()``."""

    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self._payload = payload or {}

    def body(self) -> dict[str, Any]:
        return self._payload


class Recorder:
    """Captures what the fallback asked the SDK to do."""

    def __init__(self) -> None:
        self.image_uploads: list[str] = []
        self.video_uploads: list[str] = []
        self.creatives: list[dict[str, Any]] = []
        self.deletes: list[str] = []
        self.status_reads: list[str] = []
        self.video_status = "ready"
        self.raise_on_image: Exception | None = None
        self.raise_on_video: Exception | None = None
        self.image_hash: str | None = "fake_image_hash_1"
        self.video_id: str | None = "700000000000001"
        self.creative_id: str | None = "800000000000001"
        self.object_fields: dict[str, Any] = {"name": "an ad", "status": "PAUSED"}


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Install a fake ``facebook_business`` package for the duration of a test."""
    recorder = Recorder()

    root = types.ModuleType("facebook_business")
    root.__version__ = "26.0.1-fake"  # type: ignore[attr-defined]
    api_module = types.ModuleType("facebook_business.api")
    objects = types.ModuleType("facebook_business.adobjects")

    class FacebookAdsApi:
        last_init: dict[str, Any] = {}

        @classmethod
        def init(cls, **kwargs: Any) -> FacebookAdsApi:
            cls.last_init = kwargs
            return cls()

    api_module.FacebookAdsApi = FacebookAdsApi  # type: ignore[attr-defined]

    class AdImage:
        class Field:
            filename = "filename"
            hash = "hash"

        def __init__(self, parent_id: str | None = None, api: Any = None) -> None:
            self.parent_id = parent_id
            self._data: dict[str, Any] = {}

        def __setitem__(self, key: str, value: Any) -> None:
            self._data[key] = value

        def __getitem__(self, key: str) -> Any:
            return self._data.get(key)

        def remote_create(self) -> None:
            if recorder.raise_on_image:
                raise recorder.raise_on_image
            recorder.image_uploads.append(self._data["filename"])
            self._data["hash"] = recorder.image_hash

    class AdVideo:
        class Field:
            filepath = "filepath"

        def __init__(
            self, object_id: str | None = None, api: Any = None, parent_id: str | None = None
        ) -> None:
            self.object_id = object_id
            self.parent_id = parent_id
            self._data: dict[str, Any] = {}

        def __setitem__(self, key: str, value: Any) -> None:
            self._data[key] = value

        def remote_create(self) -> None:
            if recorder.raise_on_video:
                raise recorder.raise_on_video
            recorder.video_uploads.append(self._data["filepath"])

        def get_id(self) -> str | None:
            return recorder.video_id

        def api_get(self, fields: list[str] | None = None) -> dict[str, Any]:
            recorder.status_reads.append(self.object_id or "")
            return {"status": {"video_status": recorder.video_status}}

        def get_thumbnails(self, fields: list[str] | None = None) -> list[dict[str, Any]]:
            return [{"uri": "https://scontent.example.com/thumb.jpg", "is_preferred": True}]

    class _Created:
        def __init__(self, object_id: str | None) -> None:
            self._id = object_id

        def get_id(self) -> str | None:
            return self._id

    class AdAccount:
        def __init__(self, account_id: str, api: Any = None) -> None:
            self.account_id = account_id

        def get_id_assured(self) -> str:
            return self.account_id

        def create_ad_creative(self, params: dict[str, Any]) -> _Created:
            recorder.creatives.append(params)
            return _Created(recorder.creative_id)

    def _deletable(name: str) -> type:
        class Deletable:
            def __init__(self, object_id: str, api: Any = None) -> None:
                self.object_id = object_id

            def api_get(self, fields: list[str] | None = None) -> dict[str, Any]:
                return dict(recorder.object_fields)

            def api_delete(self) -> None:
                recorder.deletes.append(f"{name}:{self.object_id}")

        return Deletable

    submodules = {
        "facebook_business": root,
        "facebook_business.api": api_module,
        "facebook_business.adobjects": objects,
        "facebook_business.adobjects.adimage": _module("adimage", AdImage=AdImage),
        "facebook_business.adobjects.advideo": _module("advideo", AdVideo=AdVideo),
        "facebook_business.adobjects.adaccount": _module("adaccount", AdAccount=AdAccount),
        "facebook_business.adobjects.campaign": _module(
            "campaign", Campaign=_deletable("campaign")
        ),
        "facebook_business.adobjects.adset": _module("adset", AdSet=_deletable("ad_set")),
        "facebook_business.adobjects.ad": _module("ad", Ad=_deletable("ad")),
    }
    for name, module in submodules.items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.setenv("META_ACCESS_TOKEN", FAKE_TOKEN)
    monkeypatch.delenv("META_APP_ID", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    return recorder


def _module(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(f"facebook_business.adobjects.{name}")
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


# ---------------------------------------------------------------------------


class TestGraphApiVersion:
    def test_default_is_the_tested_version(self) -> None:
        assert graph_api_version() == DEFAULT_GRAPH_API_VERSION

    def test_environment_overrides_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_VAR, "v27.0")
        assert graph_api_version() == "v27.0"

    def test_an_explicit_argument_wins_over_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_VAR, "v27.0")
        assert graph_api_version("v25.0") == "v25.0"

    @pytest.mark.parametrize("bad", ["26.0", "v26", "latest", "v26.0.1", ""])
    def test_malformed_versions_are_rejected(
        self, bad: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_VAR, bad)
        if bad == "":
            assert graph_api_version() == DEFAULT_GRAPH_API_VERSION
        else:
            with pytest.raises(ValueError, match="not a Graph API version"):
                graph_api_version()

    def test_version_ordering(self) -> None:
        assert version_tuple("v26.0") > version_tuple("v24.0")
        assert version_tuple("v9.0") < version_tuple("v10.0")

    def test_ancient_versions_are_flagged(self) -> None:
        assert is_probably_unsupported("v18.0") is True
        assert is_probably_unsupported(DEFAULT_GRAPH_API_VERSION) is False

    def test_the_version_is_passed_to_the_sdk(self, sdk: Recorder) -> None:
        from facebook_business.api import FacebookAdsApi  # type: ignore[import-not-found]

        ApiClient(api_version="v25.0").connect()
        assert FacebookAdsApi.last_init["api_version"] == "v25.0"

    def test_an_unsupported_version_refuses_to_connect(
        self, sdk: Recorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_VAR, "v18.0")
        with pytest.raises(ApiFallbackUnavailable, match="older than"):
            ApiClient().connect()


class TestCredentials:
    def test_a_missing_token_explains_that_it_is_optional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
        with pytest.raises(ApiFallbackUnavailable, match="only need this"):
            Credentials.from_env()

    def test_the_summary_never_shows_the_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_ACCESS_TOKEN", FAKE_TOKEN)
        described = Credentials.from_env().describe()
        assert FAKE_TOKEN not in repr(described)
        assert described["META_ACCESS_TOKEN"].startswith("sha256:")

    def test_the_sdk_being_absent_explains_the_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_ACCESS_TOKEN", FAKE_TOKEN)
        monkeypatch.setitem(sys.modules, "facebook_business.api", None)
        with pytest.raises(ApiFallbackUnavailable, match=r"meta-ads-agent\[api\]"):
            ApiClient().connect()

    def test_an_account_without_the_act_prefix_is_normalised(self, sdk: Recorder) -> None:
        assert ApiClient().account("1234567890").account_id == "act_1234567890"

    def test_no_account_anywhere_is_reported(self, sdk: Recorder) -> None:
        with pytest.raises(ApiFallbackUnavailable, match="No ad account given"):
            ApiClient().account(None)


class TestErrorWrapping:
    def test_metas_error_code_is_preserved(self) -> None:
        wrapped = wrap_sdk_error(
            FakeSdkError(
                "bad request",
                {"error": {"code": 100, "error_subcode": 1487036, "message": "Invalid field"}},
            ),
            stage="creatives_created",
            operation="create_video_creative",
        )
        assert wrapped.meta_code == 100
        assert wrapped.meta_subcode == 1487036
        assert "Invalid field" in str(wrapped)
        assert wrapped.stage == "creatives_created"

    def test_a_write_is_never_marked_retry_safe(self) -> None:
        # A timeout does not tell you whether Meta created the object.
        for code in TRANSIENT_CODES:
            wrapped = wrap_sdk_error(
                FakeSdkError("transient", {"error": {"code": code}}),
                stage="ads_created",
                operation="create_ad",
            )
            assert wrapped.retry_safe is False

    def test_a_transient_read_is_retry_safe(self) -> None:
        wrapped = wrap_sdk_error(
            FakeSdkError("throttled", {"error": {"code": 4}}),
            stage="read_account",
            operation="get_account",
        )
        assert wrapped.retry_safe is True

    def test_a_non_transient_read_is_not_retry_safe(self) -> None:
        wrapped = wrap_sdk_error(
            FakeSdkError("expired", {"error": {"code": 190}}),
            stage="read_account",
            operation="get_account",
        )
        assert wrapped.retry_safe is False

    def test_a_credential_in_an_error_message_is_redacted(self) -> None:
        leaky = FakeSdkError(f"call failed for access_token=EAAleak{'x' * 20}")
        assert "EAAleak" not in str(
            wrap_sdk_error(leaky, stage="ads_created", operation="create_ad")
        )

    def test_an_unparseable_error_body_does_not_raise(self) -> None:
        class Weird(Exception):
            def body(self) -> Any:
                raise RuntimeError("nope")

        wrapped = wrap_sdk_error(Weird("odd"), stage="x", operation="create_ad")
        assert isinstance(wrapped, ApiCallFailed)


class TestImageUpload:
    def test_uploads_and_records_the_hash(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        result = upload_image(
            png_file, "act_1234567890", client=ApiClient(), store=AssetStore(workspace)
        )
        assert result.reused is False
        assert result.remote_id == "fake_image_hash_1"
        assert sdk.image_uploads == [str(png_file)]

    def test_a_second_upload_of_the_same_bytes_is_skipped(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        store = AssetStore(workspace)
        upload_image(png_file, "act_1234567890", client=ApiClient(), store=store)
        again = upload_image(png_file, "act_1234567890", client=ApiClient(), store=store)
        assert again.reused is True
        assert again.remote_id == "fake_image_hash_1"
        assert len(sdk.image_uploads) == 1
        assert "skipped re-upload" in again.detail

    def test_the_same_bytes_under_a_new_name_are_also_skipped(
        self, sdk: Recorder, workspace: Workspace, tmp_path: Path
    ) -> None:
        from conftest import write_png
        from meta_ads_agent.api.media import upload_image

        store = AssetStore(workspace)
        first = write_png(tmp_path / "one.png", 400, 400)
        upload_image(first, "act_1234567890", client=ApiClient(), store=store)
        second = write_png(tmp_path / "two.png", 400, 400)
        assert (
            upload_image(second, "act_1234567890", client=ApiClient(), store=store).reused is True
        )
        assert len(sdk.image_uploads) == 1

    def test_another_account_uploads_again(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        store = AssetStore(workspace)
        upload_image(png_file, "act_1234567890", client=ApiClient(), store=store)
        sdk.image_hash = "fake_image_hash_2"
        assert (
            upload_image(png_file, "act_9999999999", client=ApiClient(), store=store).reused
            is False
        )
        assert len(sdk.image_uploads) == 2

    def test_a_dry_run_needs_no_client(self, workspace: Workspace, png_file: Path) -> None:
        from meta_ads_agent.api.media import upload_image

        with pytest.raises(DryRun, match="would upload image"):
            upload_image(
                png_file,
                "act_1234567890",
                client=None,
                store=AssetStore(workspace),
                dry_run=True,
            )

    def test_a_dry_run_reports_a_cached_asset_instead_of_pretending_to_upload(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        store = AssetStore(workspace)
        upload_image(png_file, "act_1234567890", client=ApiClient(), store=store)
        result = upload_image(png_file, "act_1234567890", client=None, store=store, dry_run=True)
        assert result.reused is True

    def test_a_missing_hash_is_a_hard_failure_not_a_silent_success(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        sdk.image_hash = None
        with pytest.raises(ApiCallFailed, match="returned no hash"):
            upload_image(
                png_file, "act_1234567890", client=ApiClient(), store=AssetStore(workspace)
            )

    def test_an_sdk_failure_is_wrapped_with_its_stage(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        sdk.raise_on_image = FakeSdkError("boom", {"error": {"code": 100}})
        with pytest.raises(ApiCallFailed) as caught:
            upload_image(
                png_file, "act_1234567890", client=ApiClient(), store=AssetStore(workspace)
            )
        assert caught.value.stage == "assets_uploaded"
        assert caught.value.retry_safe is False

    def test_nothing_is_recorded_when_the_upload_fails(
        self, sdk: Recorder, workspace: Workspace, png_file: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_image

        sdk.raise_on_image = FakeSdkError("boom")
        store = AssetStore(workspace)
        with pytest.raises(ApiCallFailed):
            upload_image(png_file, "act_1234567890", client=ApiClient(), store=store)
        assert store.lookup(probe_asset(png_file), "act_1234567890") is None


class TestVideoUpload:
    def test_uploads_waits_for_processing_and_records_the_id(
        self, sdk: Recorder, workspace: Workspace, fake_mp4: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_video

        result = upload_video(
            fake_mp4,
            "act_1234567890",
            client=ApiClient(),
            store=AssetStore(workspace),
            sleep=lambda _s: None,
        )
        assert result.remote_id == "700000000000001"
        assert sdk.video_uploads == [str(fake_mp4)]
        assert sdk.status_reads == ["700000000000001"]
        assert "processing: ready" in result.detail

    def test_a_retry_does_not_re_upload(
        self, sdk: Recorder, workspace: Workspace, fake_mp4: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_video

        store = AssetStore(workspace)
        upload_video(
            fake_mp4, "act_1234567890", client=ApiClient(), store=store, sleep=lambda _s: None
        )
        again = upload_video(
            fake_mp4, "act_1234567890", client=ApiClient(), store=store, sleep=lambda _s: None
        )
        assert again.reused is True
        assert len(sdk.video_uploads) == 1

    def test_the_id_is_recorded_before_waiting_so_a_timeout_does_not_cause_a_re_upload(
        self, sdk: Recorder, workspace: Workspace, fake_mp4: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_video

        sdk.video_status = "processing"
        store = AssetStore(workspace)
        with pytest.raises(ApiCallFailed, match="still processing"):
            upload_video(
                fake_mp4,
                "act_1234567890",
                client=ApiClient(),
                store=store,
                sleep=lambda _s: None,
                timeout_seconds=0,
            )
        # The bytes reached Meta, so the manifest must already know.
        assert store.lookup(probe_asset(fake_mp4), "act_1234567890").video_id == ("700000000000001")

    def test_a_timeout_is_retry_safe_because_only_the_wait_failed(
        self, sdk: Recorder, workspace: Workspace, fake_mp4: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_video

        sdk.video_status = "processing"
        with pytest.raises(ApiCallFailed) as caught:
            upload_video(
                fake_mp4,
                "act_1234567890",
                client=ApiClient(),
                store=AssetStore(workspace),
                sleep=lambda _s: None,
                timeout_seconds=0,
            )
        assert caught.value.retry_safe is True

    def test_a_processing_error_is_reported_as_unusable(
        self, sdk: Recorder, workspace: Workspace, fake_mp4: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_video

        sdk.video_status = "error"
        with pytest.raises(ApiCallFailed, match="cannot be used"):
            upload_video(
                fake_mp4,
                "act_1234567890",
                client=ApiClient(),
                store=AssetStore(workspace),
                sleep=lambda _s: None,
            )

    def test_no_wait_skips_the_status_poll(
        self, sdk: Recorder, workspace: Workspace, fake_mp4: Path
    ) -> None:
        from meta_ads_agent.api.media import upload_video

        upload_video(
            fake_mp4,
            "act_1234567890",
            client=ApiClient(),
            store=AssetStore(workspace),
            wait=False,
        )
        assert sdk.status_reads == []

    def test_a_dry_run_needs_no_client(self, workspace: Workspace, fake_mp4: Path) -> None:
        from meta_ads_agent.api.media import upload_video

        with pytest.raises(DryRun, match="would upload video"):
            upload_video(
                fake_mp4,
                "act_1234567890",
                client=None,
                store=AssetStore(workspace),
                dry_run=True,
            )


class TestCreatives:
    def test_a_video_creative_uses_video_data_and_a_thumbnail(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.creatives import create_video_creative
        from meta_ads_agent.models.plan import CopyVariant

        result = create_video_creative(
            client=ApiClient(),
            ad_account_id="act_1234567890",
            name="angle-a video",
            page_id="1111111111",
            video_id="700000000000001",
            destination_url="https://acme.example.com/webinar",
            variant=CopyVariant(
                angle="time saved",
                primary_text="Fridays, returned.",
                headline="Stop rebuilding the report",
                cta_type="SIGN_UP",
            ),
        )
        assert result.creative_id == "800000000000001"
        spec = sdk.creatives[0]["object_story_spec"]
        assert spec["page_id"] == "1111111111"
        assert spec["video_data"]["video_id"] == "700000000000001"
        assert spec["video_data"]["call_to_action"]["type"] == "SIGN_UP"
        assert spec["video_data"]["image_url"].startswith("https://")
        assert "Business SDK fallback" in result.detail

    def test_an_explicit_thumbnail_hash_is_used_instead_of_a_generated_one(
        self, sdk: Recorder
    ) -> None:
        from meta_ads_agent.api.creatives import create_video_creative
        from meta_ads_agent.models.plan import CopyVariant

        create_video_creative(
            client=ApiClient(),
            ad_account_id="act_1234567890",
            name="v",
            page_id="1111111111",
            video_id="700000000000001",
            destination_url="https://acme.example.com",
            variant=CopyVariant(angle="a", primary_text="t"),
            thumbnail_hash="thumb_hash_1",
        )
        video_data = sdk.creatives[0]["object_story_spec"]["video_data"]
        assert video_data["image_hash"] == "thumb_hash_1"
        assert "image_url" not in video_data

    def test_an_existing_post_creative_references_the_real_post(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.creatives import create_existing_post_creative

        result = create_existing_post_creative(
            client=ApiClient(),
            ad_account_id="act_1234567890",
            name="boost the launch post",
            post_id="1111111111_2222222222",
        )
        # object_story_id preserves the post's engagement; a dark post would not.
        assert sdk.creatives[0]["object_story_id"] == "1111111111_2222222222"
        assert "engagement preserved" in result.detail
        assert "object_story_spec" not in sdk.creatives[0]

    def test_multi_variant_builds_an_asset_feed_spec(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.creatives import create_multi_variant_creative
        from meta_ads_agent.models.plan import CopyVariant

        create_multi_variant_creative(
            client=ApiClient(),
            ad_account_id="act_1234567890",
            name="three angles",
            page_id="1111111111",
            destination_url="https://acme.example.com",
            variants=[
                CopyVariant(angle="time", primary_text="A", headline="Ah", cta_type="SIGN_UP"),
                CopyVariant(angle="risk", primary_text="B", headline="Bh"),
            ],
            image_hashes=["h1", "h2"],
        )
        spec = sdk.creatives[0]["asset_feed_spec"]
        assert [b["text"] for b in spec["bodies"]] == ["A", "B"]
        assert [t["text"] for t in spec["titles"]] == ["Ah", "Bh"]
        assert spec["images"] == [{"hash": "h1"}, {"hash": "h2"}]
        assert spec["ad_formats"] == ["SINGLE_IMAGE"]

    def test_multi_variant_with_no_assets_is_rejected(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.creatives import create_multi_variant_creative
        from meta_ads_agent.models.plan import CopyVariant

        with pytest.raises(ValidationError, match="at least one image or video"):
            create_multi_variant_creative(
                client=ApiClient(),
                ad_account_id="act_1234567890",
                name="n",
                page_id="1",
                destination_url="https://x.example.com",
                variants=[CopyVariant(angle="a", primary_text="t")],
            )

    def test_a_missing_creative_id_is_a_hard_failure(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.creatives import create_existing_post_creative

        sdk.creative_id = None
        with pytest.raises(ApiCallFailed, match="returned no creative id"):
            create_existing_post_creative(
                client=ApiClient(),
                ad_account_id="act_1234567890",
                name="n",
                post_id="1_2",
            )

    def test_dry_runs_create_nothing(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.creatives import create_existing_post_creative

        with pytest.raises(DryRun, match="not modified"):
            create_existing_post_creative(
                client=None,
                ad_account_id="act_1234567890",
                name="n",
                post_id="1_2",
                dry_run=True,
            )
        assert sdk.creatives == []


class TestDeletion:
    def test_a_paused_object_is_deleted_with_its_reason_recorded(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.deletion import DeletableType, delete_object

        result = delete_object(
            client=ApiClient(),
            object_id="120210000000009",
            object_type=DeletableType.AD,
            reason="created by mistake, never delivered, no history worth keeping",
        )
        assert sdk.deletes == ["ad:120210000000009"]
        assert result.previous_status == "PAUSED"
        assert "no history worth keeping" in result.detail

    def test_an_active_object_is_refused(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.deletion import DeletableType, delete_object

        sdk.object_fields = {"name": "live ad", "status": "ACTIVE"}
        with pytest.raises(ValidationError, match="Pause it first"):
            delete_object(
                client=ApiClient(),
                object_id="120210000000009",
                object_type=DeletableType.AD,
                reason="cleanup",
            )
        assert sdk.deletes == []

    def test_an_empty_reason_is_refused(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.deletion import DeletableType, delete_object

        with pytest.raises(ValidationError, match="optimisation history"):
            delete_object(
                client=ApiClient(),
                object_id="1",
                object_type=DeletableType.AD,
                reason="   ",
            )

    def test_a_dry_run_names_what_it_would_delete(self, sdk: Recorder) -> None:
        from meta_ads_agent.api.deletion import DeletableType, delete_object

        with pytest.raises(DryRun) as caught:
            delete_object(
                client=ApiClient(),
                object_id="120210000000009",
                object_type=DeletableType.AD,
                reason="duplicate of another ad",
                dry_run=True,
            )
        assert "an ad" in str(caught.value)
        assert "irreversible" in str(caught.value)
        assert sdk.deletes == []

    @pytest.mark.parametrize("kind", ["campaign", "ad_set", "ad"])
    def test_every_deletable_type_is_supported(self, sdk: Recorder, kind: str) -> None:
        from meta_ads_agent.api.deletion import DeletableType, delete_object

        delete_object(
            client=ApiClient(),
            object_id="120",
            object_type=DeletableType(kind),
            reason="test",
        )
        assert sdk.deletes == [f"{kind}:120"]
