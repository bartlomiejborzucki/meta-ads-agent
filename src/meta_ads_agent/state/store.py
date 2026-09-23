"""Load, save, and reconcile campaign state."""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.errors import ReconciliationError, StateError
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import CampaignState, CreatedObject, Failure, Stage
from meta_ads_agent.redaction import redact_mapping
from meta_ads_agent.workspace import Workspace


def plan_fingerprint(doc: CampaignPlanDocument) -> str:
    """Stable hash of a plan's meaningful content.

    Excludes ``created_at`` and ``notes`` so re-saving a plan does not look
    like a change, and includes everything that affects what gets built. A
    resume compares this against the fingerprint stored with the objects: if
    the plan changed after objects were created, continuing would apply a
    different plan to existing structure.

    Fields left at their default are excluded too. Otherwise adding any field
    with a default to the plan model - an ordinary minor release - changes the
    fingerprint of every existing plan, and every in-flight campaign falsely
    reports that its plan was edited. The prefix names the algorithm, so a
    fingerprint recorded by an older release is still compared the way it was
    computed (:func:`fingerprint_matches`).
    """
    payload = doc.campaign.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    return _FINGERPRINT_V2 + _digest(payload)


# 0.1-0.2 hashed defaulted fields as well. Kept only to read their state.
_FINGERPRINT_V1 = "sha256:"
_FINGERPRINT_V2 = "v2:sha256:"


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_matches(recorded: str, doc: CampaignPlanDocument) -> bool:
    """Whether *doc* is the plan that produced a recorded fingerprint."""
    if recorded.startswith(_FINGERPRINT_V1):
        legacy = doc.campaign.model_dump(mode="json", exclude_none=True)
        return recorded == _FINGERPRINT_V1 + _digest(legacy)
    return recorded == plan_fingerprint(doc)


class StateStore:
    """File-backed campaign state, written atomically after every change."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    # -- plan --------------------------------------------------------------
    def save_plan(self, doc: CampaignPlanDocument) -> None:
        path = self.workspace.plan_file(doc.slug)
        self.workspace.write_yaml(
            path,
            doc.model_dump(mode="json", exclude_none=True),
            header=(
                "# Campaign plan - the source of truth for INTENT.\n"
                "# Reviewed before anything is written to Meta. Once validated,\n"
                "# execution reads this file rather than the conversation.\n"
                "# Created object ids live in state.json next to this file.\n"
                "# Budget amounts are display amounts in the stated currency."
            ),
        )

    def load_plan(self, slug: str) -> CampaignPlanDocument:
        path = self.workspace.plan_file(slug)
        raw = self.workspace.read_yaml(path)
        try:
            return CampaignPlanDocument.model_validate(raw)
        except PydanticValidationError as exc:
            raise StateError(f"{path} is not a valid campaign plan:\n{exc}") from exc

    def plan_exists(self, slug: str) -> bool:
        return self.workspace.plan_file(slug).is_file()

    # -- state -------------------------------------------------------------
    def save_state(self, state: CampaignState) -> None:
        """Persist state. Called after every single create, not at the end.

        Secrets are scrubbed on the way out as a second line of defence. Code
        should never be putting them in state at all; this makes a mistake
        harmless rather than permanent.
        """
        payload = redact_mapping(state.model_dump(mode="json", exclude_none=True))
        self.workspace.write_json(self.workspace.state_file(state.slug), payload)

    def load_state(self, slug: str) -> CampaignState:
        path = self.workspace.state_file(slug)
        raw = self.workspace.read_json(path)
        try:
            return CampaignState.model_validate(raw)
        except PydanticValidationError as exc:
            raise StateError(f"{path} is not valid campaign state:\n{exc}") from exc

    def state_exists(self, slug: str) -> bool:
        return self.workspace.state_file(slug).is_file()

    def load_or_create_state(self, doc: CampaignPlanDocument) -> CampaignState:
        """Get existing state for a plan, or start fresh.

        Refuses to reuse state whose plan fingerprint no longer matches. That
        situation means the plan was edited after objects were created, and
        resolving it is a human decision: either revert the plan, or start a new
        campaign slug.
        """
        if self.state_exists(doc.slug):
            state = self.load_state(doc.slug)
            if state.ad_account_id != doc.ad_account_id:
                raise ReconciliationError(
                    f"state for {doc.slug!r} belongs to account "
                    f"{state.ad_account_id} but the plan targets "
                    f"{doc.ad_account_id}. Use a different slug."
                )
            if (
                state.plan_fingerprint
                and not fingerprint_matches(state.plan_fingerprint, doc)
                and state.objects
            ):
                raise ReconciliationError(
                    f"the plan for {doc.slug!r} changed after "
                    f"{len(state.objects)} object(s) were created on Meta.\n"
                    "Continuing would apply a different plan to existing "
                    "structure. Either restore the plan that produced them, or "
                    "start a new campaign slug for the new plan."
                )
            return state

        state = CampaignState(
            slug=doc.slug,
            ad_account_id=doc.ad_account_id,
            plan_fingerprint=plan_fingerprint(doc),
        )
        self.save_state(state)
        return state

    # -- mutation helpers --------------------------------------------------
    def record_object(self, state: CampaignState, obj: CreatedObject) -> CreatedObject:
        """Record an object and flush immediately.

        The flush is the whole point: an id that exists on Meta but not on disk
        is an orphan waiting to be duplicated.
        """
        recorded = state.record(obj)
        self.save_state(state)
        return recorded

    def advance(self, state: CampaignState, stage: Stage) -> None:
        state.advance(stage)
        self.save_state(state)

    def record_failure(self, state: CampaignState, failure: Failure) -> None:
        state.record_failure(failure)
        self.save_state(state)

    # -- reconciliation ----------------------------------------------------
    def reconcile(self, state: CampaignState, remote: dict[str, dict[str, object]]) -> list[str]:
        """Compare recorded objects against Meta and report differences.

        *remote* maps object id to the fields read back from Meta, or to an
        empty mapping when the object no longer exists. The caller does the
        reading - this module never talks to the network.

        Returns human-readable differences. An empty list means local and
        remote agree. A non-empty list must be shown to the user before any
        mutation: somebody may have changed something in Ads Manager, and their
        change wins until they say otherwise.
        """
        differences: list[str] = []
        for obj in state.objects:
            if obj.id not in remote:
                differences.append(
                    f"{obj.type.value} {obj.id} ({obj.name or 'unnamed'}) was not "
                    "checked against Meta"
                )
                continue
            fields = remote[obj.id]
            if not fields:
                differences.append(
                    f"{obj.type.value} {obj.id} ({obj.name or 'unnamed'}) no longer "
                    "exists on Meta - it may have been deleted outside this tool"
                )
                continue
            remote_status = str(fields.get("status", "")).upper()
            if (
                remote_status
                and obj.status_at_creation
                and remote_status != obj.status_at_creation.upper()
            ):
                differences.append(
                    f"{obj.type.value} {obj.id} is {remote_status} on Meta but was "
                    f"recorded as {obj.status_at_creation.upper()} here"
                )
            remote_name = fields.get("name")
            if obj.name and remote_name and str(remote_name) != obj.name:
                differences.append(
                    f"{obj.type.value} {obj.id} is named {remote_name!r} on Meta "
                    f"but {obj.name!r} here"
                )
        return differences
