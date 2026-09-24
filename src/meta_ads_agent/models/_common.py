"""Shared field types and validators for the models."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict

# Video containers, by extension. An extension is a routing hint only - what a
# file actually is comes from its header (meta_ads_agent.state.assets).
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"})


def looks_like_video(path: str) -> bool:
    """Whether *path* is named like a video. Not proof that it is one."""
    return any(path.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)


_ACCOUNT_RE = re.compile(r"^act_\d{1,20}$")
_NUMERIC_ID_RE = re.compile(r"^\d{1,25}$")
# Meta object ids are numeric, but ad ids and creative ids can appear as
# "<numeric>" and post ids as "<page_id>_<post_id>".
_POST_ID_RE = re.compile(r"^\d{1,25}_\d{1,25}$")
# Objectives, optimization goals, CTA types and similar are SCREAMING_SNAKE on
# Meta's side. We check the *shape* only. The set of valid values changes with
# every API version, so it is discovered at runtime via ads_get_field_context
# rather than hardcoded here - see ADR-007.
_ENUM_SHAPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class StrictModel(BaseModel):
    """Base model that rejects unknown fields.

    An agent writing a plan will occasionally invent a field name. Silently
    dropping it means the user reviews a plan containing a setting that will
    never be applied, which is worse than an error.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=False)


def _check_account_id(value: str) -> str:
    if not _ACCOUNT_RE.match(value):
        raise ValueError(f"ad account id must look like 'act_1234567890', got {value!r}")
    return value


def _check_numeric_id(value: str) -> str:
    if not _NUMERIC_ID_RE.match(value):
        raise ValueError(f"expected a numeric Meta object id, got {value!r}")
    return value


def _check_post_id(value: str) -> str:
    if not (_POST_ID_RE.match(value) or _NUMERIC_ID_RE.match(value)):
        raise ValueError(f"expected a post id like '1234_5678' or a numeric id, got {value!r}")
    return value


def _check_enum_shape(value: str) -> str:
    if not _ENUM_SHAPE_RE.match(value):
        raise ValueError(
            f"expected an UPPER_SNAKE_CASE Meta enum value, got {value!r}. "
            "Values are not validated against a local list - discover the "
            "current set with the field-metadata tool."
        )
    return value


def _check_https_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"destination must be an http(s) URL, got {value!r}")
    if not parts.netloc:
        raise ValueError(f"URL has no host: {value!r}")
    if parts.scheme == "http":
        # Not fatal: some advertisers still run http landing pages. The plan
        # validator downgrades this to a warning so the user sees it.
        pass
    return value


def _check_currency(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"expected an ISO 4217 currency code, got {value!r}")
    return code


def _check_country(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError(f"expected a 2-letter ISO 3166-1 country code, got {value!r}")
    return code


AccountId = Annotated[str, AfterValidator(_check_account_id)]
MetaId = Annotated[str, AfterValidator(_check_numeric_id)]
PostId = Annotated[str, AfterValidator(_check_post_id)]
MetaEnum = Annotated[str, AfterValidator(_check_enum_shape)]
HttpUrl = Annotated[str, AfterValidator(_check_https_url)]
CurrencyCode = Annotated[str, AfterValidator(_check_currency)]
CountryCode = Annotated[str, AfterValidator(_check_country)]


def dump_yaml_ready(model: BaseModel) -> dict[str, Any]:
    """Model as plain data suitable for YAML, with ``None`` fields omitted.

    Plans are read by humans. Fields the user did not set should not appear as
    ``null`` noise.
    """
    return model.model_dump(mode="json", exclude_none=True)


def _schema_check(current: int) -> Callable[[int], int]:
    """A ``schema_version`` check that refuses a file from a newer release.

    Pydantic would otherwise read ``schema_version: 2`` as a number like any
    other and carry on, interpreting a newer format by the older rules - the
    silent misreading a version field exists to prevent. An older version is
    accepted: reading those is what the compatibility policy promises
    (docs/reference/compatibility.md).
    """

    def check(value: int) -> int:
        if value < 1:
            raise ValueError(f"schema_version must be 1 or more, got {value}")
        if value > current:
            raise ValueError(
                f"schema_version {value} was written by a newer meta-ads-agent; this "
                f"one reads up to {current}. Upgrade (meta-ads-agent upgrade) rather "
                "than editing the file down."
            )
        return value

    return check


# Current schema of each user-facing file. A bump needs a migration, a
# changelog entry, and a fixture of the old shape in tests/fixtures/.
PLAN_SCHEMA = 1
STATE_SCHEMA = 1
BRAND_SCHEMA = 1
OFFER_SCHEMA = 1
ASSET_MANIFEST_SCHEMA = 1

PlanSchemaVersion = Annotated[int, AfterValidator(_schema_check(PLAN_SCHEMA))]
StateSchemaVersion = Annotated[int, AfterValidator(_schema_check(STATE_SCHEMA))]
BrandSchemaVersion = Annotated[int, AfterValidator(_schema_check(BRAND_SCHEMA))]
OfferSchemaVersion = Annotated[int, AfterValidator(_schema_check(OFFER_SCHEMA))]
AssetManifestSchemaVersion = Annotated[int, AfterValidator(_schema_check(ASSET_MANIFEST_SCHEMA))]
