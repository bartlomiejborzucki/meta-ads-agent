"""Shared fixtures.

No test in this directory talks to Meta. The SDK boundary is mocked, the HTTP
boundary is never reached, and every fixture uses a temporary directory.
Live tests live in ``tests/live/`` and are opt-in.
"""

from __future__ import annotations

import struct
import sys
import types
import zlib
from pathlib import Path
from typing import Any

import pytest

from meta_ads_agent import envfile
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.validation import AccountContext
from meta_ads_agent.workspace import Workspace

# POSIX file semantics the tests check directly: owner-only modes, exec bits,
# unreadable files, a bare /usr/bin:/bin PATH. Windows has none of them, and
# the code under test does not claim otherwise - so on Windows these skip,
# with the reason, rather than fail for a property the platform lacks.
posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="checks a POSIX file property Windows does not have"
)

# Obviously-fake credentials. Deliberately not shaped like real Meta tokens so
# a secret scanner does not flag the test suite, and so nobody can mistake one
# for a working value.
FAKE_TOKEN = "test-not-a-real-token-0000"
FAKE_APP_SECRET = "test-not-a-real-secret-0000"


# The real loader, kept for tests of it; everywhere else it is a no-op, so a
# developer's own .env (with a real token) never reaches a test that runs the
# CLI from the repository.
REAL_DOTENV_APPLY = envfile.apply


@pytest.fixture(autouse=True)
def _no_developer_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(envfile, "apply", lambda directory=None: ())
    monkeypatch.setattr(envfile, "loaded_from", None)
    monkeypatch.setattr(envfile, "loaded_keys", ())


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """A fresh brand workspace in a temporary directory."""
    ws = Workspace.at(tmp_path / ".meta-ads")
    ws.create()
    return ws


@pytest.fixture
def spaced_workspace(tmp_path: Path) -> Workspace:
    """A workspace under a path containing spaces and non-ASCII characters.

    Paths like this are normal on Windows and macOS and routinely break tools
    that build shell strings.
    """
    project = tmp_path / "my projects" / "Acme Sp. z o.o. — kampanie"
    project.mkdir(parents=True)
    ws = Workspace.at(project / ".meta-ads")
    ws.create()
    return ws


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    """A real, valid 1200x628 PNG."""
    return write_png(tmp_path / "creative.png", 1200, 628)


@pytest.fixture
def tiny_png_file(tmp_path: Path) -> Path:
    """A valid but too-small PNG, to exercise the dimension warning."""
    return write_png(tmp_path / "tiny.png", 80, 80)


@pytest.fixture
def fake_mp4(tmp_path: Path) -> Path:
    """A file with a valid ISO base media header and no real video data.

    Enough for type detection. ffprobe will fail on it, which is the point:
    the probe must degrade to a warning rather than an error.
    """
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 512)
    return path


def write_png(path: Path, width: int, height: int) -> Path:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    rows = b"".join(b"\x00" + bytes([64, 128, 200]) * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    return path


def plan_dict(**overrides: Any) -> dict[str, Any]:
    """A minimal valid plan, as a dict, for mutation in tests."""
    base: dict[str, Any] = {
        "slug": "acme-webinar",
        "ad_account_id": "act_1234567890",
        "brand": "Acme",
        "offer": "webinar",
        "campaign": {
            "name": "Acme | OUTCOME_LEADS | 2026-09-16",
            "objective": "OUTCOME_LEADS",
            "dsa": {"beneficiary": "Acme Sp. z o.o.", "payor": "Acme Sp. z o.o."},
            "ad_sets": [
                {
                    "name": "PL broad 25-55",
                    "optimization_goal": "OFFSITE_CONVERSIONS",
                    "budget": {
                        "level": "ad_set",
                        "type": "daily",
                        "amount": "70",
                        "currency": "PLN",
                    },
                    "targeting": {"countries": ["PL"], "age_min": 25, "age_max": 55},
                    "tracking": {
                        "dataset_id": "1234567890",
                        "conversion_event": "LEAD",
                    },
                    "ads": [
                        {
                            "name": "angle-a",
                            "creative": {
                                "mode": "single_image",
                                "destination_url": "https://acme.example.com/webinar",
                                "page_id": "1111111111",
                                "assets": [{"image_hash": "abc123def456"}],
                                "variants": [
                                    {
                                        "angle": "time saved",
                                        "primary_text": "Friday afternoons, returned.",
                                        "headline": "Stop rebuilding the report",
                                        "cta_type": "SIGN_UP",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def plan() -> CampaignPlanDocument:
    return CampaignPlanDocument.model_validate(plan_dict())


@pytest.fixture
def account() -> AccountContext:
    """An account that satisfies every check, so a test can remove one thing."""
    return AccountContext(
        id="act_1234567890",
        name="Acme Ads",
        currency="PLN",
        currency_offset=100,
        timezone_name="Europe/Warsaw",
        account_status=1,
        has_payment_method=True,
        is_queryable=True,
        is_ads_mcp_enabled=True,
        available_page_ids=["1111111111"],
        available_instagram_account_ids=["2222222222"],
        available_dataset_ids=["1234567890"],
        available_conversion_events=["LEAD", "PURCHASE"],
    )


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
