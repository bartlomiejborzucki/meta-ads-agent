"""State persistence, idempotency, resume, and reconciliation.

The failure this exists to prevent: a campaign build that dies after the ad set
is created, then a rerun that creates a second campaign.
"""

from __future__ import annotations

import json

import pytest

from conftest import plan_dict
from meta_ads_agent.errors import ReconciliationError, StateError
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import (
    CampaignState,
    CreatedObject,
    Failure,
    ObjectType,
    Provider,
    Stage,
    next_stage,
    stage_order,
)
from meta_ads_agent.state.store import StateStore, fingerprint_matches, plan_fingerprint
from meta_ads_agent.workspace import Workspace


def campaign(slug: str = "acme-webinar") -> CreatedObject:
    return CreatedObject(
        id="120210000000001",
        type=ObjectType.CAMPAIGN,
        name="Acme | OUTCOME_LEADS | 2026-09-16",
        provider=Provider.OFFICIAL_MCP,
        plan_ref="campaign",
        status_at_creation="PAUSED",
    )


def ad_set(index: int = 0) -> CreatedObject:
    return CreatedObject(
        id=f"1202100000100{index}",
        type=ObjectType.AD_SET,
        name=f"ad set {index}",
        provider=Provider.OFFICIAL_MCP,
        plan_ref=f"ad_sets[{index}]",
        parent_id="120210000000001",
        status_at_creation="PAUSED",
    )


