"""Account facts, as read from Meta.

The agent reads the account through the official MCP and hands the result here.
This module never touches the network: keeping the read outside means the
validator is pure, testable, and identical whether the data came from the MCP
or the SDK fallback.

Every field is optional. A plan can be validated with no account context at all
- it just gets fewer checks and a warning saying so, which is better than
refusing to look at a plan until the user is connected.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from meta_ads_agent.models._common import (
    AccountId,
    CurrencyCode,
    MetaId,
    StrictModel,
)


class AccountContext(StrictModel):
    """What we know about the target ad account.

    Field names follow Meta's own vocabulary so a response can be passed
    through with minimal reshaping. Unknown keys are dropped by
    :meth:`from_meta` rather than rejected, because Meta adds fields.
    """

    id: AccountId
    name: str | None = None
    currency: CurrencyCode | None = None
    currency_offset: int | None = Field(
        default=None,
        description=(
            "Meta's minor-unit multiplier for this account's currency. When "
            "present it OUTRANKS our built-in table - see meta_ads_agent.money."
        ),
    )
    timezone_name: str | None = None
    account_status: int | None = Field(
        default=None, description="Meta's numeric account status; 1 is active"
    )
    disable_reason: int | None = None
    min_daily_budget: int | None = Field(
        default=None,
        description=(
            "Meta's minimum daily budget for this account, in minor units of its "
            "currency, as the account's min_daily_budget field reports it"
        ),
    )
    has_payment_method: bool | None = None
    is_queryable: bool | None = None
    is_ads_mcp_enabled: bool | None = None
    business_id: MetaId | None = None
    business_country_code: str | None = None

    available_page_ids: list[MetaId] = Field(default_factory=list)
    available_instagram_account_ids: list[MetaId] = Field(default_factory=list)
    available_dataset_ids: list[MetaId] = Field(default_factory=list)
    available_conversion_events: list[str] = Field(default_factory=list)
    available_custom_audience_ids: list[MetaId] = Field(default_factory=list)

    # Enum sets discovered at runtime, e.g. via the field-metadata tool. When a
    # set is empty we do not check membership, because an empty list means "we
    # did not look", not "nothing is valid". Guessing here would reject valid
    # configurations every time Meta ships a new objective.
    valid_objectives: list[str] = Field(default_factory=list)
    valid_optimization_goals: list[str] = Field(default_factory=list)
    valid_call_to_action_types: list[str] = Field(default_factory=list)

    @property
    def is_active(self) -> bool | None:
        if self.account_status is None:
            return None
        return self.account_status == 1

    @classmethod
    def from_meta(cls, payload: dict[str, Any]) -> AccountContext:
        """Build from a raw account response, ignoring fields we do not model."""
        known = set(cls.model_fields)
        filtered = {k: v for k, v in payload.items() if k in known}
        if "id" not in filtered and "account_id" in payload:
            filtered["id"] = f"act_{payload['account_id']}"
        return cls.model_validate(filtered)
