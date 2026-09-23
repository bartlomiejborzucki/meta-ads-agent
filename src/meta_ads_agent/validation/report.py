"""The result of validating a plan: findings, and what they add up to."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from meta_ads_agent.capabilities import Provider


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Render order. Sorting by the enum's string value put notes before warnings.
_RANK = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation result.

    ``code`` is stable and greppable so a skill can reference a specific check
    and tests can assert on it without matching prose.
    """

    severity: Severity
    code: str
    message: str
    path: str = ""

    def __str__(self) -> str:
        where = f" [{self.path}]" if self.path else ""
        return f"{self.severity.value.upper()}: {self.code}{where}: {self.message}"


@dataclass(slots=True)
class ValidationReport:
    """The outcome of validating one plan."""

    findings: list[Finding] = field(default_factory=list)
    providers_used: dict[str, str] = field(default_factory=dict)

    def add(self, severity: Severity, code: str, message: str, path: str = "") -> None:
        self.findings.append(Finding(severity, code, message, path))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def ok(self) -> bool:
        """True when no error blocks execution. Warnings do not block."""
        return not self.errors

    @property
    def uses_fallback(self) -> bool:
        return Provider.API_FALLBACK.value in self.providers_used.values()

    def render(self) -> str:
        if not self.findings:
            return "Plan is valid. No findings."
        lines = [str(f) for f in sorted(self.findings, key=lambda f: (_RANK[f.severity], f.code))]
        verdict = "VALID" if self.ok else "BLOCKED"
        summary = (
            f"{verdict}: {len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s), {len(self.infos)} note(s)"
        )
        return "\n".join([*lines, "", summary])
