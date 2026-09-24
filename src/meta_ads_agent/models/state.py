"""Persisted state: what actually exists on Meta, and how to resume.

The plan records intent. State records outcome. Keeping them separate is what
makes a partially-failed run resumable: the plan is unchanged, so the only
question is which stages already completed.

Two hard rules:

* **Ids are written the moment they exist**, before the next write starts. A
  crash between two creates must leave a resumable record, not an orphan.
* **No secrets, ever.** No tokens, no app secrets, no customer data. A test
  asserts this against every field name.

State is a convenience, never an authority. Meta is authoritative - see ADR-005.
"""

from __future__ import annotations

import datetime as _dt
from enum import StrEnum

from pydantic import Field, model_validator

from meta_ads_agent.models._common import (
    AccountId,
    AssetManifestSchemaVersion,
    StateSchemaVersion,
    StrictModel,
)


class Stage(StrEnum):
    """Pipeline stages, in execution order.

    A resume continues from the first stage that is not ``done``. The ordering
    is load-bearing; :func:`stage_order` depends on it.
    """

    PLANNED = "planned"
    VALIDATED = "validated"
    CAMPAIGN_CREATED = "campaign_created"
    AD_SETS_CREATED = "ad_sets_created"
    ASSETS_UPLOADED = "assets_uploaded"
    CREATIVES_CREATED = "creatives_created"
    ADS_CREATED = "ads_created"
    PREVIEWED = "previewed"
    QA_PASSED = "qa_passed"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTIVATED = "activated"


_STAGE_ORDER: tuple[Stage, ...] = (
    Stage.PLANNED,
    Stage.VALIDATED,
    Stage.CAMPAIGN_CREATED,
    Stage.AD_SETS_CREATED,
    Stage.ASSETS_UPLOADED,
    Stage.CREATIVES_CREATED,
    Stage.ADS_CREATED,
    Stage.PREVIEWED,
    Stage.QA_PASSED,
    Stage.AWAITING_APPROVAL,
    Stage.ACTIVATED,
)


def stage_order(stage: Stage) -> int:
    return _STAGE_ORDER.index(stage)


def next_stage(stage: Stage) -> Stage | None:
    index = stage_order(stage)
    return _STAGE_ORDER[index + 1] if index + 1 < len(_STAGE_ORDER) else None


class ObjectType(StrEnum):
    CAMPAIGN = "campaign"
    AD_SET = "ad_set"
    AD = "ad"
    CREATIVE = "creative"
    IMAGE = "image"
    VIDEO = "video"


class Provider(StrEnum):
    """Which layer created the object.

    Recorded per object so the agent can tell the user *why* a step used the
    fallback, and so a later migration can find objects created the old way.
    """

    OFFICIAL_MCP = "official_mcp"
    API_FALLBACK = "api_fallback"


class CreatedObject(StrictModel):
    """One object confirmed to exist on Meta."""

    id: str = Field(min_length=1)
    type: ObjectType
    name: str | None = None
    provider: Provider
    created_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    # Links an object back to the plan element that asked for it, so a resume
    # knows which ad set is missing rather than only how many exist.
    plan_ref: str | None = Field(default=None, description="Plan path, e.g. ad_sets[0].ads[1]")
    parent_id: str | None = None
    status_at_creation: str | None = Field(
        default=None, description="Status Meta reported, normally PAUSED"
    )

    @model_validator(mode="after")
    def _paused_or_explained(self) -> CreatedObject:
        spendable = {ObjectType.CAMPAIGN, ObjectType.AD_SET, ObjectType.AD}
        if (
            self.type in spendable
            and self.status_at_creation
            and self.status_at_creation.upper() == "ACTIVE"
        ):
            raise ValueError(
                f"{self.type.value} {self.id} was recorded as ACTIVE at creation. "
                "New objects are created PAUSED; an activation is recorded "
                "separately in the action log."
            )
        return self


class Failure(StrictModel):
    """A recorded failure, kept so a resume knows what went wrong.

    ``retry_safe`` is the important field. False means the write may have
    partially applied and Meta must be queried before it is attempted again -
    a timeout does not mean nothing happened.
    """

    stage: Stage
    at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    message: str
    meta_code: int | None = None
    meta_subcode: int | None = None
    retry_safe: bool = False
    plan_ref: str | None = None


