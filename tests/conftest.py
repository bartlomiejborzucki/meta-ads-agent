"""Shared fixtures.

No test in this directory talks to Meta. The SDK boundary is mocked, the HTTP
boundary is never reached, and every fixture uses a temporary directory.
Live tests live in ``tests/live/`` and are opt-in.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.validation import AccountContext
from meta_ads_agent.workspace import Workspace

# Obviously-fake credentials. Deliberately not shaped like real Meta tokens so
# a secret scanner does not flag the test suite, and so nobody can mistake one
# for a working value.
FAKE_TOKEN = "test-not-a-real-token-0000"
FAKE_APP_SECRET = "test-not-a-real-secret-0000"


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
