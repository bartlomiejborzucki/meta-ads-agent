"""Files written by every earlier release, read by this one.

docs/reference/compatibility.md promises that a workspace written by an
earlier release keeps working after an upgrade. These tests hold that to the
files those releases actually shipped (tests/fixtures/written-by/), not to
files written with today's code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from meta_ads_agent.models.brand import BrandConfig, Offer
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import CampaignState
from meta_ads_agent.state.store import StateStore, fingerprint_matches
from meta_ads_agent.validation import validate_plan
from meta_ads_agent.workspace import Workspace

WRITTEN_BY = Path(__file__).parent / "fixtures" / "written-by"
RELEASES = sorted(p.name for p in WRITTEN_BY.iterdir() if p.is_dir())


def load(release: str, name: str) -> object:
    text = (WRITTEN_BY / release / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else yaml.safe_load(text)


def test_there_is_a_fixture_for_each_earlier_release() -> None:
    assert RELEASES == ["0.1.0", "0.2.0"]


@pytest.mark.parametrize("release", RELEASES)
class TestReadsWhatEarlierReleasesWrote:
    def test_the_brand_config(self, release: str) -> None:
        assert BrandConfig.model_validate(load(release, "brand.yaml")).name

    def test_the_offer(self, release: str) -> None:
        assert Offer.model_validate(load(release, "offer.yaml"))

    @pytest.mark.parametrize("name", ["campaign-plan.yaml", "campaign-plan-template.yaml"])
    def test_the_plans_validate(self, release: str, name: str) -> None:
        doc = CampaignPlanDocument.model_validate(load(release, name))
        report = validate_plan(doc, check_assets=False)
        assert report.findings  # it ran; errors are the plan's own business

    def test_the_state_still_resumes_against_its_plan(self, release: str, tmp_path: Path) -> None:
        # The case that matters: a campaign part way through a build on the
        # old release, resumed on this one. A changed fingerprint would block it.
        doc = CampaignPlanDocument.model_validate(load(release, "campaign-plan.yaml"))
        raw_state = load(release, "state.json")
        state = CampaignState.model_validate(raw_state)
        assert state.plan_fingerprint
        assert fingerprint_matches(state.plan_fingerprint, doc)

        workspace = Workspace.at(tmp_path / ".meta-ads")
        workspace.create()
        path = workspace.state_file(doc.slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw_state = {**raw_state, "slug": doc.slug, "ad_account_id": doc.ad_account_id}
        path.write_text(json.dumps(raw_state))
        resumed = StateStore(workspace).load_or_create_state(doc)
        assert len(resumed.objects) == len(state.objects)

    def test_the_account_template_reads_as_not_yet_read(self, release: str) -> None:
        raw = load(release, "account-template.yaml")
        assert isinstance(raw, dict)
        assert raw.get("id") is None


class TestRefusesWhatALaterReleaseWrote:
    @pytest.mark.parametrize(
        ("model", "raw"),
        [
            (BrandConfig, {"schema_version": 2, "name": "Acme"}),
            (CampaignState, {"schema_version": 2, "slug": "x", "ad_account_id": "act_1"}),
        ],
    )
    def test_a_newer_schema_version_is_an_error_that_says_upgrade(
        self, model: type, raw: dict[str, object]
    ) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="newer meta-ads-agent"):
            model.model_validate(raw)

    def test_a_newer_plan_is_refused_too(self) -> None:
        from pydantic import ValidationError

        raw = load("0.2.0", "campaign-plan.yaml")
        assert isinstance(raw, dict)
        with pytest.raises(ValidationError, match="upgrade"):
            CampaignPlanDocument.model_validate({**raw, "schema_version": 9})
