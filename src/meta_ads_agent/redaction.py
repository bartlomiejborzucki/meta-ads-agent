"""Secret redaction for anything user-visible or written to disk.

Two independent jobs:

* :func:`redact` scrubs strings before they reach a log, an error message, or
  a state file. It is the last line of defence, not the first - code should not
  be putting tokens in messages at all.
* :func:`redact_url` strips query parameters from Graph API URLs. A Graph URL
  routinely carries ``access_token`` in the query string, so a full request URL
  in a log is a leaked credential.

Never print a token, not even a prefix long enough to be useful. The fingerprint
helper exists so a user can confirm *which* token is configured without the
value appearing anywhere.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MASK = "[REDACTED]"

# Environment variables and config keys whose values must never be printed.
SECRET_KEYS = frozenset(
    {
        "meta_access_token",
        "meta_app_secret",
        "meta_app_id",
        "access_token",
        "app_secret",
        "app_id",
        "client_secret",
        "mcp_client_secret",
        "authorization",
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
    }
)

# Query parameters stripped from any URL before it is shown.
_SECRET_QUERY_PARAMS = frozenset({"access_token", "client_secret", "appsecret_proof"})

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # key=value / key: value / "key": "value" in prose, JSON, or shell output.
    (
        re.compile(
            r"""(?ix)
            \b(access[_-]?token|app[_-]?secret|client[_-]?secret|appsecret[_-]?proof
              |bearer|api[_-]?key|token|secret|password|passwd)
            \b\s*["']?\s*[:=]\s*["']?
            ([A-Za-z0-9._\-|]{8,})
            """,
        ),
        r"\1=" + MASK,
    ),
    # Authorization headers.
    (re.compile(r"(?i)\b(Bearer)\s+([A-Za-z0-9._\-|]{8,})"), r"\1 " + MASK),
    # Meta access tokens have a recognisable shape: EAA... base64-ish and long.
    # Catch them even when they appear bare, with no key naming them.
    (re.compile(r"\bEAA[A-Za-z0-9]{12,}\b"), MASK),
    # Meta app-scoped secrets appear as <app_id>|<secret>.
    (re.compile(r"\b\d{15,17}\|[A-Za-z0-9_\-]{20,}\b"), MASK),
)


def redact(text: str) -> str:
    """Mask anything that looks like a credential in *text*."""
    if not text:
        return text
    out = text
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def redact_url(url: str) -> str:
    """Drop the query string from a URL that may carry credentials.

    Graph API URLs put ``access_token`` in the query, so the whole query is
    replaced rather than filtered field by field - a parameter we have not
    thought of is more likely than one we have.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.query:
        return url
    lowered = parts.query.lower()
    if any(p in lowered for p in _SECRET_QUERY_PARAMS):
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "[REDACTED_QUERY]", ""))
    return url


def redact_mapping(data: Any, *, _depth: int = 0) -> Any:
    """Recursively mask secret-named keys in dicts and lists.

    Used before writing state or printing diagnostics. Keys are matched by
    normalised name, so ``META_ACCESS_TOKEN``, ``metaAccessToken``, and
    ``meta_access_token`` are all caught.
    """
    if _depth > 20:  # pathological nesting; stop rather than recurse forever
        return MASK
    if isinstance(data, dict):
        out: dict[Any, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and _normalise_key(key) in SECRET_KEYS:
                out[key] = MASK
            else:
                out[key] = redact_mapping(value, _depth=_depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        items = [redact_mapping(v, _depth=_depth + 1) for v in data]
        return type(data)(items) if isinstance(data, tuple) else items
    if isinstance(data, str):
        return redact(data)
    return data


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", key.strip().lower()).strip("_")


def fingerprint(secret: str | None) -> str:
    """A short, stable, non-reversible identifier for a configured secret.

    Lets ``doctor`` say *which* token is configured, and lets a user notice a
    token changed, without the value ever being displayed. Truncating a real
    token would leak part of a credential; a hash prefix leaks nothing.
    """
    if not secret:
        return "not set"
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]} (len {len(secret)})"
