"""What only Meta can confirm: that the fallback's requests are accepted.

The five checks ``README.md`` lists, and nothing that the offline suite can
already verify. Nothing here is activated, nothing has a budget, and every
creative is inert - it spends nothing until an ad uses it and is activated.
Objects are named ``TEST_META_ADS_AGENT_*`` and are not deleted by the tests;
see the README for cleanup.

Every test here is marked ``live`` and skips unless all of the following are
set, so a default ``pytest`` run, and every CI run, reaches nothing:

* ``META_ADS_LIVE_TESTS=1`` - the explicit opt-in
* ``META_ADS_LIVE_TEST_ACCOUNT`` - a designated test ad account
* ``META_ACCESS_TOKEN`` - with ``ads_management`` on that account
* the real ``facebook-business`` SDK (the ``api`` extra)

Tests that need an identity also skip without it:
``META_ADS_LIVE_TEST_PAGE`` (a Page id), ``META_ADS_LIVE_TEST_POST`` (an
existing Page post id, ``<page>_<post>``), ``META_ADS_LIVE_TEST_IG_ACCOUNT``
and ``META_ADS_LIVE_TEST_IG_MEDIA`` (an Instagram account and one of its
posts).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import write_png
from meta_ads_agent.api.client import ApiClient, normalise_account_id
from meta_ads_agent.api.creatives import (
    CarouselCardSpec,
    create_carousel_creative,
    create_existing_post_creative,
    create_multi_variant_creative,
    create_video_creative,
)
from meta_ads_agent.api.media import upload_image, upload_video
from meta_ads_agent.models.plan import CopyVariant
from meta_ads_agent.state.assets import AssetStore
from meta_ads_agent.workspace import Workspace

# Marks every test in this file, so `-m "not live"` (CI) never collects one.
pytestmark = pytest.mark.live

PREFIX = "TEST_META_ADS_AGENT_"
DESTINATION = "https://www.example.com/"
VARIANT = CopyVariant(angle="live test", primary_text="Live test - not for delivery.")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"live test: {name} is not set")
    return value


@pytest.fixture(scope="session")
def live_account() -> str:
    if os.environ.get("META_ADS_LIVE_TESTS") != "1":
        pytest.skip("live tests are opt-in: set META_ADS_LIVE_TESTS=1 (tests/live/README.md)")
    pytest.importorskip("facebook_business", reason="live tests need the api extra")
    _require("META_ACCESS_TOKEN")
    return normalise_account_id(_require("META_ADS_LIVE_TEST_ACCOUNT"))


@pytest.fixture(scope="session")
def live_client(live_account: str) -> ApiClient:
    return ApiClient()


@pytest.fixture
def live_page() -> str:
    return _require("META_ADS_LIVE_TEST_PAGE")


@pytest.fixture
def live_post() -> str:
    return _require("META_ADS_LIVE_TEST_POST")


@pytest.fixture
def object_name() -> str:
    """Every object created is named so it is unmistakable in Ads Manager."""
    return f"{PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture
def live_store(tmp_path: Path) -> Iterator[AssetStore]:
    # A fresh manifest, so every run really uploads rather than reusing.
    workspace = Workspace.at(tmp_path / ".meta-ads")
    workspace.create()
    yield AssetStore(workspace)


def _mp4(path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("live video test: ffmpeg is needed to make a test clip")
    subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1080x1080:rate=30",
            "-t",
            "5",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture(scope="module")
def uploaded_image(
    live_client: ApiClient, live_account: str, tmp_path_factory: pytest.TempPathFactory
) -> str:
    directory = tmp_path_factory.mktemp("live-image")
    workspace = Workspace.at(directory / ".meta-ads")
    workspace.create()
    result = upload_image(
        write_png(directory / "live.png", 1080, 1080),
        live_account,
        client=live_client,
        store=AssetStore(workspace),
    )
    return result.remote_id


def test_a_local_image_upload_returns_a_usable_hash(uploaded_image: str) -> None:
    assert uploaded_image
    assert len(uploaded_image) >= 16


def test_a_local_video_upload_finishes_processing(
    live_client: ApiClient, live_account: str, live_store: AssetStore, tmp_path: Path
) -> None:
    result = upload_video(
        _mp4(tmp_path / "live.mp4"), live_account, client=live_client, store=live_store
    )
    assert result.remote_id
    assert "processing: ready" in result.detail.lower()


def test_a_video_creative_is_accepted(
    live_client: ApiClient,
    live_account: str,
    live_store: AssetStore,
    live_page: str,
    object_name: str,
    tmp_path: Path,
) -> None:
    video = upload_video(
        _mp4(tmp_path / "live.mp4"), live_account, client=live_client, store=live_store
    )
    created = create_video_creative(
        client=live_client,
        ad_account_id=live_account,
        name=object_name,
        page_id=live_page,
        video_id=video.remote_id,
        destination_url=DESTINATION,
        variant=VARIANT,
    )
    assert created.creative_id


def test_an_existing_post_creative_keeps_the_post(
    live_client: ApiClient, live_account: str, live_post: str, object_name: str
) -> None:
    from facebook_business.adobjects.adcreative import AdCreative

    created = create_existing_post_creative(
        client=live_client, ad_account_id=live_account, name=object_name, post_id=live_post
    )
    read = AdCreative(created.creative_id, api=live_client.connect()).api_get(
        fields=[AdCreative.Field.object_story_id]
    )
    assert read[AdCreative.Field.object_story_id] == live_post


def test_asset_feed_spec_is_accepted_in_the_shape_we_send(
    live_client: ApiClient, live_account: str, live_page: str, object_name: str, uploaded_image: str
) -> None:
    created = create_multi_variant_creative(
        client=live_client,
        ad_account_id=live_account,
        name=object_name,
        page_id=live_page,
        destination_url=DESTINATION,
        variants=[VARIANT, VARIANT.model_copy(update={"angle": "live test b"})],
        image_hashes=[uploaded_image],
    )
    assert created.creative_id


def test_a_carousel_is_accepted(
    live_client: ApiClient, live_account: str, live_page: str, object_name: str, uploaded_image: str
) -> None:
    created = create_carousel_creative(
        client=live_client,
        ad_account_id=live_account,
        name=object_name,
        page_id=live_page,
        destination_url=DESTINATION,
        primary_text=VARIANT.primary_text,
        cards=[
            CarouselCardSpec(image_hash=uploaded_image, headline="one"),
            CarouselCardSpec(image_hash=uploaded_image, headline="two"),
        ],
    )
    assert created.creative_id


def test_placement_customisation_rules_are_accepted(
    live_client: ApiClient,
    live_account: str,
    live_page: str,
    object_name: str,
    uploaded_image: str,
    tmp_path: Path,
) -> None:
    workspace = Workspace.at(tmp_path / ".meta-ads")
    workspace.create()
    vertical = upload_image(
        write_png(tmp_path / "vertical.png", 1080, 1920),
        live_account,
        client=live_client,
        store=AssetStore(workspace),
    ).remote_id
    created = create_multi_variant_creative(
        client=live_client,
        ad_account_id=live_account,
        name=object_name,
        page_id=live_page,
        destination_url=DESTINATION,
        variants=[VARIANT],
        image_hashes=[uploaded_image, vertical],
        placements={vertical: "instagram_stories"},
    )
    assert created.creative_id


def test_an_instagram_post_becomes_a_creative(
    live_client: ApiClient, live_account: str, live_page: str, object_name: str
) -> None:
    created = create_existing_post_creative(
        client=live_client,
        ad_account_id=live_account,
        name=object_name,
        instagram_media_id=_require("META_ADS_LIVE_TEST_IG_MEDIA"),
        instagram_account_id=_require("META_ADS_LIVE_TEST_IG_ACCOUNT"),
        page_id=live_page,
    )
    assert created.creative_id
