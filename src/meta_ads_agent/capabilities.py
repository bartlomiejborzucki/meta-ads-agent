"""Capability registry: which layer owns which capability, and at what risk.

Loaded from ``config/capabilities.yaml``. The routing rule is deliberately
boring - see docs/architecture/adr/ADR-002-api-fallback.md:

1. If the official MCP covers it, use the MCP.
2. Only if it does not, use the fallback.
3. Never use the fallback because it is more convenient.
4. When the fallback is used, say so and name the gap.

Tool names in the registry are **hints for the agent, not contracts**. Meta can
rename them, so nothing in this module dispatches on a tool name.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from meta_ads_agent.errors import CapabilityError, ConfigError


class Provider(StrEnum):
    """Execution layer that owns a capability."""

    OFFICIAL_MCP = "official_mcp"
    API_FALLBACK = "api_fallback"
    NONE = "none"


class RiskLevel(StrEnum):
    """Approval class. Mirrors skills/meta-ads-core/references/safety-policy.md.

    Declared in ascending order of consequence; :func:`risk_rank` relies on it.
    """

    READ = "read"
    CREATE_PAUSED = "create_paused"
    UPDATE_INACTIVE = "update_inactive"
    UPDATE_ACTIVE = "update_active"
    BUDGET_INCREASE = "budget_increase"
    ACTIVATE = "activate"
    BULK = "bulk"
    DELETE = "delete"
    PII_UPLOAD = "pii_upload"


_RISK_ORDER: tuple[RiskLevel, ...] = (
    RiskLevel.READ,
    RiskLevel.CREATE_PAUSED,
    RiskLevel.UPDATE_INACTIVE,
    RiskLevel.UPDATE_ACTIVE,
    RiskLevel.BUDGET_INCREASE,
    RiskLevel.ACTIVATE,
    RiskLevel.BULK,
    RiskLevel.DELETE,
    RiskLevel.PII_UPLOAD,
)

# Classes that must never proceed without the user explicitly approving this
# specific change. Kept here, next to the enum, rather than trusting each
# registry entry's requires_confirmation flag - a typo in YAML must not be able
# to downgrade an activation to "no approval needed".
APPROVAL_REQUIRED: frozenset[RiskLevel] = frozenset(
    {
        RiskLevel.UPDATE_ACTIVE,
        RiskLevel.BUDGET_INCREASE,
        RiskLevel.ACTIVATE,
        RiskLevel.BULK,
        RiskLevel.DELETE,
        RiskLevel.PII_UPLOAD,
    }
)


def risk_rank(level: RiskLevel) -> int:
    """Position in the consequence ordering. Higher means more dangerous."""
    return _RISK_ORDER.index(level)


@dataclass(frozen=True, slots=True)
class Capability:
    """One routable capability."""

    name: str
    area: str
    preferred_provider: Provider
    fallback_provider: Provider
    risk_level: RiskLevel
    mcp_tools: tuple[str, ...]
    cli: str | None
    notes: str
    last_reviewed: _dt.date | None
    requires_confirmation_declared: bool

    @property
    def requires_approval(self) -> bool:
        """Whether this needs explicit user approval for *this* change.

        The risk class decides. A registry entry cannot opt out of an approval
        the class demands; it can only opt *in* to a stricter stance.
        """
        return self.risk_level in APPROVAL_REQUIRED or self.requires_confirmation_declared

    @property
    def supported(self) -> bool:
        """False only when neither layer can do this in the current release."""
        return Provider.NONE not in (self.preferred_provider, self.fallback_provider) or (
            self.preferred_provider is not Provider.NONE
        )

    @property
    def is_gap(self) -> bool:
        """True when the official MCP cannot do this and we fall back."""
        return self.preferred_provider is Provider.API_FALLBACK


@dataclass(frozen=True, slots=True)
class Route:
    """The outcome of a routing decision, including why."""

    capability: str
    provider: Provider
    risk_level: RiskLevel
    requires_approval: bool
    reason: str
    mcp_tools: tuple[str, ...] = ()
    cli: str | None = None

    @property
    def uses_fallback(self) -> bool:
        return self.provider is Provider.API_FALLBACK


@dataclass(frozen=True, slots=True)
class Registry:
    """An immutable view over the capability registry."""

    version: int
    reviewed: _dt.date | None
    graph_api_version: str
    mcp_endpoint: str
    capabilities: dict[str, Capability]

    def get(self, name: str) -> Capability:
        try:
            return self.capabilities[name]
        except KeyError:
            raise CapabilityError(
                f"Unknown capability {name!r}. Known: {', '.join(sorted(self.capabilities))}"
            ) from None

    def route(self, name: str, *, mcp_available: bool = True) -> Route:
        """Decide which layer should perform *name*.

        ``mcp_available=False`` models a session with no Meta MCP connected. It
        does **not** let the fallback take over MCP-owned work: if the MCP owns
        a capability and is absent, the answer is "connect the MCP", not "use a
        token instead". Silently rerouting would turn a setup problem into a
        credential request.
        """
        cap = self.get(name)

        if cap.preferred_provider is Provider.NONE:
            raise CapabilityError(f"{name!r} is not supported in this release. {cap.notes.strip()}")

        if cap.preferred_provider is Provider.OFFICIAL_MCP:
            if not mcp_available:
                raise CapabilityError(
                    f"{name!r} is provided by Meta's official Ads MCP, which is not "
                    "connected. See docs/getting-started/connect-meta-mcp.md. "
                    "The API fallback deliberately does not cover it."
                )
            return Route(
                capability=cap.name,
                provider=Provider.OFFICIAL_MCP,
                risk_level=cap.risk_level,
                requires_approval=cap.requires_approval,
                reason="Meta's official Ads MCP covers this capability.",
                mcp_tools=cap.mcp_tools,
            )

        return Route(
            capability=cap.name,
            provider=Provider.API_FALLBACK,
            risk_level=cap.risk_level,
            requires_approval=cap.requires_approval,
            reason=(
                "Meta's official Ads MCP does not currently expose this, so it "
                "runs through the Meta Business SDK fallback."
            ),
            mcp_tools=cap.mcp_tools,
            cli=cap.cli,
        )

    def gaps(self) -> list[Capability]:
        """Capabilities the fallback exists for. This list should shrink."""
        return sorted((c for c in self.capabilities.values() if c.is_gap), key=lambda c: c.name)

    def unsupported(self) -> list[Capability]:
        return sorted(
            (c for c in self.capabilities.values() if c.preferred_provider is Provider.NONE),
            key=lambda c: c.name,
        )

    def by_area(self) -> dict[str, list[Capability]]:
        grouped: dict[str, list[Capability]] = {}
        for cap in self.capabilities.values():
            grouped.setdefault(cap.area, []).append(cap)
        for caps in grouped.values():
            caps.sort(key=lambda c: c.name)
        return dict(sorted(grouped.items()))

    def stale(self, *, older_than_days: int = 90, today: _dt.date | None = None) -> list[str]:
        """Capabilities whose review is older than *older_than_days*.

        Meta changes. A registry entry nobody has looked at in a quarter is a
        claim, not a fact.
        """
        now = today or _dt.date.today()
        out = []
        for cap in self.capabilities.values():
            if cap.last_reviewed is None or (now - cap.last_reviewed).days > older_than_days:
                out.append(cap.name)
        return sorted(out)


def default_registry_path() -> Path:
    """Locate ``capabilities.yaml`` for a source checkout or an installed wheel."""
    packaged = Path(__file__).with_name("_data") / "capabilities.yaml"
    if packaged.is_file():
        return packaged
    # Source checkout: src/meta_ads_agent/ -> repo root.
    repo = Path(__file__).resolve().parents[2] / "config" / "capabilities.yaml"
    if repo.is_file():
        return repo
    raise ConfigError(
        "Could not locate capabilities.yaml. Expected it next to the package "
        f"at {packaged} or in the repository at {repo}."
    )


def load_registry(path: Path | str | None = None) -> Registry:
    """Parse and validate the capability registry."""
    target = Path(path) if path else default_registry_path()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Capability registry not found: {target}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Capability registry is not valid YAML: {target}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Capability registry must be a mapping: {target}")

    entries = raw.get("capabilities")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"Capability registry has no 'capabilities' list: {target}")

    caps: dict[str, Capability] = {}
    for index, entry in enumerate(entries):
        cap = _parse_capability(entry, index, target)
        if cap.name in caps:
            raise ConfigError(f"Duplicate capability {cap.name!r} in {target}")
        caps[cap.name] = cap

    return Registry(
        version=int(raw.get("version", 1)),
        reviewed=_as_date(raw.get("reviewed")),
        graph_api_version=str(raw.get("graph_api_version", "")),
        mcp_endpoint=str(raw.get("mcp_endpoint", "")),
        capabilities=caps,
    )


@lru_cache(maxsize=4)
def cached_registry(path: str | None = None) -> Registry:
    """Process-lifetime cached registry, for CLI commands that load it twice."""
    return load_registry(path)


def _parse_capability(entry: Any, index: int, source: Path) -> Capability:
    where = f"{source} capability #{index + 1}"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: expected a mapping")

    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"{where}: missing 'name'")

    def provider(key: str, default: str) -> Provider:
        value = str(entry.get(key, default))
        try:
            return Provider(value)
        except ValueError:
            raise ConfigError(
                f"{where} ({name}): {key}={value!r} is not one of {[p.value for p in Provider]}"
            ) from None

    risk_raw = str(entry.get("risk_level", ""))
    try:
        risk = RiskLevel(risk_raw)
    except ValueError:
        raise ConfigError(
            f"{where} ({name}): risk_level={risk_raw!r} is not one of "
            f"{[r.value for r in RiskLevel]}"
        ) from None

    tools = entry.get("mcp_tools") or []
    if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
        raise ConfigError(f"{where} ({name}): mcp_tools must be a list of strings")

    return Capability(
        name=name,
        area=str(entry.get("area", "uncategorised")),
        preferred_provider=provider("preferred_provider", "none"),
        fallback_provider=provider("fallback_provider", "none"),
        risk_level=risk,
        mcp_tools=tuple(tools),
        cli=(str(entry["cli"]) if entry.get("cli") else None),
        notes=str(entry.get("notes") or ""),
        last_reviewed=_as_date(entry.get("last_reviewed")),
        requires_confirmation_declared=bool(entry.get("requires_confirmation", False)),
    )


def _as_date(value: Any) -> _dt.date | None:
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value))
    except ValueError:
        return None
