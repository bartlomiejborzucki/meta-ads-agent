"""Secret redaction.

The last line of defence before anything reaches a log, an error message, or a
state file. Code should not be putting credentials in messages at all - these
tests cover the case where it does.
"""

from __future__ import annotations

import pytest

from meta_ads_agent.redaction import (
    MASK,
    fingerprint,
    redact,
    redact_mapping,
    redact_url,
)

# Shaped like real credentials but obviously synthetic.
LOOKS_LIKE_META_TOKEN = "EAA" + "GZc9fake0Token0Value0000"
LOOKS_LIKE_APP_SECRET = "123456789012345|abcdef0123456789_fakeSecret"


class TestRedactStrings:
    @pytest.mark.parametrize(
        "text",
        [
            f"access_token={LOOKS_LIKE_META_TOKEN}",
            f'"access_token": "{LOOKS_LIKE_META_TOKEN}"',
            f"ACCESS_TOKEN = {LOOKS_LIKE_META_TOKEN}",
            f"app_secret={LOOKS_LIKE_APP_SECRET}",
            f"client_secret: {LOOKS_LIKE_META_TOKEN}",
            f"Authorization: Bearer {LOOKS_LIKE_META_TOKEN}",
            f"api_key={LOOKS_LIKE_META_TOKEN}",
            f"token={LOOKS_LIKE_META_TOKEN}",
        ],
    )
    def test_named_secrets_are_masked(self, text: str) -> None:
        result = redact(text)
        assert LOOKS_LIKE_META_TOKEN not in result
        assert LOOKS_LIKE_APP_SECRET not in result
        assert MASK in result

    def test_bare_meta_token_is_masked_without_a_key_naming_it(self) -> None:
        # Tokens leak in prose too, not only as key=value.
        assert LOOKS_LIKE_META_TOKEN not in redact(
            f"Meta said: the token {LOOKS_LIKE_META_TOKEN} has expired"
        )

    def test_bare_app_scoped_secret_is_masked(self) -> None:
        assert LOOKS_LIKE_APP_SECRET not in redact(f"using {LOOKS_LIKE_APP_SECRET} now")

    def test_no_partial_token_survives(self) -> None:
        # A truncated token is still part of a credential. Nothing recognisable
        # may remain.
        result = redact(f"access_token={LOOKS_LIKE_META_TOKEN}")
        assert LOOKS_LIKE_META_TOKEN[:12] not in result

    @pytest.mark.parametrize(
        "innocent",
        [
            "tokenizer=fast",
            "the token is short: abc",
            "secretary=true",
            "campaign_name=Acme | OUTCOME_LEADS | 2026-09-16",
            "daily_budget=7000",
        ],
    )
    def test_ordinary_text_is_untouched(self, innocent: str) -> None:
        assert redact(innocent) == innocent

    def test_oauth_authorization_header_is_masked(self) -> None:
        token = "opaque0token0value0without0prefix"
        assert token not in redact(f"Authorization: OAuth {token}")
        assert redact("finish the OAuth callback") == "finish the OAuth callback"

    def test_empty_input(self) -> None:
        assert redact("") == ""


class TestRedactUrl:
    def test_graph_url_query_is_dropped(self) -> None:
        url = (
            "https://graph.facebook.com/v26.0/act_1/ads"
            f"?access_token={LOOKS_LIKE_META_TOKEN}&fields=id,name"
        )
        result = redact_url(url)
        assert LOOKS_LIKE_META_TOKEN not in result
        assert "REDACTED_QUERY" in result
        # The path survives, so the log still says which endpoint was called.
        assert "/v26.0/act_1/ads" in result

    def test_appsecret_proof_is_caught(self) -> None:
        assert "REDACTED_QUERY" in redact_url(
            "https://graph.facebook.com/v26.0/me?appsecret_proof=deadbeefcafe"
        )

    def test_harmless_query_is_preserved(self) -> None:
        url = "https://graph.facebook.com/v26.0/act_1/ads?fields=id,name&limit=25"
        assert redact_url(url) == url

    @pytest.mark.parametrize(
        "param", ["fb_exchange_token", "code", "input_token", "unheard_of_param"]
    )
    def test_unknown_query_parameters_drop_the_query(self, param: str) -> None:
        # Opaque on purpose: the old filter only caught values shaped like a
        # token or parameters it had been told about.
        url = f"https://graph.facebook.com/v26.0/oauth?{param}=opaque123&limit=5"
        result = redact_url(url)
        assert "opaque123" not in result
        assert "REDACTED_QUERY" in result

    def test_credentials_in_the_authority_are_removed(self) -> None:
        result = redact_url("https://user:hunter22@example.com/path")
        assert "hunter22" not in result
        assert result.endswith("@example.com/path")

    def test_no_query_is_a_no_op(self) -> None:
        assert redact_url("https://example.com/path") == "https://example.com/path"
        assert redact_url("") == ""


class TestRedactMapping:
    def test_secret_keys_masked_in_any_naming_style(self) -> None:
        payload = {
            "META_ACCESS_TOKEN": LOOKS_LIKE_META_TOKEN,
            "metaAccessToken": LOOKS_LIKE_META_TOKEN,
            "meta_access_token": LOOKS_LIKE_META_TOKEN,
            "app_secret": LOOKS_LIKE_APP_SECRET,
        }
        result = redact_mapping(payload)
        assert all(value == MASK for value in result.values())

    @pytest.mark.parametrize(
        "key",
        ["metaAccessToken", "pageAccessToken", "X-Access-Token", "user_token", "clientSecret"],
    )
    def test_secret_keys_masked_whatever_the_value_looks_like(self, key: str) -> None:
        # A value that matches none of the string patterns, so only the key
        # match can mask it. The earlier test passed on the value alone.
        assert redact_mapping({key: "opaque"}) == {key: MASK}

    def test_nested_structures_are_walked(self) -> None:
        payload = {
            "state": {
                "objects": [{"id": "120", "access_token": LOOKS_LIKE_META_TOKEN}],
                "note": f"used token {LOOKS_LIKE_META_TOKEN}",
            }
        }
        serialised = repr(redact_mapping(payload))
        assert LOOKS_LIKE_META_TOKEN not in serialised
        assert "120" in serialised

    def test_business_data_is_preserved(self) -> None:
        payload = {"campaign_id": "120001", "daily_budget": 7000, "currency": "PLN"}
        assert redact_mapping(payload) == payload

    def test_pathological_nesting_terminates(self) -> None:
        deep: dict[str, object] = {"value": "leaf"}
        for _ in range(60):
            deep = {"nested": deep}
        assert redact_mapping(deep) is not None  # does not recurse forever


class TestFingerprint:
    def test_is_stable_and_non_reversible(self) -> None:
        first = fingerprint(LOOKS_LIKE_META_TOKEN)
        assert first == fingerprint(LOOKS_LIKE_META_TOKEN)
        assert LOOKS_LIKE_META_TOKEN[:8] not in first
        assert first.startswith("sha256:")

    def test_different_secrets_differ(self) -> None:
        assert fingerprint("one-value") != fingerprint("another-value")

    def test_absent_secret_reports_not_set(self) -> None:
        assert fingerprint(None) == "not set"
        assert fingerprint("") == "not set"

    def test_length_is_disclosed_to_help_spot_a_truncated_paste(self) -> None:
        assert "len 9" in fingerprint("123456789")
