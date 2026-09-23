"""The fallback's requests, checked against the real ``facebook-business`` SDK.

Every other fallback test runs against a fake SDK, which accepts whatever it
is given - so a misspelt field, a field on the wrong object, or a
call-to-action Meta does not have would pass all of them and fail on the
first real call. The SDK ships Meta's own description of each object: the
fields it has (``Field``), their types (``_field_types``), and the allowed
values of its enums (``_get_field_enum_info``). This module holds every
request the fallback builds up to that description.

It does not prove Meta accepts a request - only a live call can - but it
removes the class of error a live call would otherwise be the first to find.

Needs the ``api`` extra. The real classes are loaded when this module is
imported, before the ``sdk`` fixture swaps in the fake.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import Recorder
from meta_ads_agent.api.client import ApiClient
from meta_ads_agent.api.creatives import (
    create_existing_post_creative,
    create_multi_variant_creative,
    create_video_creative,
)
from meta_ads_agent.models.plan import CopyVariant

pytest.importorskip("facebook_business", reason="needs the api extra (facebook-business)")

SRC = Path(__file__).resolve().parents[1] / "src" / "meta_ads_agent"
_LIST = re.compile(r"^list<(.+)>$")


def _load(name: str) -> type[Any] | None:
    try:
        module = importlib.import_module(f"facebook_business.adobjects.{name.lower()}")
    except ImportError:
        return None
    return getattr(module, name, None)


def _graph(root: str) -> dict[str, type[Any]]:
    """Every SDK class reachable from *root* through its field types."""
    classes: dict[str, type[Any]] = {}
    pending = [root]
    while pending:
        name = pending.pop()
        if name in classes:
            continue
        cls = _load(name)
        if cls is None:
            continue
        classes[name] = cls
        for kind in getattr(cls, "_field_types", {}).values():
            inner = _LIST.match(kind)
            pending.append(inner.group(1) if inner else kind)
    return classes


CLASSES = _graph("AdCreative")
REAL = {name: _load(name) for name in ("AdImage", "AdVideo", "Campaign", "AdSet", "Ad")}


def violations(value: Any, kind: str, path: str, owner: type[Any] | None = None) -> list[str]:
    """Where *value* does not fit SDK type *kind*. Empty means it fits."""
    inner = _LIST.match(kind)
    if inner:
        if not isinstance(value, list):
            return [f"{path}: expected a list for {kind}, got {type(value).__name__}"]
        return [
            p
            for i, item in enumerate(value)
            for p in violations(item, inner.group(1), f"{path}[{i}]", owner)
        ]
    enums = owner._get_field_enum_info() if owner is not None else {}
    if kind in enums:
        return [] if value in enums[kind] else [f"{path}: {value!r} is not a {kind} value"]
    if kind in CLASSES:
        return check(value, kind, path)
    if kind == "string" and not isinstance(value, str):
        return [f"{path}: expected a string, got {type(value).__name__}"]
    # Other scalars, and types this walk does not model, are not asserted.
    return []


def check(params: Any, class_name: str, path: str = "") -> list[str]:
    cls = CLASSES[class_name]
    if not isinstance(params, dict):
        return [f"{path or class_name}: expected an object for {class_name}"]
    types = cls._field_types
    out: list[str] = []
    for key, value in params.items():
        where = f"{path}.{key}" if path else key
        if key not in types:
            out.append(f"{where}: {class_name} has no field {key!r}")
            continue
        out.extend(violations(value, types[key], where, cls))
    return out


class TestTheCheckerItself:
    """A checker that passes everything is worse than none."""

    def test_an_unknown_field_is_caught(self) -> None:
        assert check({"object_story_spec": {"page_idd": "1"}}, "AdCreative") == [
            "object_story_spec.page_idd: AdCreativeObjectStorySpec has no field 'page_idd'"
        ]

    def test_an_unknown_call_to_action_is_caught(self) -> None:
        spec = {"video_data": {"call_to_action": {"type": "SIGN_UP_NOW"}}}
        (problem,) = check({"object_story_spec": spec}, "AdCreative")
        assert "'SIGN_UP_NOW' is not a Type value" in problem

    def test_a_list_field_given_a_scalar_is_caught(self) -> None:
        (problem,) = check({"asset_feed_spec": {"bodies": "text"}}, "AdCreative")
        assert "expected a list" in problem


def _client(sdk: Recorder) -> ApiClient:
    # The fixture is what makes ApiClient build against the fake SDK.
    return ApiClient()


VARIANT = CopyVariant(
    angle="time saved",
    primary_text="Friday afternoons, returned.",
    headline="Stop rebuilding the report",
    description="A 40-minute walkthrough",
    cta_type="SIGN_UP",
)


class TestCreativeRequests:
    def test_a_video_creative(self, sdk: Recorder) -> None:
        create_video_creative(
            client=_client(sdk),
            ad_account_id="act_1234567890",
            name="angle-a video",
            page_id="1111111111",
            video_id="700000000000001",
            destination_url="https://acme.example.com/webinar",
            variant=VARIANT,
            thumbnail_hash="abc123",
            instagram_account_id="2222222222",
        )
        assert check(sdk.creatives[-1], "AdCreative") == []

    def test_an_existing_post_creative(self, sdk: Recorder) -> None:
        create_existing_post_creative(
            client=_client(sdk),
            ad_account_id="act_1234567890",
            name="promote the post",
            post_id="1111111111_3333333333",
            instagram_account_id="2222222222",
        )
        assert check(sdk.creatives[-1], "AdCreative") == []

    @pytest.mark.parametrize("media", ["images", "videos"])
    def test_a_multi_variant_creative(self, sdk: Recorder, media: str) -> None:
        second = VARIANT.model_copy(update={"angle": "error risk", "cta_type": "LEARN_MORE"})
        create_multi_variant_creative(
            client=_client(sdk),
            ad_account_id="act_1234567890",
            name="variants",
            page_id="1111111111",
            destination_url="https://acme.example.com/webinar",
            variants=[VARIANT, second],
            image_hashes=["abc123"] if media == "images" else None,
            video_ids=["700000000000001"] if media == "videos" else None,
        )
        assert check(sdk.creatives[-1], "AdCreative") == []


class TestFieldNamesUsedInCode:
    """``X.Field.y`` and ``fields=[...]`` in the fallback, against the real classes."""

    def test_every_field_constant_exists(self) -> None:
        missing = []
        for path in sorted((SRC / "api").glob("*.py")):
            for cls, field in re.findall(r"\b(\w+)\.Field\.(\w+)", path.read_text()):
                real = REAL.get(cls)
                assert real is not None, f"{path.name}: {cls} is not a class this test loads"
                if not hasattr(real.Field, field):
                    missing.append(f"{path.name}: {cls}.Field.{field}")
        assert missing == []

    @pytest.mark.parametrize("cls", ["Campaign", "AdSet", "Ad"])
    def test_the_pre_delete_read_asks_for_real_fields(self, cls: str) -> None:
        text = (SRC / "api" / "deletion.py").read_text()
        (fields,) = re.findall(r"api_get\(fields=\[([^\]]+)\]", text)
        names = re.findall(r'"(\w+)"', fields)
        real = REAL[cls]
        assert real is not None
        assert [n for n in names if not hasattr(real.Field, n)] == []

    def test_the_video_status_read_asks_for_a_real_field(self) -> None:
        real = REAL["AdVideo"]
        assert real is not None
        assert hasattr(real.Field, "status")