class CampaignState(StrictModel):
    """``.meta-ads/campaigns/<slug>/state.json``."""

    schema_version: StateSchemaVersion = 1
    slug: str = Field(min_length=1)
    ad_account_id: AccountId
    plan_fingerprint: str | None = Field(
        default=None,
        description=(
            "SHA-256 of the validated plan. If the plan changed since these "
            "objects were created, a resume must stop and ask rather than "
            "applying a different plan to existing objects."
        ),
    )
    stage: Stage = Stage.PLANNED
    created_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    updated_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    objects: list[CreatedObject] = Field(default_factory=list)
    failures: list[Failure] = Field(default_factory=list)
    activated: bool = False
    activated_at: _dt.datetime | None = None
    notes: str | None = None

    # -- queries -----------------------------------------------------------
    def by_type(self, object_type: ObjectType) -> list[CreatedObject]:
        return [o for o in self.objects if o.type is object_type]

    def by_plan_ref(self, plan_ref: str) -> CreatedObject | None:
        for obj in self.objects:
            if obj.plan_ref == plan_ref:
                return obj
        return None

    @property
    def campaign_id(self) -> str | None:
        campaigns = self.by_type(ObjectType.CAMPAIGN)
        return campaigns[0].id if campaigns else None

    @property
    def used_fallback(self) -> bool:
        return any(o.provider is Provider.API_FALLBACK for o in self.objects)

    def is_complete_through(self, stage: Stage) -> bool:
        return stage_order(self.stage) >= stage_order(stage)

    def resume_from(self) -> Stage | None:
        """The first stage still to do, or None when the pipeline is finished."""
        return next_stage(self.stage)

    # -- mutation ----------------------------------------------------------
    def record(self, obj: CreatedObject) -> CreatedObject:
        """Add an object, or return the existing one for the same plan_ref.

        Idempotent by ``plan_ref``: a resume that re-runs a completed step must
        not append a second record for the same plan element. Duplicate ids are
        rejected outright as a bug.
        """
        if obj.plan_ref:
            existing = self.by_plan_ref(obj.plan_ref)
            if existing is not None:
                if existing.id != obj.id:
                    raise ValueError(
                        f"plan element {obj.plan_ref} already maps to "
                        f"{existing.type.value} {existing.id}, refusing to remap "
                        f"it to {obj.id}. Reconcile with Meta before continuing."
                    )
                return existing
        if any(o.id == obj.id and o.type is obj.type for o in self.objects):
            raise ValueError(f"{obj.type.value} {obj.id} is already recorded")
        self.objects.append(obj)
        self.updated_at = _dt.datetime.now(_dt.UTC)
        return obj

    def advance(self, stage: Stage) -> None:
        """Move the stage marker forward. Never backwards."""
        if stage_order(stage) < stage_order(self.stage):
            raise ValueError(
                f"refusing to move stage backwards from {self.stage.value} to {stage.value}"
            )
        self.stage = stage
        self.updated_at = _dt.datetime.now(_dt.UTC)

    def record_failure(self, failure: Failure) -> None:
        self.failures.append(failure)
        self.updated_at = _dt.datetime.now(_dt.UTC)


class AssetRecord(StrictModel):
    """One local file mapped to its remote identity.

    Keyed by content fingerprint plus account: the same file uploaded to two
    accounts is two remote objects, and a renamed file is the same asset.
    """

    fingerprint: str = Field(min_length=16, description="sha256:<hex> of the file bytes")
    ad_account_id: AccountId
    local_path: str
    size_bytes: int = Field(ge=0)
    kind: ObjectType
    image_hash: str | None = None
    video_id: str | None = None
    uploaded_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    provider: Provider = Provider.API_FALLBACK
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None

    @model_validator(mode="after")
    def _has_remote_identity(self) -> AssetRecord:
        if self.kind is ObjectType.IMAGE and not self.image_hash:
            raise ValueError("an image record needs image_hash")
        if self.kind is ObjectType.VIDEO and not self.video_id:
            raise ValueError("a video record needs video_id")
        if self.kind not in (ObjectType.IMAGE, ObjectType.VIDEO):
            raise ValueError(f"asset kind must be image or video, got {self.kind.value}")
        return self

    def key(self) -> str:
        return f"{self.ad_account_id}:{self.fingerprint}"


class AssetManifest(StrictModel):
    """``.meta-ads/assets/manifest.json``.

    Exists so a retry never re-uploads. Uploading a 200MB video twice is slow,
    and creating two Meta video objects for one file makes later reporting
    ambiguous.
    """

    schema_version: AssetManifestSchemaVersion = 1
    updated_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    assets: dict[str, AssetRecord] = Field(default_factory=dict)

    def lookup(self, fingerprint: str, ad_account_id: str) -> AssetRecord | None:
        return self.assets.get(f"{ad_account_id}:{fingerprint}")

    def put(self, record: AssetRecord) -> AssetRecord:
        """Insert, or return the existing record for the same content.

        First write wins. If the same bytes were already uploaded we keep the
        original remote id rather than replacing it, so previously created
        creatives keep pointing at a live object.
        """
        existing = self.assets.get(record.key())
        if existing is not None:
            return existing
        self.assets[record.key()] = record
        self.updated_at = _dt.datetime.now(_dt.UTC)
        return record
