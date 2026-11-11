"""``plan-calls``: a plan as the Meta MCP calls that build it.

The translation used to happen in the conversation - display amounts to minor
units, a targeting object to a JSON string. These tests hold it to the plan,
and hold its argument names to the tool schemas as read on 2026-11-11
(tests/fixtures/mcp-schemas-2026-11-11.json). Nothing here calls Meta.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import plan_dict
from meta_ads_agent.mcp_calls import SCHEMA_READ, Call, CallPlan, compile_calls
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.models.state import CampaignState, CreatedObject, ObjectType, Provider
from meta_ads_agent.validation import AccountContext

SCHEMAS = json.loads(
    (Path(__file__).parent / "fixtures" / "mcp-schemas-2026-11-11.json").read_text("utf-8")
)
ACCOUNT = AccountContext(id="act_1234567890", currency="PLN", currency_offset=100)


def build(mutate=None, **overrides: Any) -> CampaignPlanDocument:  # type: ignore[no-untyped-def]
    raw = plan_dict(**overrides)
    if mutate:
        mutate(raw)
    return CampaignPlanDocument.model_validate(raw)


def creative(raw: dict[str, Any]) -> dict[str, Any]:
    return raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]


def compiled(mutate=None, **kwargs: Any) -> CallPlan:  # type: ignore[no-untyped-def]
    kwargs.setdefault("account", ACCOUNT)
    return compile_calls(build(mutate), **kwargs)


def call(plan: CallPlan, tool: str, index: int = 0) -> Call:
    return [c for c in plan.calls if c.tool == tool][index]


def every_shape() -> list[CallPlan]:
    """One plan per creative shape the compiler knows, for the schema checks."""

    def video(raw):  # type: ignore[no-untyped-def]
        c = creative(raw)
        c.update(mode="single_video", assets=[{"video_id": "700000000000031"}])
        c["thumbnail"] = {"image_hash": "thumb0001"}

    def carousel(raw):  # type: ignore[no-untyped-def]
        c = creative(raw)
        c.update(mode="carousel")
        c.pop("assets")
        c["cards"] = [
            {
                "asset": {"image_hash": "aaa111"},
                "headline": "One",
                "link": "https://a.example.com/1",
            },
            {"asset": {"video_id": "222"}, "description": "Two"},
        ]

    def multi(raw):  # type: ignore[no-untyped-def]
        c = creative(raw)
        c.update(mode="multi_variant", assets=[{"image_hash": "aaa111"}, {"image_hash": "bbb222"}])
        c["variants"] = [
            {"angle": "a", "primary_text": "First.", "headline": "H1", "description": "D1"},
            {"angle": "b", "primary_text": "Second.", "headline": "H2", "description": "D2"},
        ]

    def pinned(raw):  # type: ignore[no-untyped-def]
        c = creative(raw)
        c.update(
            mode="multi_variant",
            assets=[
                {"image_hash": "wide0001"},
                {"image_hash": "tall0001", "placement": "instagram_stories"},
                {"image_hash": "reel0001", "placement": "facebook_reels"},
            ],
        )
        c["advantage"] = {"enhancements": {"image_touchups": False, "text_optimizations": True}}

    def post(raw):  # type: ignore[no-untyped-def]
        c = creative(raw)
        for key in ("assets", "variants", "destination_url"):
            c.pop(key)
        c.update(mode="existing_post", post_id="1111111111_999")

    def everything_else(raw):  # type: ignore[no-untyped-def]
        campaign = raw["campaign"]
        campaign["special_ad_categories"] = ["HOUSING"]
        campaign["spend_cap"] = {"amount": "5000", "currency": "PLN"}
        campaign["schedule"] = {"start": "2026-10-01T00:00:00Z", "end": "2026-10-31T00:00:00Z"}
        ad_set = campaign["ad_sets"][0]
        ad_set.update(bid_strategy="COST_CAP", bid_amount="12.50", billing_event="IMPRESSIONS")
        ad_set["schedule"] = {"start": "2026-10-01T00:00:00Z", "end": "2026-10-31T00:00:00Z"}
        ad_set["placements"] = {"mode": "manual", "positions": ["facebook_feed"]}
        creative(raw)["display_link"] = "acme.example.com"
        creative(raw)["instagram_account_id"] = "2222222222"

    def campaign_budget(raw):  # type: ignore[no-untyped-def]
        ad_set = raw["campaign"]["ad_sets"][0]
        raw["campaign"]["budget"] = {
            **ad_set.pop("budget"),
            "level": "campaign",
            "type": "lifetime",
        }
        ad_set["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"

    shapes = [None, video, carousel, multi, pinned, post, everything_else, campaign_budget]
    return [compiled(shape) for shape in shapes]


class TestSchemas:
    def test_the_fixture_is_the_schema_the_compiler_says_it_follows(self) -> None:
        assert SCHEMAS["read"] == SCHEMA_READ

    def test_only_arguments_the_schemas_listed_are_sent(self) -> None:
        for plan in every_shape():
            for c in plan.calls:
                known = SCHEMAS["tools"][c.tool]
                assert set(c.args) <= set(known["properties"]), (c.tool, c.args)
                for name, fields in known.get("nested", {}).items():
                    for item in c.args.get(name, []):
                        assert set(item) <= set(fields), (c.tool, name, item)

    def test_every_required_argument_is_sent_or_asked_for(self) -> None:
        for plan in every_shape():
            for c in plan.calls:
                missing = set(SCHEMAS["tools"][c.tool]["required"]) - set(c.args)
                assert not missing or c.needs, (c.tool, missing)

    def test_nested_arguments_meta_takes_as_strings_are_strings(self) -> None:
        for plan in every_shape():
            for c in plan.calls:
                for name in (
                    "targeting",
                    "promoted_object",
                    "creative",
                    "special_ad_categories",
                    "special_ad_category_country",
                    "degrees_of_freedom_spec",
                ):
                    if name in c.args:
                        assert isinstance(c.args[name], str), (c.tool, name)
                        json.loads(c.args[name])

    def test_nothing_is_created_with_a_status(self) -> None:
        # The create tools take none: everything arrives PAUSED, or as a draft.
        for plan in every_shape():
            assert not [c.tool for c in plan.calls if "status" in c.args]


class TestOrderAndReferences:
    def test_campaign_ad_set_creative_ad_in_that_order(self) -> None:
        plan = compiled()
        assert [(c.step, c.tool, c.plan_ref) for c in plan.calls] == [
            (1, "ads_create_campaign", "campaign"),
            (2, "ads_create_ad_set", "ad_sets[0]"),
            (3, "ads_create_creative", "ad_sets[0].ads[0].creative"),
            (4, "ads_create_ad", "ad_sets[0].ads[0]"),
        ]
        assert plan.complete

    def test_an_id_that_does_not_exist_yet_is_a_named_placeholder(self) -> None:
        plan = compiled()
        ad_set = call(plan, "ads_create_ad_set")
        assert ad_set.args["campaign_id"] == "<id:campaign>"
        assert ad_set.refs == {"campaign_id": "campaign"}
        ad = call(plan, "ads_create_ad")
        assert json.loads(ad.args["creative"]) == {"creative_id": "<id:ad_sets[0].ads[0].creative>"}
        assert ad.refs == {
            "creative": "ad_sets[0].ads[0].creative",
            "ad_set_id": "ad_sets[0]",
        }

    def test_the_account_id_is_sent_bare(self) -> None:
        assert {c.args["ad_account_id"] for c in compiled().calls} == {"1234567890"}


class TestMoney:
    def test_a_display_budget_becomes_minor_units(self) -> None:
        assert call(compiled(), "ads_create_ad_set").args["daily_budget"] == 7000

    def test_the_accounts_own_offset_is_used(self) -> None:
        # A currency with no minor unit: 70 is 70, not 7000.
        def yen(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["budget"].update(currency="JPY", amount="7000")

        jpy = AccountContext(id="act_1234567890", currency="JPY", currency_offset=1)
        assert call(compiled(yen, account=jpy), "ads_create_ad_set").args["daily_budget"] == 7000

    def test_a_campaign_budget_goes_on_the_campaign_with_the_bid_strategy(self) -> None:
        def cbo(raw):  # type: ignore[no-untyped-def]
            ad_set = raw["campaign"]["ad_sets"][0]
            raw["campaign"]["budget"] = {**ad_set.pop("budget"), "level": "campaign"}
            ad_set["bid_strategy"] = "COST_CAP"
            ad_set["bid_amount"] = "12.50"

        plan = compiled(cbo)
        campaign = call(plan, "ads_create_campaign")
        ad_set = call(plan, "ads_create_ad_set")
        assert campaign.args["campaign_daily_budget"] == 7000
        assert campaign.args["campaign_bid_strategy"] == "COST_CAP"
        assert "daily_budget" not in ad_set.args and "bid_strategy" not in ad_set.args
        assert ad_set.args["bid_amount"] == 1250

    def test_a_spend_cap_is_minor_units_too(self) -> None:
        def cap(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["spend_cap"] = {"amount": "5000", "currency": "PLN"}

        assert call(compiled(cap), "ads_create_campaign").args["campaign_spend_cap"] == 500000

    def test_without_the_accounts_offset_it_says_so(self) -> None:
        plan = compile_calls(build())
        assert any("built-in currency table" in note for note in plan.notes)


class TestTargeting:
    def targeting(self, mutate=None) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        return json.loads(call(compiled(mutate), "ads_create_ad_set").args["targeting"])

    def test_countries_and_ages(self) -> None:
        assert self.targeting() == {
            "geo_locations": {"countries": ["PL"]},
            "age_min": 25,
            "age_max": 55,
        }

    def test_what_the_plan_models_wins_over_raw(self) -> None:
        # A duplicated plan keeps the source's geo_locations in raw; an edit to
        # the plan's countries must be what is sent.
        def edited(raw):  # type: ignore[no-untyped-def]
            t = raw["campaign"]["ad_sets"][0]["targeting"]
            t["countries"] = ["DE"]
            t["raw"] = {
                "geo_locations": {"countries": ["PL"], "location_types": ["home"]},
                "publisher_platforms": ["facebook"],
                "flexible_spec": [{"interests": [{"id": "6003"}]}],
            }
            raw["campaign"]["ad_sets"][0]["placements"] = {
                "mode": "manual",
                "positions": ["instagram_stories", "instagram_feed"],
            }

        spec = self.targeting(edited)
        assert spec["geo_locations"] == {"countries": ["DE"], "location_types": ["home"]}
        assert spec["publisher_platforms"] == ["instagram"]
        assert spec["instagram_positions"] == ["story", "stream"]
        assert spec["flexible_spec"] == [{"interests": [{"id": "6003"}]}]

    def test_whole_platforms(self) -> None:
        def platforms(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["placements"] = {
                "mode": "manual",
                "platforms": ["instagram"],
            }

        spec = self.targeting(platforms)
        assert spec["publisher_platforms"] == ["instagram"]
        assert "instagram_positions" not in spec

    def test_audiences_genders_and_an_age_suggestion(self) -> None:
        def audience(raw):  # type: ignore[no-untyped-def]
            t = raw["campaign"]["ad_sets"][0]["targeting"]
            t.update(
                genders="female",
                custom_audience_ids=["111"],
                excluded_custom_audience_ids=["222"],
                advantage_audience=True,
                age_suggestion={"min": 30, "max": 50},
            )
            t.pop("age_max")
            t["age_min"] = 18

        spec = self.targeting(audience)
        assert spec["genders"] == [2]
        assert spec["custom_audiences"] == [{"id": "111"}]
        assert spec["excluded_custom_audiences"] == [{"id": "222"}]
        assert spec["targeting_automation"] == {"advantage_audience": 1}
        assert spec["age_range"] == [30, 50]

    def test_turning_advantage_audience_off_needs_its_reason(self) -> None:
        def off(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["targeting"]["advantage_audience"] = False

        plan = compiled(off)
        ad_set = call(plan, "ads_create_ad_set")
        assert json.loads(ad_set.args["targeting"])["targeting_automation"] == {
            "advantage_audience": 0
        }
        assert any("advantage_audience_off_reason" in need for need in ad_set.needs)
        assert not plan.complete

    def test_interest_names_are_not_sent_as_ids(self) -> None:
        def interests(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["targeting"]["interests"] = ["Webinars"]

        ad_set = call(compiled(interests), "ads_create_ad_set")
        assert "Webinars" not in ad_set.args["targeting"]
        assert any("interest ids only" in need for need in ad_set.needs)


class TestAdSet:
    def test_tracking_becomes_the_promoted_object(self) -> None:
        promoted = json.loads(call(compiled(), "ads_create_ad_set").args["promoted_object"])
        assert promoted == {"pixel_id": "1234567890", "custom_event_type": "LEAD"}

    def test_eu_transparency_fields_come_from_the_plan_then_the_brand(self) -> None:
        args = call(compiled(), "ads_create_ad_set").args
        assert args["dsa_beneficiary"] == "Acme Sp. z o.o."

        def none(raw):  # type: ignore[no-untyped-def]
            raw["campaign"].pop("dsa")

        brand = BrandConfig.model_validate(
            {"name": "Acme", "dsa": {"beneficiary": "Acme Ltd", "payor": "Acme Ltd"}}
        )
        assert (
            call(compiled(none, brand=brand), "ads_create_ad_set").args["dsa_payor"] == "Acme Ltd"
        )
        bare = call(compiled(none), "ads_create_ad_set")
        assert "dsa_payor" not in bare.args
        assert any("dsa_beneficiary" in need for need in bare.needs)

    def test_no_optimisation_goal_is_asked_for_not_guessed(self) -> None:
        def none(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0].pop("optimization_goal")

        ad_set = call(compiled(none), "ads_create_ad_set")
        assert "optimization_goal" not in ad_set.args
        assert any("valid_optimization_goals" in need for need in ad_set.needs)

    def test_special_categories_list_every_targeted_country(self) -> None:
        def housing(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["special_ad_categories"] = ["HOUSING"]
            raw["campaign"]["ad_sets"][0]["targeting"]["countries"] = ["PL", "DE"]

        args = call(compiled(housing), "ads_create_campaign").args
        assert json.loads(args["special_ad_categories"]) == ["HOUSING"]
        assert json.loads(args["special_ad_category_country"]) == ["DE", "PL"]


class TestCreatives:
    def test_a_single_image(self) -> None:
        args = call(compiled(), "ads_create_creative").args
        assert args["image_hash"] == "abc123def456"
        assert args["message"] == "Friday afternoons, returned."
        assert args["headline"] == "Stop rebuilding the report"
        assert args["call_to_action_type"] == "SIGN_UP"
        assert args["link_url"] == "https://acme.example.com/webinar"
        assert args["page_id"] == "1111111111"

    def test_a_video_with_its_thumbnail_and_without(self) -> None:
        plans = every_shape()
        video = call(plans[1], "ads_create_creative")
        assert (video.args["video_id"], video.args["image_hash"]) == (
            "700000000000031",
            "thumb0001",
        )

        def bare(raw):  # type: ignore[no-untyped-def]
            creative(raw).update(mode="single_video", assets=[{"video_id": "700000000000031"}])

        missing = call(compiled(bare), "ads_create_creative")
        assert any("thumbnail" in need for need in missing.needs)

    def test_a_carousel(self) -> None:
        args = call(every_shape()[2], "ads_create_creative").args
        assert args["cards"] == [
            {"image_hash": "aaa111", "link": "https://a.example.com/1", "headline": "One"},
            {"video_id": "222", "description": "Two"},
        ]
        assert args["message"] == "Friday afternoons, returned."

    def test_several_assets_and_texts_are_a_pool_meta_mixes(self) -> None:
        args = call(every_shape()[3], "ads_create_creative").args
        assert args["multi_media"] == [{"image_hash": "aaa111"}, {"image_hash": "bbb222"}]
        assert args["primary_texts"] == ["First.", "Second."]
        assert args["headlines"] == ["H1", "H2"]
        assert "message" not in args and "image_hash" not in args

    def test_one_asset_with_several_texts_is_a_single_image_with_variants(self) -> None:
        def texts(raw):  # type: ignore[no-untyped-def]
            c = creative(raw)
            c["mode"] = "multi_variant"
            c["variants"] = [
                {"angle": "a", "primary_text": "First.", "headline": "Same"},
                {"angle": "b", "primary_text": "Second.", "headline": "Same"},
            ]

        args = call(compiled(texts), "ads_create_creative").args
        assert args["image_hash"] == "abc123def456"
        assert args["primary_texts"] == ["First.", "Second."]
        assert args["headline"] == "Same"  # one distinct value: the singular field

    def test_pinned_assets_become_placement_rules_with_one_fallback(self) -> None:
        creative_call = call(every_shape()[4], "ads_create_creative")
        assert creative_call.args["placement_customizations"] == [
            {"image_hash": "wide0001"},
            {
                "image_hash": "tall0001",
                "publisher_platforms": ["instagram"],
                "instagram_positions": ["story"],
            },
            {
                "image_hash": "reel0001",
                "publisher_platforms": ["facebook"],
                "facebook_positions": ["facebook_reels"],
            },
        ]
        assert not creative_call.needs

    def test_advantage_preferences_are_opted_in_and_out_by_name(self) -> None:
        spec = json.loads(
            call(every_shape()[4], "ads_create_creative").args["degrees_of_freedom_spec"]
        )
        assert spec == {
            "creative_features_spec": {
                "image_touchups": {"enroll_status": "OPT_OUT"},
                "text_optimizations": {"enroll_status": "OPT_IN"},
            }
        }

    def test_an_existing_post_goes_inline_in_the_ad(self) -> None:
        plan = every_shape()[5]
        assert not [c for c in plan.calls if c.tool == "ads_create_creative"]
        assert json.loads(call(plan, "ads_create_ad").args["creative"]) == {
            "object_story_id": "1111111111_999"
        }

    def test_an_instagram_post_names_its_account(self) -> None:
        def instagram(raw):  # type: ignore[no-untyped-def]
            c = creative(raw)
            for key in ("assets", "variants", "destination_url"):
                c.pop(key)
            c.update(
                mode="existing_post",
                instagram_media_id="18000000000000001",
                instagram_account_id="2222222222",
            )

        spec = json.loads(call(compiled(instagram), "ads_create_ad").args["creative"])
        assert spec == {
            "source_instagram_media_id": "18000000000000001",
            "instagram_user_id": "2222222222",
        }


class TestLocalFiles:
    @staticmethod
    def two_ads_one_file(raw):  # type: ignore[no-untyped-def]
        ad_set = raw["campaign"]["ad_sets"][0]
        first = ad_set["ads"][0]
        first["creative"]["assets"] = [{"local_path": "creatives/square.png"}]
        second = json.loads(json.dumps(first))
        second["name"] = "angle-b"
        second["creative"]["assets"] = [{"local_path": "./creatives/../creatives/square.png"}]
        ad_set["ads"].append(second)

    def test_one_upload_per_file_however_it_is_spelled(self, tmp_path: Path) -> None:
        plan = compiled(self.two_ads_one_file, asset_base=tmp_path)
        uploads = [c for c in plan.calls if c.tool == "ads_creative_upload_media"]
        assert len(uploads) == 1
        assert uploads[0].args == {"ad_account_id": "1234567890", "upload_source": "LOCAL_FILE"}
        assert uploads[0].file == tmp_path / "creatives" / "square.png"
        placeholder = "<id:ad_sets[0].ads[0].creative.assets[0]>"
        assert [c.args["image_hash"] for c in plan.calls if c.tool == "ads_create_creative"] == [
            placeholder,
            placeholder,
        ]

    def test_uploads_come_after_ad_sets_and_before_creatives(self, tmp_path: Path) -> None:
        tools = [c.tool for c in compiled(self.two_ads_one_file, asset_base=tmp_path).calls]
        assert tools.index("ads_creative_upload_media") == 2
        assert tools.index("ads_create_creative") == 3

    def test_a_file_already_on_the_account_is_not_uploaded_again(self, tmp_path: Path) -> None:
        plan = compiled(
            self.two_ads_one_file,
            asset_base=tmp_path,
            asset_lookup=lambda path: ("image_hash", "known0001"),
        )
        assert not [c for c in plan.calls if c.tool == "ads_creative_upload_media"]
        assert call(plan, "ads_create_creative").args["image_hash"] == "known0001"


class TestResume:
    def state(self, *objects: tuple[str, str, str]) -> CampaignState:
        state = CampaignState(slug="acme-webinar", ad_account_id="act_1234567890")
        for object_type, object_id, plan_ref in objects:
            state.record(
                CreatedObject(
                    id=object_id,
                    type=ObjectType(object_type),
                    provider=Provider.OFFICIAL_MCP,
                    plan_ref=plan_ref,
                )
            )
        return state

    def test_what_exists_is_done_and_its_id_is_filled_in(self) -> None:
        state = self.state(("campaign", "120210000000001", "campaign"))
        plan = compiled(state=state)
        campaign = call(plan, "ads_create_campaign")
        ad_set = call(plan, "ads_create_ad_set")
        assert campaign.done == "120210000000001"
        assert ad_set.args["campaign_id"] == "120210000000001"
        assert ad_set.refs == {}
        assert [c.tool for c in plan.pending] == [
            "ads_create_ad_set",
            "ads_create_creative",
            "ads_create_ad",
        ]

    def test_a_finished_build_has_nothing_pending(self) -> None:
        state = self.state(
            ("campaign", "1", "campaign"),
            ("ad_set", "2", "ad_sets[0]"),
            ("creative", "3", "ad_sets[0].ads[0].creative"),
            ("ad", "4", "ad_sets[0].ads[0]"),
        )
        plan = compiled(state=state)
        assert plan.pending == [] and plan.complete

    def test_a_need_on_something_already_built_does_not_hold_the_rest_up(self) -> None:
        def none(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0].pop("optimization_goal")

        state = self.state(("campaign", "1", "campaign"), ("ad_set", "2", "ad_sets[0]"))
        assert compiled(none, state=state).complete


@pytest.mark.parametrize("shape", range(8))
def test_every_shape_compiles_to_json(shape: int) -> None:
    plan = every_shape()[shape]
    json.dumps([c.args for c in plan.calls])