class TestPlanPersistence:
    def test_plan_round_trips_through_yaml(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        store.save_plan(plan)
        loaded = store.load_plan(plan.slug)
        assert loaded.campaign.name == plan.campaign.name
        assert loaded.campaign.ad_sets[0].budget.amount == plan.campaign.ad_sets[0].budget.amount

    def test_saved_plan_is_human_readable(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        StateStore(workspace).save_plan(plan)
        text = workspace.plan_file(plan.slug).read_text()
        assert "source of truth for INTENT" in text
        # Display amounts, not minor units, in a file a human reviews.
        assert "70" in text
        assert "7000" not in text

    def test_a_corrupt_plan_is_reported_not_silently_ignored(
        self, workspace: Workspace, plan
    ) -> None:  # type: ignore[no-untyped-def]
        StateStore(workspace).save_plan(plan)
        workspace.plan_file(plan.slug).write_text("campaign: {objective: 12345}\n")
        with pytest.raises(StateError, match="not a valid campaign plan"):
            StateStore(workspace).load_plan(plan.slug)

    def test_paths_with_spaces_and_unicode_work(self, spaced_workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(spaced_workspace)
        store.save_plan(plan)
        assert store.load_plan(plan.slug).slug == plan.slug


class TestFingerprint:
    def test_is_stable_across_saves(self, plan) -> None:  # type: ignore[no-untyped-def]
        assert plan_fingerprint(plan) == plan_fingerprint(plan.model_copy(deep=True))

    def test_ignores_metadata_that_does_not_change_what_gets_built(self, plan) -> None:  # type: ignore[no-untyped-def]
        other = plan.model_copy(deep=True)
        other.notes = "added a note"
        assert plan_fingerprint(plan) == plan_fingerprint(other)

    def test_changes_when_the_budget_changes(self, plan) -> None:  # type: ignore[no-untyped-def]
        other = CampaignPlanDocument.model_validate(plan_dict())
        other.campaign.ad_sets[0].budget.amount = other.campaign.ad_sets[0].budget.amount * 2
        assert plan_fingerprint(plan) != plan_fingerprint(other)

    def test_changes_when_copy_changes(self, plan) -> None:  # type: ignore[no-untyped-def]
        other = plan.model_copy(deep=True)
        other.campaign.ad_sets[0].ads[0].creative.variants[0].headline = "Different"
        assert plan_fingerprint(plan) != plan_fingerprint(other)

    def test_a_field_left_at_its_default_does_not_count(self) -> None:
        # What a new release adding a defaulted field looks like to an old
        # plan: the field appears with its default. That must not read as an
        # edit, or every in-flight campaign would refuse to resume.
        raw = plan_dict()
        explicit = plan_dict()
        explicit["campaign"]["ad_sets"][0]["targeting"]["genders"] = "all"
        explicit["campaign"]["buying_type"] = "AUCTION"
        assert plan_fingerprint(CampaignPlanDocument.model_validate(raw)) == plan_fingerprint(
            CampaignPlanDocument.model_validate(explicit)
        )

    def test_the_algorithm_is_named_in_the_fingerprint(self, plan) -> None:  # type: ignore[no-untyped-def]
        assert plan_fingerprint(plan).startswith("v2:sha256:")
        assert fingerprint_matches(plan_fingerprint(plan), plan)

    def test_a_fingerprint_recorded_by_0_2_still_matches_its_plan(self) -> None:
        # The shipped example was written by 0.1; its state must still resume.
        from pathlib import Path

        import yaml

        examples = Path(__file__).resolve().parents[1] / "examples"
        doc = CampaignPlanDocument.model_validate(
            yaml.safe_load((examples / "campaign-plan.yaml").read_text())
        )
        recorded = json.loads((examples / "state.json").read_text())["plan_fingerprint"]
        assert recorded.startswith("sha256:")
        assert fingerprint_matches(recorded, doc)

        edited = doc.model_copy(deep=True)
        edited.campaign.name = "Something else"
        assert not fingerprint_matches(recorded, edited)


class TestIdempotency:
    def test_recording_the_same_plan_element_twice_does_not_duplicate(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        first = state.record(campaign())
        second = state.record(campaign())
        assert len(state.objects) == 1
        assert first.id == second.id

    def test_remapping_a_plan_element_to_a_different_id_is_refused(self) -> None:
        # Two Meta objects for one plan element means a duplicate was created.
        state = CampaignState(slug="s", ad_account_id="act_1")
        state.record(campaign())
        other = campaign()
        object.__setattr__(other, "id", "999999999999999")
        with pytest.raises(ValueError, match="refusing to remap"):
            state.record(other)

    def test_recording_the_same_id_twice_without_a_plan_ref_is_a_bug(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        bare = CreatedObject(
            id="120",
            type=ObjectType.AD,
            provider=Provider.OFFICIAL_MCP,
            status_at_creation="PAUSED",
        )
        state.record(bare)
        with pytest.raises(ValueError, match="already recorded"):
            state.record(bare.model_copy())

    def test_ids_are_flushed_to_disk_immediately(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        # An id on Meta but not on disk is an orphan waiting to be duplicated.
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())
        raw = json.loads(workspace.state_file(plan.slug).read_text())
        assert raw["objects"][0]["id"] == "120210000000001"


class TestPausedByDefault:
    def test_recording_an_active_new_object_is_refused(self) -> None:
        with pytest.raises(ValueError, match="created PAUSED"):
            CreatedObject(
                id="120",
                type=ObjectType.CAMPAIGN,
                provider=Provider.OFFICIAL_MCP,
                status_at_creation="ACTIVE",
            )

    def test_a_creative_has_no_status_so_it_is_unaffected(self) -> None:
        obj = CreatedObject(id="120", type=ObjectType.CREATIVE, provider=Provider.API_FALLBACK)
        assert obj.status_at_creation is None


class TestStageProgression:
    def test_stages_advance_forward(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        assert state.stage is Stage.PLANNED
        state.advance(Stage.VALIDATED)
        state.advance(Stage.CAMPAIGN_CREATED)
        assert state.stage is Stage.CAMPAIGN_CREATED

    def test_stages_never_go_backwards(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        state.advance(Stage.ADS_CREATED)
        with pytest.raises(ValueError, match="backwards"):
            state.advance(Stage.CAMPAIGN_CREATED)

    def test_resume_points_at_the_next_stage(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        state.advance(Stage.AD_SETS_CREATED)
        assert state.resume_from() is Stage.ASSETS_UPLOADED

    def test_the_final_stage_has_nothing_to_resume(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        state.advance(Stage.ACTIVATED)
        assert state.resume_from() is None

    def test_activation_is_the_last_stage(self) -> None:
        assert next_stage(Stage.ACTIVATED) is None
        assert stage_order(Stage.ACTIVATED) > stage_order(Stage.QA_PASSED)

    def test_approval_comes_before_activation(self) -> None:
        assert stage_order(Stage.AWAITING_APPROVAL) < stage_order(Stage.ACTIVATED)

    def test_preview_and_qa_come_before_approval(self) -> None:
        assert stage_order(Stage.PREVIEWED) < stage_order(Stage.AWAITING_APPROVAL)
        assert stage_order(Stage.QA_PASSED) < stage_order(Stage.AWAITING_APPROVAL)


class TestResumeAfterPartialCreation:
    def test_an_interrupted_build_resumes_without_duplicating(
        self, workspace: Workspace, plan
    ) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        store.save_plan(plan)

        # Run 1: campaign created, then the process dies mid ad-set creation.
        state = store.load_or_create_state(plan)
        store.advance(state, Stage.VALIDATED)
        store.record_object(state, campaign())
        store.advance(state, Stage.CAMPAIGN_CREATED)
        store.record_failure(
            state,
            Failure(
                stage=Stage.AD_SETS_CREATED,
                message="socket closed",
                retry_safe=False,
            ),
        )

        # Run 2: a fresh store, as a new process would have.
        resumed = StateStore(workspace).load_or_create_state(store.load_plan(plan.slug))
        assert resumed.campaign_id == "120210000000001"
        assert resumed.stage is Stage.CAMPAIGN_CREATED
        assert resumed.resume_from() is Stage.AD_SETS_CREATED
        assert len(resumed.by_type(ObjectType.CAMPAIGN)) == 1

        # Continuing records the ad set without a second campaign.
        StateStore(workspace).record_object(resumed, ad_set(0))
        assert len(resumed.by_type(ObjectType.CAMPAIGN)) == 1
        assert len(resumed.by_type(ObjectType.AD_SET)) == 1

    def test_a_failure_is_marked_not_retry_safe_so_a_write_is_verified_first(
        self, workspace: Workspace, plan
    ) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_failure(
            state, Failure(stage=Stage.ADS_CREATED, message="timeout", retry_safe=False)
        )
        reloaded = store.load_state(plan.slug)
        assert reloaded.failures[0].retry_safe is False

    def test_a_changed_plan_blocks_a_resume(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        # Continuing would apply a different plan to existing structure.
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())

        edited = plan.model_copy(deep=True)
        edited.campaign.ad_sets[0].ads[0].creative.variants[0].headline = "New headline"
        with pytest.raises(ReconciliationError, match="changed after"):
            store.load_or_create_state(edited)

    def test_a_changed_plan_with_no_objects_yet_is_fine(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        store.load_or_create_state(plan)
        edited = plan.model_copy(deep=True)
        edited.campaign.ad_sets[0].ads[0].creative.variants[0].headline = "New headline"
        assert store.load_or_create_state(edited).slug == plan.slug

    def test_state_from_another_account_is_refused(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        store.load_or_create_state(plan)
        other = plan.model_copy(deep=True)
        other.ad_account_id = "act_9999999999"
        with pytest.raises(ReconciliationError, match="belongs to account"):
            store.load_or_create_state(other)


class TestReconciliation:
    def test_agreement_produces_no_differences(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())
        remote = {
            "120210000000001": {
                "status": "PAUSED",
                "name": "Acme | OUTCOME_LEADS | 2026-09-16",
            }
        }
        assert store.reconcile(state, remote) == []

    def test_a_status_change_made_in_ads_manager_is_reported(
        self, workspace: Workspace, plan
    ) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())
        differences = store.reconcile(state, {"120210000000001": {"status": "ACTIVE"}})
        assert any("ACTIVE on Meta" in d for d in differences)

    def test_a_rename_made_in_ads_manager_is_reported(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())
        differences = store.reconcile(
            state, {"120210000000001": {"status": "PAUSED", "name": "Renamed by hand"}}
        )
        assert any("Renamed by hand" in d for d in differences)

    def test_a_deleted_object_is_reported(self, workspace: Workspace, plan) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())
        differences = store.reconcile(state, {"120210000000001": {}})
        assert any("no longer exists" in d for d in differences)

    def test_an_unchecked_object_is_reported_rather_than_assumed_fine(
        self, workspace: Workspace, plan
    ) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        store.record_object(state, campaign())
        differences = store.reconcile(state, {})
        assert any("was not checked" in d for d in differences)


class TestSecretsNeverReachState:
    def test_a_token_smuggled_into_state_is_scrubbed_on_write(
        self, workspace: Workspace, plan
    ) -> None:  # type: ignore[no-untyped-def]
        store = StateStore(workspace)
        state = store.load_or_create_state(plan)
        state.notes = "debug: access_token=EAAnotarealtoken0000000"
        store.save_state(state)
        text = workspace.state_file(plan.slug).read_text()
        assert "EAAnotarealtoken0000000" not in text
        assert "REDACTED" in text

    def test_the_state_model_has_no_credential_fields(self) -> None:
        # Structural: no field should invite a secret in the first place.
        forbidden = ("token", "secret", "password", "credential", "api_key")
        for name in CampaignState.model_fields:
            assert not any(f in name.lower() for f in forbidden), name
        for name in CreatedObject.model_fields:
            assert not any(f in name.lower() for f in forbidden), name

    def test_provider_is_recorded_so_fallback_use_is_explainable(self) -> None:
        state = CampaignState(slug="s", ad_account_id="act_1")
        state.record(CreatedObject(id="1", type=ObjectType.VIDEO, provider=Provider.API_FALLBACK))
        assert state.used_fallback is True
