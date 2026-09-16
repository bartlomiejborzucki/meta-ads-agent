"""Exception hierarchy.

Every error carries a message that is safe to print: no tokens, no customer
data. Anything reaching a user-visible surface goes through
:mod:`meta_ads_agent.redaction` as a second line of defence.
"""

from __future__ import annotations


class MetaAdsAgentError(Exception):
    """Base class for every error this package raises."""


class ConfigError(MetaAdsAgentError):
    """Configuration on disk is missing, malformed, or contradictory."""


class WorkspaceError(MetaAdsAgentError):
    """The brand workspace is missing or not usable."""


class ValidationError(MetaAdsAgentError):
    """A plan or config failed validation.

    Carries the individual findings so a caller can render them all at once
    rather than making the user fix one field per run.
    """

    def __init__(self, message: str, findings: list[str] | None = None) -> None:
        super().__init__(message)
        self.findings = findings or []

    def __str__(self) -> str:
        base = super().__str__()
        if not self.findings:
            return base
        lines = "\n".join(f"  - {f}" for f in self.findings)
        return f"{base}\n{lines}"


class CurrencyError(MetaAdsAgentError):
    """A currency's minor-unit scale is unknown, so no amount can be trusted.

    Raised rather than guessing. Guessing here means a budget off by 100x.
    """


class CapabilityError(MetaAdsAgentError):
    """A capability is unknown, or is not supported by any provider."""


class StateError(MetaAdsAgentError):
    """Persisted state is missing, corrupt, or inconsistent with a request."""


class ReconciliationError(StateError):
    """Local state and Meta disagree.

    Raised instead of overwriting: a human may have changed something in Ads
    Manager and their change wins until they say otherwise.
    """


class ApiFallbackError(MetaAdsAgentError):
    """The Marketing API fallback could not run or failed."""


class ApiFallbackUnavailable(ApiFallbackError):
    """The optional ``api`` extra is not installed, or credentials are absent."""


class ApiCallFailed(ApiFallbackError):
    """Meta rejected a fallback call.

    ``stage`` names the pipeline step that failed so a resume knows where to
    pick up. ``retry_safe`` is False when the call may have partially applied -
    the caller must query Meta before retrying rather than repeating the write.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        meta_code: int | None = None,
        meta_subcode: int | None = None,
        retry_safe: bool = False,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.meta_code = meta_code
        self.meta_subcode = meta_subcode
        self.retry_safe = retry_safe


class ApprovalRequired(MetaAdsAgentError):
    """A spend-affecting or destructive operation was attempted without approval.

    The CLI raises this rather than prompting. Approval is a conversation
    between the user and the agent; a tool that prompts on stdin would let an
    agent approve on the user's behalf.
    """

    def __init__(self, message: str, *, risk_level: str, operation: str) -> None:
        super().__init__(message)
        self.risk_level = risk_level
        self.operation = operation


class DryRun(MetaAdsAgentError):
    """Raised instead of performing a mutation when ``--dry-run`` is set.

    An exception rather than a return value so a dry run can never be mistaken
    for a completed operation by a caller that ignores the result. The CLI
    prints it and exits successfully.
    """
