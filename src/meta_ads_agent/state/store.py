"""Load, save, and reconcile campaign state."""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.errors import ReconciliationError, StateError, WorkspaceError
from meta_ads_agent.locking import file_lock
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import (
    CampaignState,
    CreatedObject,
    Failure,
    Stage,
    stage_order,
)
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


# Plan fields added after 0.2 whose default dumps as something other than
# None. A v1 fingerprint hashed every field it knew of, so recomputing one
# must leave these out when they are at their default, or every 0.2 campaign
# stops resuming the day a field is added - the v1 flaw, repeated. The
# example-state test fails when a new field needs adding here.
_ADDED_SINCE_V1: dict[str, object] = {"cards": []}


def _as_v1(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _as_v1(item)
            for key, item in value.items()
            if not (key in _ADDED_SINCE_V1 and item == _ADDED_SINCE_V1[key])
        }
    if isinstance(value, list):
        return [_as_v1(item) for item in value]
    return value


def fingerprint_matches(recorded: str, doc: CampaignPlanDocument) -> bool:
    """Whether *doc* is the plan that produced a recorded fingerprint."""
    if recorded.startswith(_FINGERPRINT_V1):
        legacy = _as_v1(doc.campaign.model_dump(mode="json", exclude_none=True))
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
        # Through the merge, so two sessions starting the same campaign at once
        # end with one state file rather than the second overwriting the first.
        self._flush(state)
        return state

    # -- mutation helpers --------------------------------------------------
    def record_object(self, state: CampaignState, obj: CreatedObject) -> CreatedObject:
        """Record an object and flush immediately.

        The flush is the whole point: an id that exists on Meta but not on disk
        is an orphan waiting to be duplicated.
        """
        recorded = state.record(obj)
        self._flush(state)
        return recorded

    def advance(self, state: CampaignState, stage: Stage) -> None:
        state.advance(stage)
        self._flush(state)

    def record_failure(self, state: CampaignState, failure: Failure) -> None:
        state.record_failure(failure)
        self._flush(state)

    def _flush(self, state: CampaignState) -> None:
        """Save *state* without discarding what another process saved meanwhile.

        Two sessions working on one campaign each hold the state they loaded.
        Saving that copy as-is would erase the other session's objects - ids
        that exist on Meta, and so a duplicate on the next resume. Under the
        lock, anything on disk that this copy lacks is merged in first. The
        merge always completes before an error is raised, so no id is lost
        even when the two sessions disagree.
        """
        path = self.workspace.state_file(state.slug)
        with file_lock(path, what=f"campaign state for {state.slug!r}"):
            conflicts: list[str] = []
            if path.is_file():
                try:
                    disk = self.load_state(state.slug)
                except (StateError, WorkspaceError) as exc:
                    # The file on disk cannot be read - hand-edited, or from a
                    # newer release. Overwriting it could destroy ids only it
                    # holds; raising without saving would lose the id just
                    # created. So this copy goes beside it, and then we stop.
                    recovered = path.with_name(f"{path.name}.recovered")
                    self.workspace.write_json(
                        recovered,
                        redact_mapping(state.model_dump(mode="json", exclude_none=True)),
                    )
                    raise StateError(
                        f"{path} could not be read, so it was not overwritten. The "
                        f"state this session holds, including every id it created, "
                        f"was saved to {recovered}. Reconcile the two before "
                        f"continuing.\n{exc}"
                    ) from exc
                conflicts = _merge_from_disk(state, disk)
            self.save_state(state)
        if conflicts:
            raise ReconciliationError(
                "another session recorded different objects for the same plan "
                f"element(s): {'; '.join(conflicts)}. Both ids are kept in state. "
                "One of each pair is probably a duplicate on Meta - check before "
                "continuing."
            )

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


def _merge_from_disk(state: CampaignState, disk: CampaignState) -> list[str]:
    """Fold into *state* what *disk* has and it lacks. Returns plan-ref conflicts."""
    conflicts: list[str] = []
    known = {(o.type, o.id) for o in state.objects}
    for obj in disk.objects:
        if (obj.type, obj.id) in known:
            continue
        mine = state.by_plan_ref(obj.plan_ref) if obj.plan_ref else None
        if mine is not None and mine.id != obj.id:
            conflicts.append(f"{obj.plan_ref}: {mine.id} and {obj.id}")
        # Appended directly: record() would refuse the conflicting one, and
        # dropping it is exactly the loss this merge exists to prevent.
        state.objects.append(obj)
    for failure in disk.failures:
        if failure not in state.failures:
            state.failures.append(failure)
    if stage_order(disk.stage) > stage_order(state.stage):
        state.stage = disk.stage
    if disk.activated and not state.activated:
        state.activated, state.activated_at = True, disk.activated_at
    return conflicts
