"""Thin wrapper around the official Meta Business SDK.

Deliberately thin. The SDK already handles authentication, pagination, retries,
request formatting, and chunked uploads; reimplementing any of that would be
the mistake ADR-002 exists to avoid. This module only:

* loads credentials from the environment, never from state or the workspace
* pins the Graph API version from one place
* converts SDK exceptions into our error types with the Meta error code intact
* decides whether a failed write is safe to retry

Credentials come from ``.env``-style environment variables and are never
logged, echoed, or persisted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from meta_ads_agent.api.version import graph_api_version, is_probably_unsupported
from meta_ads_agent.errors import ApiCallFailed, ApiFallbackUnavailable
from meta_ads_agent.redaction import fingerprint, redact

# Meta error codes that indicate a transient condition. A read may be retried
# with backoff. A WRITE may not be retried blindly even for these - a timeout
# does not tell you whether Meta created the object. See ADR-005.
# Codes after which a *read* may be retried, with backoff: the core skill's
# error reference. 368 is not one of them although it is "temporary" - it is a
# block for policy violations, and the reference says stop and investigate.
# Retrying it is how a temporary block becomes a longer one.
TRANSIENT_CODES = frozenset({1, 2, 4, 17, 341, 613})

TOKEN_ENV = "META_ACCESS_TOKEN"  # noqa: S105 - a variable name, not a value
APP_ID_ENV = "META_APP_ID"
APP_SECRET_ENV = "META_APP_SECRET"  # noqa: S105 - a variable name, not a value
ACCOUNT_ENV = "META_AD_ACCOUNT_ID"


@dataclass(frozen=True, slots=True)
class Credentials:
    """Fallback credentials, read from the environment."""

    access_token: str
    app_id: str | None = None
    app_secret: str | None = None
    ad_account_id: str | None = None

    @classmethod
    def from_env(cls) -> Credentials:
        token = (os.environ.get(TOKEN_ENV) or "").strip()
        if not token:
            raise ApiFallbackUnavailable(
                f"{TOKEN_ENV} is not set. The Marketing API fallback needs an "
                "access token with ads_management on the target account.\n"
                "You only need this for capabilities Meta's official Ads MCP "
                "does not expose - run 'meta-ads-agent capabilities' to see "
                "which. Setup: docs/getting-started/api-fallback.md"
            )
        return cls(
            access_token=token,
            app_id=(os.environ.get(APP_ID_ENV) or "").strip() or None,
            app_secret=(os.environ.get(APP_SECRET_ENV) or "").strip() or None,
            ad_account_id=(os.environ.get(ACCOUNT_ENV) or "").strip() or None,
        )

    def describe(self) -> dict[str, str]:
        """Non-sensitive summary for ``doctor``.

        Reports a hash, never a prefix: a truncated token is still part of a
        credential.
        """
        return {
            TOKEN_ENV: fingerprint(self.access_token),
            APP_ID_ENV: "set" if self.app_id else "not set",
            APP_SECRET_ENV: fingerprint(self.app_secret),
            ACCOUNT_ENV: self.ad_account_id or "not set",
        }


class ApiClient:
    """An initialised Business SDK session."""

    def __init__(
        self,
        credentials: Credentials | None = None,
        *,
        api_version: str | None = None,
    ) -> None:
        self.credentials = credentials or Credentials.from_env()
        self.api_version = graph_api_version(api_version)
        self._api: Any | None = None

    @cached_property
    def _sdk(self) -> Any:
        """Import the SDK lazily, with an actionable message when absent."""
        try:
            from facebook_business.api import FacebookAdsApi
        except ImportError as exc:
            raise ApiFallbackUnavailable(
                "The Meta Business SDK is not installed. It is an optional "
                "extra so that MCP-only installations stay credential-free:\n"
                '  uv pip install "meta-ads-agent[api]"\n'
                '  pip install "meta-ads-agent[api]"'
            ) from exc
        return FacebookAdsApi

    def connect(self) -> Any:
        """Initialise and return the SDK API object."""
        if self._api is not None:
            return self._api
        if is_probably_unsupported(self.api_version):
            raise ApiFallbackUnavailable(
                f"Graph API {self.api_version} is older than the oldest version "
                "known to be supported. Unset META_GRAPH_API_VERSION or set a "
                "current version."
            )
        self._api = self._sdk.init(
            app_id=self.credentials.app_id,
            app_secret=self.credentials.app_secret,
            access_token=self.credentials.access_token,
            api_version=self.api_version,
            crash_log=False,
        )
        return self._api

    def account(self, ad_account_id: str | None = None) -> Any:
        """An ``AdAccount`` object for *ad_account_id* or the configured default."""
        from facebook_business.adobjects.adaccount import AdAccount

        target = ad_account_id or self.credentials.ad_account_id
        if not target:
            raise ApiFallbackUnavailable(
                f"No ad account given and {ACCOUNT_ENV} is not set. Pass --account act_<id>."
            )
        target = normalise_account_id(target)
        self.connect()
        return AdAccount(target, api=self._api)


def wrap_sdk_error(exc: Exception, *, stage: str, operation: str) -> ApiCallFailed:
    """Convert an SDK exception into :class:`ApiCallFailed`.

    Preserves Meta's error code and subcode, which are the only reliable way to
    tell "your token expired" from "this field is invalid" from "slow down".
    Sets ``retry_safe`` conservatively: a write is never marked safe, because
    Meta may have applied it before the failure surfaced.
    """
    code: int | None = None
    subcode: int | None = None
    message = redact(str(exc))

    body = getattr(exc, "body", None)
    if callable(body):
        try:
            payload = body() or {}
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = error.get("code")
            subcode = error.get("error_subcode")
            detail = error.get("error_user_msg") or error.get("message")
            if detail:
                message = redact(str(detail))
        except Exception:  # noqa: S110
            # Error handling must never raise. Fall through to the generic
            # message rather than masking the original failure.
            pass

    is_read = stage.startswith("read") or operation.startswith(("get_", "list_"))
    retry_safe = bool(is_read and code in TRANSIENT_CODES)

    return ApiCallFailed(
        f"{operation} failed at stage {stage}: {message}",
        stage=stage,
        meta_code=code,
        meta_subcode=subcode,
        retry_safe=retry_safe,
    )


def normalise_account_id(ad_account_id: str) -> str:
    """The one spelling of an ad account id: ``act_<digits>``.

    ``123`` and ``act_123`` are the same account, and the asset manifest keys
    uploads by account - two spellings would mean two uploads of one file.
    """
    target = ad_account_id.strip()
    return target if target.startswith("act_") else f"act_{target}"
