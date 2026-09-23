"""Append-only local audit log.

Every consequential operation is appended as one JSON object per line, so the
user can answer "what did this thing do to my account, and when" without
trusting a transcript. JSONL because appending is atomic-enough per line and a
crash cannot corrupt earlier entries.

What is recorded: timestamp, host, operation, resource, before/after summaries,
provider, result, and whether approval was noted.

What is never recorded: credentials, customer data, or hidden reasoning. The
log is a record of *actions*, not of thinking, and summaries pass through
redaction on the way in.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field

from meta_ads_agent.capabilities import Provider, RiskLevel
from meta_ads_agent.locking import file_lock
from meta_ads_agent.models._common import StrictModel
from meta_ads_agent.redaction import redact_mapping
from meta_ads_agent.workspace import Workspace


class ActionRecord(StrictModel):
    """One logged action."""

    at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    operation: str = Field(min_length=1, description="e.g. create_campaign, change_budget")
    capability: str | None = None
    risk_level: RiskLevel = RiskLevel.READ
    provider: Provider = Provider.OFFICIAL_MCP
    resource_type: str | None = None
    resource_id: str | None = None
    ad_account_id: str | None = None
    campaign_slug: str | None = None
    before: dict[str, Any] = Field(
        default_factory=dict, description="Summary of prior state, not a full object dump"
    )
    after: dict[str, Any] = Field(default_factory=dict)
    result: str = Field(default="ok", pattern="^(ok|failed|dry_run|skipped)$")
    detail: str | None = None
    approval_noted: bool = Field(
        default=False,
        description=(
            "Whether the caller asserted the user approved this specific change. "
            "A record, not an enforcement point - the gate is in the workflow."
        ),
    )
    agent_host: str = Field(
        default_factory=lambda: os.environ.get("META_ADS_AGENT_HOST", "unknown")
    )


class ActionLog:
    """Append-only JSONL log in the workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    @property
    def path(self) -> Path:
        return self.workspace.action_log_file

    def append(self, record: ActionRecord) -> ActionRecord:
        payload = redact_mapping(record.model_dump(mode="json", exclude_none=True))
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One writer at a time, so two processes' lines cannot interleave, and
        # fsync so a record of something done to the account survives a crash.
        with (
            file_lock(self.path, what="the action log"),
            self.path.open("a", encoding="utf-8", newline="\n") as stream,
        ):
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record

    def read(self, *, limit: int | None = None) -> list[ActionRecord]:
        """Read the log, newest last. Malformed lines are skipped, not fatal.

        A hand-edited or partially-written line should not make the whole log
        unreadable - the log's job is to be there when something went wrong.
        """
        if not self.path.is_file():
            return []
        records: list[ActionRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ActionRecord.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        if limit is None:
            return records
        # `if limit` used to read limit=0 as "no limit" and return everything.
        return records[-limit:] if limit > 0 else []
