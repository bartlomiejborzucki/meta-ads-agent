"""Graph API error responses, through the real SDK exception, into our errors.

``fixtures/graph_errors.json`` holds one response per code in the core
skill's error reference, in the shape Graph returns (``{"error": {...}}``)
and with the codes and subcodes as that reference lists them. Each is raised
as the SDK's own ``FacebookRequestError`` - not a fake - and must come out of
``wrap_sdk_error`` with its code, its subcode, Meta's most useful message, no
credential in the text, and a retry decision that matches the reference.

The retry rule under test is the reference's: a read may be retried on a
transient code; a write never is, whatever the code, because a failed write
may already have been applied.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from meta_ads_agent.api.client import TRANSIENT_CODES, wrap_sdk_error

errors = pytest.importorskip("facebook_business.exceptions", reason="needs the api extra")

FIXTURES: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "graph_errors.json").read_text(encoding="utf-8")
)
REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "meta-ads-core"
    / "references"
    / "meta-errors.md"
).read_text(encoding="utf-8")


def raised(name: str) -> Exception:
    fixture = FIXTURES[name]
    return errors.FacebookRequestError(
        "Call was not successful",
        {"method": "POST", "path": "/act_1234567890/adcreatives"},
        fixture["http_status"],
        {},
        json.dumps(fixture["body"]),
    )


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_code_and_subcode_survive(name: str) -> None:
    error = FIXTURES[name]["body"]["error"]
    wrapped = wrap_sdk_error(raised(name), stage="creatives_created", operation="create_x")
    assert wrapped.meta_code == error["code"]
    assert wrapped.meta_subcode == error.get("error_subcode")


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_a_failed_write_is_never_retry_safe(name: str) -> None:
    wrapped = wrap_sdk_error(raised(name), stage="creatives_created", operation="create_x")
    assert wrapped.retry_safe is False


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_a_failed_read_is_retry_safe_exactly_when_the_reference_says(name: str) -> None:
    wrapped = wrap_sdk_error(raised(name), stage="read_account", operation="get_account")
    assert wrapped.retry_safe is (FIXTURES[name]["kind"] == "transient")


def test_the_users_message_is_preferred_to_the_generic_one() -> None:
    wrapped = wrap_sdk_error(raised("invalid_budget"), stage="ad_sets_created", operation="x")
    assert "below the minimum" in str(wrapped)
    assert "Invalid parameter" not in str(wrapped)


def test_a_token_in_the_sdk_message_does_not_reach_ours() -> None:
    # A code with no error message of its own falls back to the SDK's text,
    # which can carry the request URL.
    body = {"error": {"code": 1, "type": "OAuthException"}}
    exc = errors.FacebookRequestError(
        "Call failed: https://graph.facebook.com/v26.0/me?access_token=EAAopaque0token0value00",
        {},
        500,
        {},
        json.dumps(body),
    )
    wrapped = wrap_sdk_error(exc, stage="read_account", operation="get_account")
    assert "EAAopaque0token0value00" not in str(wrapped)


def test_every_fixture_code_is_in_the_reference() -> None:
    """The fixtures are the reference's codes; neither may drift from the other."""
    for name, fixture in FIXTURES.items():
        error = fixture["body"]["error"]
        number = error.get("error_subcode") or error["code"]
        assert re.search(rf"\b{number}\b", REFERENCE), f"{name}: {number} is not in meta-errors.md"


def test_transient_codes_are_the_references_retryable_ones() -> None:
    transient = {f["body"]["error"]["code"] for f in FIXTURES.values() if f["kind"] == "transient"}
    assert transient == set(TRANSIENT_CODES)
