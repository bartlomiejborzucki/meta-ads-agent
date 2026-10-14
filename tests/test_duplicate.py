"""duplicate-plan: a campaign read from Meta, turned into a new plan.

The source below uses the Marketing API's field names, as the agent saves
what it read. Every duplicated plan must then pass the same validation as a
plan written by hand - the point of duplicating through a plan.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from meta_ads_agent.cli.main import main
from meta_ads_agent.duplicate import duplicate_plan
from meta_ads_agent.errors import ValidationError
from meta_ads_agent.validation import validate_plan

LINK = "https://acme.example.com/webinar"


def source() -> dict[str, Any]:
    identity = {"page_id": "1111111111", "instagram_user_id": "2222222222"}
    return {
        "ad_account_id": "act_1234567890",
        "currency": "PLN",
        "campaign": {
            "id": "120210000000001",
            "name": "Acme | Webinar | Q3",
            "objective": "OUTCOME_LEADS",
            "buying_type": "AUCTION",
            "special_ad_categories": [],
            "status": "ACTIVE",
            "stop_time": "2026-09-30T23:59:00+0200",
        },
        "ad_sets": [
            {
                "name": "PL broad 25-55",
                "status": "ACTIVE",
                "daily_budget": "7000",
                "optimization_goal": "OFFSITE_CONVERSIONS",
                "billing_event": "IMPRESSIONS",
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "start_time": "2026-09-01T00:00:00+0200",
                "promoted_object": {"pixel_id": "1234567890", "custom_event_type": "LEAD"},
                "dsa_beneficiary": "Acme Sp. z o.o.",
                "dsa_payor": "Acme Sp. z o.o.",
                "targeting": {
                    "geo_locations": {"countries": ["PL"], "location_types": ["home"]},
                    "age_min": 25,
                    "age_max": 55,
                    "genders": [1, 2],
                    "excluded_custom_audiences": [{"id": "3333333333", "name": "Buyers"}],
                    "targeting_automation": {"advantage_audience": 0},
                    "flexible_spec": [{"interests": [{"id": "6003", "name": "Webinars"}]}],
                    "publisher_platforms": ["facebook", "instagram"],
                    "facebook_positions": ["feed"],
                    "instagram_positions": ["stream", "story"],
                },
                "ads": [
                    {
                        "name": "Image",
                        "status": "ACTIVE",
                        "creative": {
                            "object_story_spec": {
                                **identity,
                                "link_data": {
                                    "link": LINK,
                                    "message": "Join us",
                                    "name": "Free webinar",
                                    "image_hash": "abc123",
                                    "call_to_action": {"type": "SIGN_UP"},
                                },
                            }
                        },
                    },
                    {
                        "name": "Carousel",
                        "creative": {
                            "object_story_spec": {
                                **identity,
                                "link_data": {
                                    "link": LINK,
                                    "message": "Three reasons",
                                    "child_attachments": [
                                        {"link": LINK, "name": "One", "image_hash": "h1"},
                                        {"link": LINK, "name": "Two", "video_id": "700000000001"},
                                    ],
                                },
                            }
                        },
                    },
                    {
                        "name": "Video",
                        "creative": {
                            "object_story_spec": {
                                **identity,
                                "video_data": {
                                    "video_id": "700000000002",
                                    "message": "Watch",
                                    "title": "Webinar",
                                    "call_to_action": {
                                        "type": "LEARN_MORE",
                                        "value": {"link": LINK},
                                    },
                                },
                            }
                        },
                    },
                    {
                        "name": "Page post",
                        "creative": {"object_story_id": "1111111111_4444444444"},
                    },
                ],
            }
        ],
    }


def build(src: dict[str, Any] | None = None, **kwargs: Any):  # type: ignore[no-untyped-def]
    return duplicate_plan(src or source(), slug=kwargs.pop("slug", "acme-webinar-q4"), **kwargs)


class TestMapping:
    def test_everything_is_paused_and_renamed(self) -> None:
        doc = build().document
        assert doc.campaign.name == "Acme | Webinar | Q3 (copy)"
        assert doc.campaign.status == "PAUSED"
        assert all(s.status == "PAUSED" for s in doc.campaign.ad_sets)
        assert all(a.status == "PAUSED" for s in doc.campaign.ad_sets for a in s.ads)

    def test_a_budget_in_minor_units_becomes_a_display_amount(self) -> None:
        budget = build().document.campaign.ad_sets[0].budget
        assert budget is not None
        assert (budget.level, budget.type, budget.amount, budget.currency) == (
            "ad_set", "daily", Decimal("70.00"), "PLN",
        )  # fmt: skip

    def test_without_a_currency_a_budget_is_refused_not_guessed(self) -> None:
        src = source()
        del src["currency"]
        with pytest.raises(ValidationError, match="minor units, and no currency"):
            build(src)

    def test_targeting_maps_what_the_plan_models_and_keeps_the_rest(self) -> None:
        t = build().document.campaign.ad_sets[0].targeting
        assert t.countries == ["PL"]
        assert (t.age_min, t.age_max, t.genders) == (25, 55, "all")
        assert t.excluded_custom_audience_ids == ["3333333333"]
        assert t.advantage_audience is False
        assert t.raw["flexible_spec"][0]["interests"][0]["id"] == "6003"  # type: ignore[index]
        assert t.raw["geo_locations"] == {"countries": ["PL"], "location_types": ["home"]}

    def test_placements_and_tracking(self) -> None:
        ad_set = build().document.campaign.ad_sets[0]
        assert ad_set.placements.mode == "manual"
        assert ad_set.placements.positions == [
            "facebook_feed", "instagram_feed", "instagram_stories",
        ]  # fmt: skip
        assert ad_set.tracking.dataset_id == "1234567890"
        assert ad_set.tracking.conversion_event == "LEAD"

    def test_each_creative_shape(self) -> None:
        ads = {a.name: a.creative for a in build().document.campaign.ad_sets[0].ads}
        assert ads["Image"].mode == "single_image"
        assert ads["Image"].assets[0].image_hash == "abc123"
        assert ads["Image"].variants[0].headline == "Free webinar"
        assert ads["Carousel"].mode == "carousel"
        assert ads["Carousel"].cards[1].asset.video_id == "700000000001"
        assert ads["Video"].mode == "single_video"
        assert ads["Video"].destination_url == LINK
        assert ads["Page post"].mode == "existing_post"
        assert ads["Page post"].page_id == "1111111111"

    def test_schedules_are_not_copied_and_that_is_said(self) -> None:
        result = build()
        assert result.document.campaign.ad_sets[0].schedule.start is None
        assert any("schedules were not copied" in n for n in result.notes)

    def test_a_campaign_budget_wins_over_ad_set_budgets(self) -> None:
        src = source()
        src["campaign"]["daily_budget"] = "15000"
        result = build(src)
        assert result.document.campaign.budget is not None
        assert result.document.campaign.budget.amount == Decimal("150.00")
        assert result.document.campaign.ad_sets[0].budget is None
        assert any("campaign budget governs" in n for n in result.notes)

    def test_a_multi_variant_creative_is_refused_by_name(self) -> None:
        src = source()
        src["ad_sets"][0]["ads"][0]["creative"] = {"asset_feed_spec": {"bodies": []}}
        with pytest.raises(ValidationError, match=r"'Image'.*asset_feed_spec"):
            build(src)

    def test_targeting_without_countries_is_refused(self) -> None:
        src = source()
        src["ad_sets"][0]["targeting"]["geo_locations"] = {"regions": [{"key": "3847"}]}
        with pytest.raises(ValidationError, match=r"geo_locations\.countries"):
            build(src)


class TestTheCopyValidates:
    def test_a_duplicated_plan_passes_validation(self, account) -> None:  # type: ignore[no-untyped-def]
        report = validate_plan(build().document, account=account, check_assets=False)
        assert report.ok, report.render()


class TestCommand:
    @pytest.fixture
    def saved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
        path = tmp_path / "source.json"
        path.write_text(json.dumps(source()))
        return path

    def test_without_write_it_prints_and_writes_nothing(
        self, saved: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["duplicate-plan", str(saved), "--slug", "acme-q4"]) == 0
        out = capsys.readouterr().out
        assert "all PAUSED" in out
        assert "nothing written" in out
        assert not (saved.parent / ".meta-ads").exists()

    def test_write_saves_a_plan_and_refuses_to_overwrite(
        self, saved: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["init"])
        capsys.readouterr()
        argv = ["duplicate-plan", str(saved), "--slug", "acme-q4", "--write", "--json"]
        assert main(argv) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["written"] is True
        assert payload["ads"] == 4
        plan = yaml.safe_load(Path(payload["plan"]).read_text(encoding="utf-8"))
        assert plan["campaign"]["status"] == "PAUSED"

        assert main(argv) == 1
        assert "already exists" in capsys.readouterr().err

    def test_a_source_it_cannot_map_exits_2(
        self, saved: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = copy.deepcopy(source())
        broken["ad_sets"] = []
        saved.write_text(json.dumps(broken))
        assert main(["duplicate-plan", str(saved), "--slug", "x"]) == 2
        assert "no ad_sets" in capsys.readouterr().err
